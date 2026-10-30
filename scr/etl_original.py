"""
ETL: Datos_Mineria_Galaxy_ETL.xlsx -> esquema estrella en PostgreSQL (galaxy_dw)

Uso:
    python etl/etl.py --excel /ruta/Datos_Mineria_Galaxy_ETL.xlsx [--dry-run]
    python etl/etl.py --excel datos.xlsx --desde 2025-03-01 --hasta 2025-03-31

Requiere que 'sql/01_schema_estrella.sql' y 'sql/02_tablas_ml.sql'
ya se hayan ejecutado contra la base (ver README).
"""
import argparse
import sys
import time
import math
from pathlib import Path
import pandas as pd
from sqlalchemy import text, inspect
from uuid import uuid4

sys.path.append(str(Path(__file__).resolve().parent))
from db import get_engine          # noqa: E402
from logger import get_logger      # noqa: E402

log = get_logger(__name__)

SCHEMA = "galaxy_dw"

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]

# Orden explícito de carga: dims primero (respetando dependencias), fact al final.
DIMENSIONS_ORDER = [
    "dim_fecha", "dim_equipo", "dim_sitio", "dim_prioridad", "dim_estado",
    "dim_clasificacion", "dim_falla_cierre", "dim_categoria_ticket",
    "dim_solicitud_falla", "dim_apertura", "dim_operador",
]

# Columna(s) natural(es) UNIQUE por dimensión, para ON CONFLICT.
DIM_NATURAL_KEY = {
    "dim_fecha":            "fecha_key",
    "dim_equipo":           "equipo_codigo",
    "dim_sitio":            "sitio_nombre",
    "dim_prioridad":        "prioridad",
    "dim_estado":           "estado",
    "dim_clasificacion":    "clasificacion",
    "dim_falla_cierre":     "tipo_falla_cierre",
    "dim_operador":         "operador_nombre",
    "dim_categoria_ticket": ("tipo_ticket", "tipo_requerimiento"),
    "dim_solicitud_falla":  ("tipo_solicitud", "tipo_falla"),
    "dim_apertura":         ("modo_apertura", "origen"),
}


# ---------------------------------------------------------------------
# EXTRACT
# ---------------------------------------------------------------------
def extraer(ruta: str) -> pd.DataFrame:
    """
    Lee el archivo fuente. Acepta .xlsx y .csv.
    Robusto frente a:
      - CSVs de Excel en español (separador ';', encoding latin-1/cp1252)
      - Fechas en formato dd/mm/yyyy
    """
    log.info("Extrayendo archivo: %s", ruta)
    t0 = time.time()

    path = Path(ruta)
    ext = path.suffix.lower()

    # Si la ruta relativa no existe, probar relativa a la carpeta del script
    if not path.exists():
        alterna = Path(__file__).resolve().parent / ruta
        if alterna.exists():
            log.info("Ruta no encontrada; usando alterna: %s", alterna)
            path = alterna
        else:
            raise FileNotFoundError(
                f"No se encontró el archivo '{ruta}'. Probé también '{alterna}'."
            )

    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(path, sheet_name="Sheet1", dtype={"Numero_ticket": "string"}, keep_default_na=False)
    elif ext == ".csv":
        df = _leer_csv_robusto(path)
    else:
        raise ValueError(f"Extensión no soportada: {ext}. Usa .xlsx o .csv")

    df = validar_entrada(df)

    log.info("Extraídas %d filas en %.2fs", len(df), time.time() - t0)
    return df


FECHAS = ("Fecha_creacion_ticket", "Fecha_respuesta", "Fecha_cierre")
COLUMNAS_ESPERADAS = {
    "Numero_ticket", *FECHAS, "Estado", "Prioridad", "Tiempo_abierto",
    "Tipo_ticket", "Tipo_requerimiento", "Asunto", "Nota_cierre", "Solucion",
    "Operador_apertura", "Modo_apertura", "Origen", "Tipo_solicitud", "Tipo_falla",
    "Tipo_falla_cierre", "Operador_cierre", "Equipo", "Tipo", "Clasificación",
    "Sitio", "Duración (minutos)",
}
ESTADOS_ABIERTOS = {"abierto", "pendiente", "en progreso", "en proceso", "escalado", "work in progress", "work_in_progress", "wip"}
ESTADOS_CERRADOS = {"cerrado", "resuelto"}


