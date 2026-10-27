# Postgres_ETL — Minera Galaxy

Pipeline Python que extrae tickets desde Excel o CSV, construye dimensiones y carga un modelo estrella en PostgreSQL, esquema `galaxy_dw`.

**Estado: implementación funcional según el autor, con pruebas de carga pendientes.** La revisión de preparación no ejecutó escrituras en la base. Los datos representan una minera ficticia y son sintéticos según declaración del autor.

## Alcance implementado

- Lectura de Excel (`Sheet1`) y CSV con detección de separador y alternativas de codificación.
- Conversión de fechas, comprobación de columnas y detección de tickets duplicados en el archivo.
- Construcción de once dimensiones y una tabla de hechos.
- Inserción de dimensiones con staging y `ON CONFLICT DO NOTHING`.
- Resolución de claves sustitutas a partir de PostgreSQL.
- Carga dentro de una transacción y logging con rotación.
- Filtro por rango, modo de inspección `--dry-run` y recarga destructiva de desarrollo `--truncate`.

## Arquitectura

```mermaid
flowchart LR
  F[Excel / CSV] --> E[Extracción y validación]
  E --> D[Dimensiones]
  D --> S[Staging y claves PostgreSQL]
  S --> H[Construcción de fact_tickets]
  H --> P[(galaxy_dw)]
  P --> A[Agente Minera Galaxy]
```

## Estructura

```text
scr/etl_original.py       CLI y etapas ETL
scr/db.py                 conexión SQLAlchemy
scr/logger.py             logging
scr/etl.ipynb             notebook exploratorio original
requirements.txt          lista original del entorno
requirements-runtime.txt  dependencias de ejecución complementadas
docs/                     arquitectura, pruebas y publicación
```

Se conserva el nombre existente `scr`. El notebook no se incluye en el paquete público preparado: requiere revisar código, salidas y metadatos antes de publicarlo.

## Instalación

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
```

Python 3.12 es el entorno local de referencia. Las dependencias no están fijadas como un entorno reproducible validado. `.xls` aparece aceptado en el código, pero requiere un motor adicional como xlrd, no incluido aquí; preferir `.xlsx` o CSV.

## Configuración

`scr/db.py` lee variables de entorno del proceso, **no carga `.env` automáticamente**. Configurarlas en la terminal antes de cargar datos:

```powershell
$env:DB_HOST = '127.0.0.1'
$env:DB_PORT = '5432'
$env:DB_NAME = 'Galaxy_mina'
$env:DB_USER = 'galaxy_etl'
$env:DB_PASSWORD = 'REEMPLAZAR_LOCALMENTE'
$env:LOG_TO_FILE = '0'
```

Se requiere un PostgreSQL existente con las tablas, constraints y claves correctas. Los scripts `sql/01_schema_estrella.sql` y `sql/02_tablas_ml.sql`, mencionados en el código, no están en la carpeta revisada. Tampoco hay Compose ni dump para recrearlo. No se debe presentar la instalación como reproducible de extremo a extremo hasta incorporar esos componentes.

## Ejecución segura inicial

```powershell
.venv\Scripts\python.exe scr/etl_original.py --excel examples/tickets_sinteticos.csv --dry-run
```

El ejemplo contiene filas ficticias creadas para demostración. `--dry-run` extrae datos y construye dimensiones; termina antes de conectar, construir la fact o verificar constraints. **Un dry-run exitoso no demuestra que la carga funcione.**

Para una base aislada de pruebas ya preparada:

```powershell
.venv\Scripts\python.exe scr/etl_original.py --excel examples/tickets_sinteticos.csv --desde 2025-03-01 --hasta 2025-03-31
```

Esta orden escribe y elimina previamente los hechos del rango indicado. Solo usar datos que cubran por completo el rango que se reemplaza. No ejecutar contra una base que se deba preservar.

## Limitaciones importantes

- Sin rango, la fact se agrega con append; repetir no garantiza idempotencia.
- Con rango, se borran todos los hechos del rango, aunque el archivo solo contenga una parte.
- El límite `--hasta` se compara a medianoche: registros posteriores a las 00:00 del último día pueden quedar fuera. Pendiente de corrección y pruebas.
- Fechas inválidas se convierten a NaT en extracción, pero al construir las claves enteras de la fact pueden causar error.
- La comprobación de columnas se realiza después de acceder a las fechas: una fecha ausente puede producir KeyError antes del mensaje de columnas faltantes.
- Staging usa tablas persistentes con nombres fijos, no tablas TEMP de sesión; no asumir seguridad para ejecuciones concurrentes.
- `--truncate` vacía dimensiones, hechos y cuatro tablas ML con CASCADE. No se ejecutó en esta revisión.
- El batch existente usa el entorno local `etl_venv` y está configurado en dry-run.

## Documentación

- [Modelo y contrato de entrada](docs/ARQUITECTURA.md)
- [Plan de pruebas](docs/PRUEBAS.md)
- [Preparación para GitHub](docs/PUBLICACION.md)

No se incluye una licencia de reutilización; elección pendiente del autor.
