"""Carga auditada por corte y detección independiente de incumplimientos."""
import argparse
import hashlib
import io
import json
import math
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import text, inspect
import etl_original as etl
from db import get_engine
from corte_operacional import ConfiguracionCorte
from alertas_operacionales import evaluar_corte


class ConflictoVersion(ValueError):
    pass


def _valor(v):
    if pd.isna(v): return None
    if isinstance(v, (datetime, pd.Timestamp)): return v.isoformat()
    if isinstance(v, (int, float, Decimal)) and not isinstance(v, bool):
        if not math.isfinite(v): raise ValueError('Valor no finito')
        return format(Decimal(str(v)).normalize(), 'f')
    return v


def huella(fila):
    datos = {k: _valor(fila[k]) for k in sorted(etl.COLUMNAS_ESPERADAS)}
    return hashlib.sha256(json.dumps(datos, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode()).hexdigest()


def _marca_origen(valor):
    if pd.isna(valor) or (isinstance(valor, str) and not valor.strip()):
        raise ValueError('La marca de modificación de origen debe estar informada')
    if isinstance(valor, (int, float)):
        raise ValueError('Marca de modificación numérica ambigua')
    marca = pd.Timestamp(valor)
    if pd.isna(marca): raise ValueError('Marca de modificación inválida')
    if marca.tzinfo is None:
        # Contrato explícito: timestamps sin offset del origen son hora Santiago.
        marca = marca.tz_localize('America/Santiago', ambiguous='raise', nonexistent='raise')
    return marca.to_pydatetime()


def seleccionar_incremental(df, corte, config, columna_modificacion=None, completo=False):
    desde, corte = config.ventana(corte)
    if columna_modificacion is None:
        return df.copy(), {}  # Nunca filtrar creación como sustituto de modificación.
    if columna_modificacion in etl.COLUMNAS_ESPERADAS:
        raise ValueError('Una columna de negocio existente no es la marca de modificación de origen')
    if columna_modificacion not in df.columns:
        raise ValueError('No existe la columna de modificación configurada')
    marcas = df[columna_modificacion].map(_marca_origen)
    if (marcas > corte).any(): raise ValueError('Modificación de origen posterior al corte')
    selected = df if completo else df[(marcas >= desde) & (marcas <= corte)]
    return selected.copy(), {str(df.loc[i, 'Numero_ticket']): marcas.loc[i] for i in selected.index}


def _preflight(conn):
    etl.validar_modelo(conn)
    for table in ('etl_lotes','etl_ticket_version','alertas_operacionales'):
        if not inspect(conn).has_table(table, schema='galaxy_dw'):
            raise ValueError('Falta migración aditiva 04_lotes_alertas.sql; no se aplicará automáticamente')


def _decidir(anterior, hash_nuevo, corte, modificacion, confirmado, existe):
    if anterior is None:
        if existe and not confirmado:
            raise ConflictoVersion('Ticket previo sin trazabilidad: se requiere bootstrap confirmado')
        return True
    igual = anterior['hash_contenido'] == hash_nuevo
    if igual: return False
    if corte <= anterior['ultimo_corte']:
        raise ConflictoVersion('Contenido contradictorio en corte anterior o igual')
    vieja = anterior['modificacion_origen']
    if modificacion is not None and vieja is not None:
        if modificacion <= vieja:
            raise ConflictoVersion('Modificación de origen anterior o igual con contenido distinto')
        return True
    if not confirmado:
        raise ConflictoVersion('Sin versiones de origen comparables: snapshot requiere confirmación explícita')
    return True


def cargar_lote(df, *, fecha_corte, archivo_origen, hash_archivo,
                lote_id=None, config=None, snapshot_confirmado=False,
                columna_modificacion=None, completo=False, engine=None):
    config = config or ConfiguracionCorte()
    corte = config.validar(fecha_corte)
    desde, _ = config.ventana(corte)
    lote = str(uuid.UUID(str(lote_id))) if lote_id else str(uuid.uuid4())
    if len(hash_archivo) != 64 or any(c not in '0123456789abcdef' for c in hash_archivo):
        raise ValueError('hash_archivo debe ser SHA256 hexadecimal')
    politica = 'SNAPSHOT_CONFIRMADO' if snapshot_confirmado else 'RECHAZAR'
    modo = ('COMPLETO' if completo else 'MODIFICACION_ORIGEN') if columna_modificacion else 'ARCHIVO_SIN_MARCA'
    own_engine = engine is None
    engine = engine or get_engine()
    iniciado = False
    try:
        with engine.begin() as conn:
            _preflight(conn)
            created = conn.execute(text('''INSERT INTO galaxy_dw.etl_lotes
                (lote_id,fecha_corte,archivo_origen,hash_archivo,ventana_desde,
                 solapamiento_dias,modo_extraccion,columna_modificacion,politica_conflicto,filas_recibidas,estado_ejecucion)
                VALUES (:lote,:corte,:archivo,:hash,:desde,:dias,:modo,:columna,:politica,:recibidas,'INICIADO')
                ON CONFLICT (lote_id) DO NOTHING RETURNING lote_id'''),
                dict(lote=lote,corte=corte,archivo=Path(archivo_origen).name,hash=hash_archivo,
                     desde=desde,dias=config.solapamiento_dias,modo=modo,columna=columna_modificacion,
                     politica=politica,recibidas=len(df))).first()
            if created is None:
                prev = conn.execute(text('SELECT * FROM galaxy_dw.etl_lotes WHERE lote_id=:id FOR UPDATE'),{'id':lote}).mappings().one()
                if (prev['hash_archivo'] != hash_archivo or prev['fecha_corte'] != corte
                    or prev['politica_conflicto'] != politica or prev['modo_extraccion'] != modo
                    or prev['columna_modificacion'] != columna_modificacion
                    or prev['solapamiento_dias'] != config.solapamiento_dias):
                    raise ConflictoVersion('lote_id reutilizado con otro contrato')
                if prev['estado_ejecucion'] != 'COMPLETADO':
                    raise ConflictoVersion('Lote no completado: reconciliar y reintentar con otro identificador')
                return dict(prev)
            iniciado = True
        # El inicio es durable; el éxito y todas las escrituras de negocio son atómicos.
        with engine.begin() as conn:
            conn.execute(text('SELECT pg_advisory_xact_lock(712984321)'))
            data = etl.validar_entrada(df.reset_index(drop=True))
            data, marcas = seleccionar_incremental(data,corte,config,columna_modificacion,completo)
            for fecha in etl.FECHAS:
                if (data[fecha] > pd.Timestamp(corte.replace(tzinfo=None))).any():
                    raise ValueError('Evento del ticket posterior al corte declarado')
            for row in data.to_dict('records'):
                marca = marcas.get(str(row['Numero_ticket']))
                if marca is not None and marca < _marca_origen(row['Fecha_creacion_ticket']):
                    raise ValueError('Modificación de origen anterior a la creación del ticket')
            ids = list(data['Numero_ticket'])
            actuales = {r['numero_ticket']:dict(r) for r in conn.execute(text(
                'SELECT * FROM galaxy_dw.fact_tickets WHERE numero_ticket = ANY(CAST(:ids AS TEXT[]))'),{'ids':ids}).mappings()}
            versiones = {r['numero_ticket']:dict(r) for r in conn.execute(text(
                'SELECT * FROM galaxy_dw.etl_ticket_version WHERE numero_ticket = ANY(CAST(:ids AS TEXT[]))'),{'ids':ids}).mappings()}
            huellas = {str(row['Numero_ticket']):huella(row) for row in data.to_dict('records')}
            cambiar = []
            for row in data.to_dict('records'):
                ticket = str(row['Numero_ticket'])
                if _decidir(versiones.get(ticket),huellas[ticket],corte,marcas.get(ticket),snapshot_confirmado,ticket in actuales):
                    cambiar.append(ticket)
            counts = dict(insertadas=0,actualizadas=0,sin_cambios=0)
            changed = data[data['Numero_ticket'].isin(cambiar)]
            if not changed.empty:
                dims = etl.construir_dimensiones(changed)
                for nombre in etl.DIMENSIONS_ORDER:
                    etl._upsert_dimension(conn,nombre,dims[nombre])
                fact = etl.construir_fact_tickets(changed,etl.leer_mapeos(conn))
                for row in fact.to_dict('records'):
                    prev = actuales.get(row['numero_ticket'])
                    if prev is None: counts['insertadas'] += 1
                    elif all(_valor(prev[k]) == _valor(v) for k,v in row.items()): counts['sin_cambios'] += 1
                    else: counts['actualizadas'] += 1
                etl._upsert_fact(conn,fact)
            counts['sin_cambios'] += len(data) - len(changed)
            for ticket in huellas:
                prev = versiones.get(ticket)
                if prev and corte < prev['ultimo_corte']:
                    continue  # Un reproceso idéntico no retrocede la versión.
                # No rebajar una marca real si el snapshot posterior no trae esa marca.
                marca = marcas.get(ticket)
                if marca is None and prev and huellas[ticket] == prev['hash_contenido']:
                    marca = prev['modificacion_origen']
                if (prev and huellas[ticket] == prev['hash_contenido'] and
                    marca is not None and prev['modificacion_origen'] is not None):
                    marca = max(marca,prev['modificacion_origen'])
                conn.execute(text('''INSERT INTO galaxy_dw.etl_ticket_version
                    (numero_ticket,hash_contenido,ultimo_corte,modificacion_origen,lote_id)
                    VALUES (:ticket,:hash,:corte,:marca,:lote)
                    ON CONFLICT (numero_ticket) DO UPDATE SET
                    hash_contenido=EXCLUDED.hash_contenido,ultimo_corte=EXCLUDED.ultimo_corte,
                    modificacion_origen=EXCLUDED.modificacion_origen,lote_id=EXCLUDED.lote_id'''),
                    dict(ticket=ticket,hash=huellas[ticket],corte=corte,marca=marca,lote=lote))
            alertas = evaluar_corte(data.to_dict('records'),corte,lote)
            nuevas = 0
            for alerta in alertas:
                nuevas += conn.execute(text('''INSERT INTO galaxy_dw.alertas_operacionales
                    (numero_ticket,codigo_regla,fecha_corte,estado_observado,lote_id)
                    VALUES (:numero_ticket,:codigo_regla,:fecha_corte,:estado_observado,:lote_id)
                    ON CONFLICT (numero_ticket,codigo_regla,fecha_corte) DO NOTHING'''),asdict(alerta)).rowcount
            result = conn.execute(text('''UPDATE galaxy_dw.etl_lotes SET
                fecha_fin=clock_timestamp(),estado_ejecucion='COMPLETADO',
                filas_seleccionadas=:seleccionadas,filas_insertadas=:insertadas,
                filas_actualizadas=:actualizadas,filas_sin_cambios=:sin_cambios,
                alertas_detectadas=:detectadas,alertas_nuevas=:nuevas
                WHERE lote_id=:lote RETURNING *'''),
                dict(lote=lote,seleccionadas=len(data),detectadas=len(alertas),nuevas=nuevas,**counts)).mappings().one()
            return dict(result)
    except Exception as exc:
        if iniciado:
            codigo = 'CONFLICTO_VERSION' if isinstance(exc,ConflictoVersion) else ('ERROR_VALIDACION' if isinstance(exc,ValueError) else 'ERROR_TRANSACCION')
            with engine.begin() as conn:
                conn.execute(text("UPDATE galaxy_dw.etl_lotes SET estado_ejecucion='FALLIDO',fecha_fin=clock_timestamp(),error_codigo=:error WHERE lote_id=:id"),{'error':codigo,'id':lote})
        raise
    finally:
        if own_engine: engine.dispose()


def leer_archivo(ruta):
    path = Path(ruta)
    raw = path.read_bytes()  # Hash y parsing sobre exactamente los mismos bytes.
    if path.suffix.lower() in ('.xlsx','.xls'):
        data = pd.read_excel(io.BytesIO(raw),sheet_name='Sheet1',dtype={'Numero_ticket':'string'},keep_default_na=False)
    elif path.suffix.lower() == '.csv':
        for encoding in ('utf-8','latin-1','cp1252'):
            try:
                data = pd.read_csv(io.BytesIO(raw),sep=None,engine='python',encoding=encoding,
                                   dtype={'Numero_ticket':'string'},keep_default_na=False)
                break
            except (UnicodeDecodeError,pd.errors.ParserError):
                if encoding == 'cp1252': raise
    else: raise ValueError('Usar Excel o CSV')
    return data, hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description='Carga operacional auditada al corte de 05:30 Santiago')
    parser.add_argument('--excel',required=True)
    parser.add_argument('--fecha-corte',help='ISO con offset; debe ser 05:30 Santiago. Default: último corte efectivo.')
    parser.add_argument('--solapamiento-dias',type=int,default=7)
    parser.add_argument('--columna-modificacion',help='Columna REAL del origen, nunca creación ni ingesta')
    parser.add_argument('--completo',action='store_true',help='Reconciliación, sin filtrar modificación por ventana')
    parser.add_argument('--snapshot-confirmado-al-corte',action='store_true',help='Afirmación explícita de procedencia del snapshot; permite cambios sin versiones comparables solo en cortes posteriores')
    parser.add_argument('--lote-id')
    parser.add_argument('--dry-run',action='store_true')
    parser.add_argument('--truncate',action='store_true',help='Deshabilitado')
    args = parser.parse_args()
    if args.truncate: parser.error('--truncate está deshabilitado')
    config = ConfiguracionCorte(args.solapamiento_dias)
    corte = config.validar(datetime.fromisoformat(args.fecha_corte)) if args.fecha_corte else config.efectivo(datetime.now(timezone.utc))
    data, hash_archivo = leer_archivo(args.excel)
    if args.dry_run:
        data = etl.validar_entrada(data)
        selected,_ = seleccionar_incremental(data,corte,config,args.columna_modificacion,args.completo)
        print(json.dumps({'fecha_corte':corte.isoformat(),'ventana_desde':config.ventana(corte)[0].isoformat(),
                          'filas_recibidas':len(data),'filas_seleccionadas':len(selected),'sin_escrituras':True},ensure_ascii=True))
        return
    result = cargar_lote(data,fecha_corte=corte,archivo_origen=args.excel,hash_archivo=hash_archivo,
        lote_id=args.lote_id,config=config,snapshot_confirmado=args.snapshot_confirmado_al_corte,
        columna_modificacion=args.columna_modificacion,completo=args.completo)
    print(json.dumps(result,default=str,ensure_ascii=True))


if __name__ == '__main__': main()