def _fecha(valor):
    """ISO se interpreta como ISO; formatos locales usan día primero."""
    if pd.isna(valor):
        return pd.NaT
    if isinstance(valor, (int, float)):
        raise ValueError("Fecha numérica sin formato de fecha explícito")
    if isinstance(valor, str) and len(valor) >= 10 and valor[4] == "-" and valor[7] == "-":
        parsed = pd.Timestamp(valor)
    else:
        parsed = pd.to_datetime(valor, dayfirst=True, errors="raise")
    if pd.isna(parsed):
        raise ValueError("Fecha no vacía no interpretable")
    if parsed.tzinfo is not None:
        raise ValueError("La base utiliza TIMESTAMP sin zona horaria")
    return parsed


def validar_entrada(df: pd.DataFrame) -> pd.DataFrame:
    """Valida todo el snapshot sin imputar datos de respuesta o cierre."""
    faltantes = COLUMNAS_ESPERADAS - set(df.columns)
    if faltantes:
        raise ValueError(f"Faltan columnas esperadas: {sorted(faltantes)}")
    df = df.copy()
    # Solo blancos son ausencia. No convertir identificadores como NA en nulos.
    for col in df.columns:
        df[col] = df[col].map(lambda v: None if isinstance(v, str) and not v.strip() else v)
    # Una carga formada solo por abiertos puede tener columnas textuales 100%
    # nulas; pandas infiere float. Mantener tipos de claves naturales estables.
    for col in COLUMNAS_ESPERADAS - set(FECHAS) - {"Tiempo_abierto", "Duración (minutos)"}:
        df[col] = df[col].astype("string")
    df["Numero_ticket"] = df["Numero_ticket"].astype("string").str.strip()
    if df["Numero_ticket"].isna().any() or df["Numero_ticket"].duplicated().any():
        raise ValueError("Numero_ticket debe estar informado y ser único dentro del archivo")
    for col in FECHAS:
        try:
            df[col] = pd.to_datetime(df[col].map(_fecha))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f"Fecha inválida en {col}") from exc
    if df["Fecha_creacion_ticket"].isna().any():
        raise ValueError("Fecha_creacion_ticket es obligatoria")
    estado = df["Estado"].astype("string").str.strip().str.casefold().str.replace(r"\s+", " ", regex=True)
    if not estado.isin(ESTADOS_ABIERTOS | ESTADOS_CERRADOS).all():
        raise ValueError("Estado ausente o no reconocido; revisar la política documentada")
    cerrados = estado.isin(ESTADOS_CERRADOS)
    cierre = df["Fecha_cierre"].notna()
    if (cerrados & ~cierre).any() or (~cerrados & cierre).any():
        raise ValueError("Estado y Fecha_cierre son inconsistentes")
    for col in ("Fecha_respuesta", "Fecha_cierre"):
        if (df[col].notna() & (df[col] < df["Fecha_creacion_ticket"])).any():
            raise ValueError(f"{col} no puede preceder la creación")
    if (cierre & df["Fecha_respuesta"].notna() & (df["Fecha_cierre"] < df["Fecha_respuesta"])).any():
        raise ValueError("Fecha_cierre no puede preceder la respuesta")
    for col in ("Nota_cierre", "Solucion", "Tipo_falla_cierre", "Operador_cierre", "Duración (minutos)"):
        if ((~cierre) & df[col].notna()).any():
            raise ValueError(f"{col} informado sin Fecha_cierre; no se inventará cierre")
    for col in ("Tiempo_abierto", "Duración (minutos)"):
        try:
            df[col] = pd.to_numeric(df[col], errors="raise")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Valor no numérico en {col}") from exc
        if ((df[col].notna()) & ((df[col] < 0) | ~df[col].map(lambda v: pd.isna(v) or math.isfinite(v)))).any():
            raise ValueError(f"Duración negativa o no finita en {col}")
    if (df["Tiempo_abierto"].dropna() % 1 != 0).any():
        raise ValueError("Tiempo_abierto debe contener minutos enteros")
    requeridas = ["Prioridad", "Estado", "Tipo_ticket", "Tipo_requerimiento",
                  "Tipo_solicitud", "Tipo_falla", "Modo_apertura", "Origen", "Operador_apertura"]
    for col in requeridas:
        if df[col].isna().any():
            raise ValueError(f"{col} es obligatorio")
    for col in ("Tipo_falla_cierre", "Operador_cierre"):
        if (cerrados & df[col].isna()).any():
            raise ValueError(f"{col} es obligatorio para tickets cerrados/resueltos")
    tipos = df[["Equipo", "Tipo"]].dropna(subset=["Equipo"]).drop_duplicates()
    if tipos["Equipo"].duplicated().any():
        raise ValueError("Un equipo tiene tipos contradictorios en el mismo archivo")
    return df


