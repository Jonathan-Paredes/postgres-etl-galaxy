# Postgres ETL — Minera Galaxy

Pipeline Excel/CSV a once dimensiones y un hecho en PostgreSQL, esquema
`galaxy_dw`. Soporta tickets abiertos, pendientes, en progreso y cerrados,
actualizando por Numero_ticket sin eliminar otros tickets del período.

## Revisar el modelo antes de cargar

Leer [contrato físico](docs/CONTRATO_FISICO.md). Los scripts originales del autor
se conservan en sql/baseline. Exigen cierre e identificadores INT; el fixture
usa OPEN-001 y datos de cierre ausentes. La [migración propuesta](sql/03_open_tickets.sql)
permite NULL en esos campos y convierte numero_ticket a TEXT conservando PK,
UNIQUE y FKs. **El ETL no aplica migraciones automáticamente.** No aplicarla a
Galaxy sin confirmar DDL vigente y revisar consumidores.

## Instalación

Python 3.12, dependencias de ejecución en requirements-runtime.txt y pruebas en
requirements-test.txt. Se conserva el directorio scr por compatibilidad.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-test.txt
```

## Comprobar sin conectar a PostgreSQL

```powershell
.venv\Scripts\python.exe scr/etl_original.py --excel tests/fixtures/galaxy_tickets_abiertos_pruebas.xlsx --dry-run
.venv\Scripts\python.exe -m pytest tests/test_unit.py -v
```

dry-run valida extracción y dimensiones, no prueba la fact ni el modelo físico.

## Cargar a una base autorizada y compatible

Definir las cinco variables DB_HOST, DB_PORT, DB_NAME, DB_USER y DB_PASSWORD.
No hay destino ni credenciales predeterminados; no se carga .env automáticamente.
.env.example es solo una plantilla. No registrar contraseñas en comandos compartidos.

```powershell
.venv\Scripts\python.exe scr/etl_original.py --excel tests/fixtures/galaxy_tickets_abiertos_pruebas.xlsx
```

El archivo es un snapshot completo por ticket: los NULL explícitos reemplazan
valores anteriores y permiten reaperturas. ON CONFLICT conserva ticket_key y
no modifica tablas ML. Sin versión de origen, la última carga que toma el lock
prevalece: no se pueden detectar snapshots fuera de orden.

--desde y --hasta filtran **creación**, incluyendo ambos días completos. No
borran períodos. Para actualizar tickets antiguos con cambios de estado, cargar
sus snapshots sin ese filtro. --truncate está deshabilitado.

## Integración con PostgreSQL descartable

```powershell
# Docker activo; postgres:17, puerto local aleatorio, sin volúmenes de Galaxy
.venv\Scripts\python.exe scripts/run_tests.py
# Alternativa: ZIP oficial PostgreSQL extraído, sin instalar un servicio
.venv\Scripts\python.exe scripts/run_tests.py --postgres-bin C:\ruta\pgsql\bin
```

Runner genera credenciales, instancia y bases UUID temporales; detiene únicamente
su propia instancia al terminar. No lee .env ni usa el destino Galaxy. Los tests
solo eliminan sus bases descartables. Resultados JUnit en test-results/junit.xml.
Sin TEST_PG_URL, pytest directo omite integración explícitamente; usar el runner
para ejecutarla. [Resultados realmente ejecutados](docs/RESULTADOS_HARDENING.md).

## Documentación

- [Contrato de entrada y modelo](docs/CONTRATO_FISICO.md)
- [Cambios, decisiones y limitaciones](docs/ENDURECIMIENTO.md)
- [Fixture original preservado](docs/FIXTURE.md)
- [Pruebas y comandos](docs/PRUEBAS.md)

Solo datos sintéticos. No se incluyen credenciales, dumps ni entornos virtuales.
El autor aún no ha seleccionado licencia de reutilización.