def filtrar_rango(df, desde=None, hasta=None):
    """Ambos límites son días inclusivos, incluso si la fuente tiene hora."""
    if (desde is None) != (hasta is None):
        raise ValueError("Debes pasar --desde y --hasta juntos")
    if desde is None:
        return df.copy()
    desde, hasta = pd.Timestamp(desde).normalize(), pd.Timestamp(hasta).normalize()
    if pd.isna(desde) or pd.isna(hasta) or desde > hasta:
        raise ValueError("Rango de fechas inválido")
    return df[(df["Fecha_creacion_ticket"] >= desde) &
              (df["Fecha_creacion_ticket"] < hasta + pd.Timedelta(days=1))].copy()


def _leer_csv_robusto(path: Path) -> pd.DataFrame:
    """
    Lee un CSV probando combinaciones de encoding y detectando separador.
    Prioriza utf-8, cae a latin-1 (Excel ES) y por último cp1252.
    """
    encodings = ["utf-8", "latin-1", "cp1252"]
    ultimo_error = None

    for enc in encodings:
        try:
            df = pd.read_csv(path, sep=None, engine="python", encoding=enc,
                             dtype={"Numero_ticket": "string"}, keep_default_na=False)
            log.info("CSV leído con encoding=%s, %d filas, %d columnas",
                     enc, len(df), len(df.columns))
            return df
        except (UnicodeDecodeError, pd.errors.ParserError) as e:
            log.warning("Falló lectura con encoding=%s: %s", enc, e)
            ultimo_error = e

    raise RuntimeError(
        f"No se pudo leer el CSV con ninguno de estos encodings: {encodings}. "
        f"Último error: {ultimo_error}"
    )

# ---------------------------------------------------------------------
# TRANSFORM — dimensiones
# ---------------------------------------------------------------------
def construir_dim_fecha(df: pd.DataFrame) -> pd.DataFrame:
    """
    dim_fecha tiene fecha_key natural (YYYYMMDD), no SERIAL.
    Cubre todas las fechas usadas en el hecho (creación, respuesta, cierre).
    """
    fechas = pd.concat([
        df["Fecha_creacion_ticket"].dt.normalize(),
        df["Fecha_respuesta"].dt.normalize(),
        df["Fecha_cierre"].dt.normalize(),
    ]).dropna().drop_duplicates().sort_values().reset_index(drop=True)

    dim = pd.DataFrame({"fecha": fechas})
    dim["fecha_key"] = dim["fecha"].dt.strftime("%Y%m%d").astype("Int64")
    dim["anio"] = dim["fecha"].dt.year
    dim["mes"] = dim["fecha"].dt.month
    dim["nombre_mes"] = dim["mes"].apply(lambda m: MESES[m - 1])
    dim["dia"] = dim["fecha"].dt.day
    dim["trimestre"] = dim["fecha"].dt.quarter
    dim["dia_semana"] = dim["fecha"].dt.weekday + 1
    dim["nombre_dia_semana"] = dim["dia_semana"].apply(lambda d: DIAS_SEMANA[d - 1])
    dim["es_fin_semana"] = dim["dia_semana"].isin([6, 7])

    return dim[["fecha_key", "fecha", "anio", "mes", "nombre_mes", "dia",
                "trimestre", "dia_semana", "nombre_dia_semana", "es_fin_semana"]]


def _dim_simple(valores: pd.Series, val_col: str) -> pd.DataFrame:
    """Dimensión de una sola columna natural. Postgres asigna la surrogate key."""
    unicos = pd.Series(valores.dropna().unique()).sort_values().reset_index(drop=True)
    return pd.DataFrame({val_col: unicos})


def construir_dimensiones(df: pd.DataFrame) -> dict:
    """Construye todas las dimensiones SIN surrogate keys (las asigna Postgres)."""
    log.info("Construyendo dimensiones...")
    t0 = time.time()

    dims = {}
    dims["dim_fecha"] = construir_dim_fecha(df)

    # dim_equipo: par (equipo_codigo, tipo_equipo)
    eq = df[["Equipo", "Tipo"]].drop_duplicates().dropna(subset=["Equipo"])
    eq = eq.sort_values("Equipo").reset_index(drop=True)
    dims["dim_equipo"] = eq.rename(
        columns={"Equipo": "equipo_codigo", "Tipo": "tipo_equipo"}
    )[["equipo_codigo", "tipo_equipo"]]

    dims["dim_sitio"] = _dim_simple(df["Sitio"], "sitio_nombre")
    dims["dim_prioridad"] = _dim_simple(df["Prioridad"], "prioridad")
    dims["dim_estado"] = _dim_simple(df["Estado"], "estado")
    dims["dim_clasificacion"] = _dim_simple(df["Clasificación"], "clasificacion")
    dims["dim_falla_cierre"] = _dim_simple(df["Tipo_falla_cierre"], "tipo_falla_cierre")

    ct = df[["Tipo_ticket", "Tipo_requerimiento"]].drop_duplicates()
    ct = ct.sort_values(["Tipo_ticket", "Tipo_requerimiento"]).reset_index(drop=True)
    dims["dim_categoria_ticket"] = ct.rename(columns={
        "Tipo_ticket": "tipo_ticket",
        "Tipo_requerimiento": "tipo_requerimiento",
    })

    sf = df[["Tipo_solicitud", "Tipo_falla"]].drop_duplicates()
    sf = sf.sort_values(["Tipo_solicitud", "Tipo_falla"]).reset_index(drop=True)
    dims["dim_solicitud_falla"] = sf.rename(columns={
        "Tipo_solicitud": "tipo_solicitud",
        "Tipo_falla": "tipo_falla",
    })

    ap = df[["Modo_apertura", "Origen"]].drop_duplicates()
    ap = ap.sort_values(["Modo_apertura", "Origen"]).reset_index(drop=True)
    dims["dim_apertura"] = ap.rename(columns={
        "Modo_apertura": "modo_apertura",
        "Origen": "origen",
    })

    operadores = pd.concat([df["Operador_apertura"], df["Operador_cierre"]]).dropna()
    dims["dim_operador"] = _dim_simple(operadores, "operador_nombre")

    resumen = {k: len(v) for k, v in dims.items()}
    log.info("Dimensiones construidas en %.2fs: %s", time.time() - t0, resumen)
    return dims


# ---------------------------------------------------------------------
# LOAD — upsert de dimensiones
# ---------------------------------------------------------------------
def _staging(conn, nombre: str, tabla: pd.DataFrame) -> str:
    """Tabla TEMP con tipos de destino; no comparte nombres ni datos entre sesiones."""
    staging = "stg_" + uuid4().hex
    cols = ", ".join(tabla.columns)
    conn.execute(text(f"CREATE TEMP TABLE {staging} ON COMMIT DROP AS "
                      f"SELECT {cols} FROM {SCHEMA}.{nombre} WITH NO DATA"))
    if not tabla.empty:
        valores = [{c: None if pd.isna(v) else v for c, v in row.items()}
                   for row in tabla.to_dict(orient="records")]
        insert = text(f"INSERT INTO pg_temp.{staging} ({cols}) VALUES "
                      f"({', '.join(':' + c for c in tabla.columns)})")
        for i in range(0, len(valores), 500):
            conn.execute(insert, valores[i:i + 500])
    return staging


def _upsert_dimension(conn, nombre: str, tabla: pd.DataFrame) -> int:
    if nombre not in DIM_NATURAL_KEY:
        raise ValueError("Dimensión no permitida")
    staging = _staging(conn, nombre, tabla)
    cols = ", ".join(tabla.columns)
    natural = DIM_NATURAL_KEY[nombre]
    keys = ", ".join(natural) if isinstance(natural, tuple) else natural
    result = conn.execute(text(f"INSERT INTO {SCHEMA}.{nombre} ({cols}) "
                               f"SELECT {cols} FROM pg_temp.{staging} "
                               f"ORDER BY {keys} ON CONFLICT ({keys}) DO NOTHING"))
    conn.execute(text(f"DROP TABLE pg_temp.{staging}"))
    return result.rowcount or 0


def leer_mapeos(conn) -> dict:
    """
    Lee desde Postgres los mapeos natural -> surrogate_key de cada dim.
    Se usan para construir la fact con las keys reales asignadas por Postgres.
    """
    mapeos = {}

    simples = {
        "dim_equipo":        ("equipo_key",        "equipo_codigo"),
        "dim_sitio":         ("sitio_key",         "sitio_nombre"),
        "dim_prioridad":     ("prioridad_key",     "prioridad"),
        "dim_estado":        ("estado_key",        "estado"),
        "dim_clasificacion": ("clasificacion_key", "clasificacion"),
        "dim_falla_cierre":  ("falla_cierre_key",  "tipo_falla_cierre"),
        "dim_operador":      ("operador_key",      "operador_nombre"),
    }
    for nombre, (key_col, nat_col) in simples.items():
        mapeos[nombre] = pd.read_sql(
            f"SELECT {key_col}, {nat_col} FROM {SCHEMA}.{nombre}",
            conn,
        )

    mapeos["dim_categoria_ticket"] = pd.read_sql(
        f"SELECT categoria_ticket_key, tipo_ticket, tipo_requerimiento "
        f"FROM {SCHEMA}.dim_categoria_ticket", conn,
    )
    mapeos["dim_solicitud_falla"] = pd.read_sql(
        f"SELECT solicitud_falla_key, tipo_solicitud, tipo_falla "
        f"FROM {SCHEMA}.dim_solicitud_falla", conn,
    )
    mapeos["dim_apertura"] = pd.read_sql(
        f"SELECT apertura_key, modo_apertura, origen "
        f"FROM {SCHEMA}.dim_apertura", conn,
    )

    for nombre, tabla in mapeos.items():
        natural = DIM_NATURAL_KEY[nombre]
        keys = natural if isinstance(natural, tuple) else (natural,)
        for col in keys:
            tabla[col] = tabla[col].astype("string")
    return mapeos


# ---------------------------------------------------------------------
# TRANSFORM — hecho (necesita mapeos de Postgres)
# ---------------------------------------------------------------------
def construir_fact_tickets(df: pd.DataFrame, mapeos: dict) -> pd.DataFrame:
    """
    Construye fact_tickets usando los mapeos natural -> surrogate_key
    leídos de Postgres (así las keys son las reales).
    """
    log.info("Construyendo fact_tickets...")
    t0 = time.time()

    f = df.copy()

    # Fechas: dim_fecha tiene key natural YYYYMMDD
    f["fecha_creacion_key"] = f["Fecha_creacion_ticket"].dt.strftime("%Y%m%d").astype("Int64")
    f["fecha_respuesta_key"] = f["Fecha_respuesta"].dt.strftime("%Y%m%d").astype("Int64")
    f["fecha_cierre_key"] = f["Fecha_cierre"].dt.strftime("%Y%m%d").astype("Int64")

    # Merges contra mapeos
    f = f.merge(mapeos["dim_equipo"],
                left_on="Equipo", right_on="equipo_codigo", how="left")
    f = f.merge(mapeos["dim_sitio"],
                left_on="Sitio", right_on="sitio_nombre", how="left")
    f = f.merge(mapeos["dim_prioridad"],
                left_on="Prioridad", right_on="prioridad", how="left")
    f = f.merge(mapeos["dim_estado"],
                left_on="Estado", right_on="estado", how="left")
    f = f.merge(mapeos["dim_clasificacion"],
                left_on="Clasificación", right_on="clasificacion", how="left")
    f = f.merge(mapeos["dim_falla_cierre"],
                left_on="Tipo_falla_cierre", right_on="tipo_falla_cierre", how="left")
    f = f.merge(mapeos["dim_categoria_ticket"],
                left_on=["Tipo_ticket", "Tipo_requerimiento"],
                right_on=["tipo_ticket", "tipo_requerimiento"], how="left")
    f = f.merge(mapeos["dim_solicitud_falla"],
                left_on=["Tipo_solicitud", "Tipo_falla"],
                right_on=["tipo_solicitud", "tipo_falla"], how="left")
    f = f.merge(mapeos["dim_apertura"],
                left_on=["Modo_apertura", "Origen"],
                right_on=["modo_apertura", "origen"], how="left")

    # Operador: mapeo único, usado dos veces (roleplaying)
    op = mapeos["dim_operador"]
    f = f.merge(
        op.rename(columns={"operador_key": "operador_apertura_key"}),
        left_on="Operador_apertura", right_on="operador_nombre", how="left",
    )
    f = f.merge(
        op.rename(columns={"operador_key": "operador_cierre_key"}),
        left_on="Operador_cierre", right_on="operador_nombre",
        how="left", suffixes=("", "_cierre"),
    )

    f["es_incidente"] = f["Tipo_ticket"].eq("Incidente")

    resultado = f.rename(columns={
        "Numero_ticket": "numero_ticket",
        "Fecha_creacion_ticket": "ts_creacion",
        "Fecha_respuesta": "ts_respuesta",
        "Fecha_cierre": "ts_cierre",
        "Asunto": "asunto",
        "Nota_cierre": "nota_cierre",
        "Solucion": "solucion",
        "Tiempo_abierto": "tiempo_abierto_min",
        "Duración (minutos)": "duracion_min",
    })[[
        "numero_ticket", "fecha_creacion_key", "fecha_respuesta_key", "fecha_cierre_key",
        "ts_creacion", "ts_respuesta", "ts_cierre",
        "equipo_key", "sitio_key", "prioridad_key", "estado_key",
        "categoria_ticket_key", "solicitud_falla_key", "falla_cierre_key",
        "apertura_key", "clasificacion_key", "operador_apertura_key", "operador_cierre_key",
        "asunto", "nota_cierre", "solucion",
        "tiempo_abierto_min", "duracion_min", "es_incidente",
    ]]

    # Validación: FKs obligatorias no deben quedar nulas (equipo y sitio sí pueden)
    obligatorias = [c for c in resultado.columns
                    if c.endswith("_key") and c not in (
                        "equipo_key", "sitio_key", "fecha_respuesta_key", "fecha_cierre_key",
                        "falla_cierre_key", "operador_cierre_key", "clasificacion_key")]
    nulos = resultado[obligatorias].isna().sum()
    nulos = nulos[nulos > 0]
    if not nulos.empty:
        raise ValueError(
            f"Se generaron FKs nulas donde no debería: {nulos.to_dict()}. "
            f"Probablemente una dim no se cargó correctamente."
        )

    log.info("fact_tickets construida en %.2fs: %d filas",
             time.time() - t0, len(resultado))
    return resultado


# ---------------------------------------------------------------------
# LOAD — helpers
# ---------------------------------------------------------------------
def validar_modelo(conn):
    """Rechaza un DDL incompatible antes de escribir; nunca migra automáticamente."""
    columnas = {c["name"]: c for c in inspect(conn).get_columns("fact_tickets", schema=SCHEMA)}
    from sqlalchemy import String
    opcionales = {"fecha_respuesta_key", "fecha_cierre_key", "ts_respuesta", "ts_cierre",
                  "falla_cierre_key", "operador_cierre_key", "clasificacion_key", "tiempo_abierto_min"}
    if not isinstance(columnas["numero_ticket"]["type"], String) or any(
        not columnas[n]["nullable"] for n in opcionales
    ):
        raise ValueError("DDL incompatible con tickets abiertos/identificadores de texto. "
                         "Revisar docs/CONTRATO_FISICO.md y la migración propuesta; "
                         "el ETL no modifica el modelo automáticamente.")
    uniques = inspect(conn).get_unique_constraints("fact_tickets", schema=SCHEMA)
    if not any(u["column_names"] == ["numero_ticket"] for u in uniques):
        raise ValueError("Se requiere UNIQUE(numero_ticket) para la carga idempotente")


def _upsert_fact(conn, fact):
    staging = _staging(conn, "fact_tickets", fact)
    cols = ", ".join(fact.columns)
    updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in fact.columns if c != "numero_ticket")
    result = conn.execute(text(f"INSERT INTO {SCHEMA}.fact_tickets ({cols}) "
                              f"SELECT {cols} FROM pg_temp.{staging} ORDER BY numero_ticket "
                              f"ON CONFLICT (numero_ticket) DO UPDATE SET {updates}"))
    conn.execute(text(f"DROP TABLE pg_temp.{staging}"))
    return result.rowcount


def cargar(dims: dict, df_original: pd.DataFrame,
           dry_run: bool = False, desde=None, hasta=None,
           truncate: bool = False):
    """
    Carga dimensiones primero y fact después, en una sola transacción.
    La fact se construye DESPUÉS de cargar dims, usando los mapeos
    natural -> surrogate_key leídos de Postgres.
    """
    if truncate:
        raise ValueError("--truncate está deshabilitado: solo se permite upsert por ticket")
    df_original = validar_entrada(df_original)
    if desde is not None or hasta is not None:
        df_original = filtrar_rango(df_original, desde, hasta)
    if df_original.empty:
        log.info("Sin tickets que cargar")
        return
    # Las dimensiones provienen siempre de las mismas filas validadas/filtradas.
    dims = construir_dimensiones(df_original)
    if dry_run:
        log.info("[dry-run] No se escribe en la base. Resumen:")
        for nombre in DIMENSIONS_ORDER:
            log.info("  %-28s -> %d filas", nombre, len(dims[nombre]))
        log.info("  (fact_tickets se construiría después de cargar dims)")
        return

    engine = get_engine()
    t0 = time.time()

    try:
        with engine.begin() as conn:
            validar_modelo(conn)
            if inspect(conn).has_table('etl_lotes', schema=SCHEMA):
                raise ValueError('Usar carga_operacional.cargar_lote: el esquema operacional exige auditoría')
            # Serializa este ETL por base y esquema. Lock liberado por commit/rollback.
            # Evita carreras de dimensiones y actualizaciones parciales entre cargas.
            conn.execute(text("SELECT pg_advisory_xact_lock(712984321)"))

            # 1. DIMENSIONES
            for nombre in DIMENSIONS_ORDER:
                insertadas = _upsert_dimension(conn, nombre, dims[nombre])
                log.info("Dim %-25s -> %d candidatas, %d insertadas",
                         nombre, len(dims[nombre]), insertadas)

            # 2. LEER MAPEOS NATURAL -> SURROGATE
            mapeos = leer_mapeos(conn)
            log.info("Mapeos leídos: %s", {k: len(v) for k, v in mapeos.items()})

            # 3. CONSTRUIR FACT con keys reales
            fact = construir_fact_tickets(df_original, mapeos)

            # Actualiza por clave natural sin borrar otros tickets ni cambiar ticket_key.
            _upsert_fact(conn, fact)
            log.info("Fact fact_tickets -> %d tickets insertados/actualizados", len(fact))

        log.info("Carga completada en %.2fs", time.time() - t0)

    except Exception:
        log.error("Error durante la carga; la transacción fue revertida.")
        raise
    finally:
        engine.dispose()


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------
def main_historico():
    parser = argparse.ArgumentParser(description="ETL Excel/CSV -> esquema estrella Postgres")
    parser.add_argument("--excel", required=True,
                        help="Ruta al archivo fuente (.xlsx o .csv)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo transformar y validar, no escribir en la BD")
    parser.add_argument("--truncate", action="store_true",
                        help="Opción heredada deshabilitada; siempre se rechaza")
    parser.add_argument("--desde", type=str, default=None,
                        help="Fecha inicial para modo incremental (YYYY-MM-DD)")
    parser.add_argument("--hasta", type=str, default=None,
                        help="Fecha final para modo incremental (YYYY-MM-DD)")
    args = parser.parse_args()
    if args.truncate:
        parser.error("--truncate está deshabilitado; carga idempotente por Numero_ticket")

    desde = pd.to_datetime(args.desde).normalize() if args.desde else None
    hasta = pd.to_datetime(args.hasta).normalize() if args.hasta else None

    if (desde is None) != (hasta is None):
        log.error("Debes pasar --desde y --hasta juntos, o ninguno.")
        sys.exit(2)

    t_inicio = time.time()
    log.info("=== Inicio ETL Galaxy Mining ===")

    try:
        df = extraer(args.excel)

        if desde is not None:
            antes = len(df)
            df = filtrar_rango(df, desde, hasta)
            log.info("Filtro incremental %s..%s: %d -> %d filas",
                     desde.date(), hasta.date(), antes, len(df))

            if df.empty:
                log.warning("No quedaron filas tras el filtro incremental. Nada que cargar.")
                return

        dims = construir_dimensiones(df)

        cargar(dims, df, dry_run=args.dry_run,
               desde=desde, hasta=hasta, truncate=args.truncate)

        log.info("=== ETL completado OK en %.2fs ===", time.time() - t_inicio)

    except Exception:
        log.exception("=== ETL FALLIDO tras %.2fs ===", time.time() - t_inicio)
        sys.exit(1)


def main():
    from carga_operacional import main as main_operacional
    main_operacional()


if __name__ == "__main__":
    main()
