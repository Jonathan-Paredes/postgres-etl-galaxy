# Postgres ETL — Minera Galaxy

Pipeline Excel/CSV a once dimensiones y un hecho en PostgreSQL, esquema
`galaxy_dw`. Soporta tickets abiertos, pendientes, en progreso y cerrados,
actualizando por Numero_ticket sin eliminar otros tickets del período.

## Iteración 3: cinco estados confirmados

Cerrado, Abierto, Pendiente, Cancelado y Work in Progress son legítimos y se
conservan literalmente. Solo WIP genera WIP_EN_CORTE_0530; no bloquea el lote ni
se convierte a otro estado. Cancelado conserva observaciones y referencias sin
inventar cierre. No cambian versionado, idempotencia ni alertas históricas.

[Contrato definitivo y compatibilidad](docs/ITERACION_3_CONTRATO_ESTADOS.md) ·
[Resultados JUnit ejecutados](docs/ITERACION_3_RESULTADOS.md).

## Iteración 2: flujo operacional auditado

La CLI ahora usa cortes a las **05:30 America/Santiago**, solapamiento configurable
de siete días, lotes auditados, control de versiones y alertas WIP históricas sin
alterar tickets. Requiere la migración **aditiva 04**, además de 03, solo tras revisión.
No se aplica automáticamente a Galaxy.

[Contrato, políticas y ejecución local](docs/ITERACION_2.md) ·
[Resultados ejecutados](docs/ITERACION_2_RESULTADOS.md).

Los ejemplos históricos de carga sin fecha-corte usan ahora el último corte
efectivo; para reproducibilidad pasar --fecha-corte con offset. La carga auditada
rechaza por defecto cambios contradictorios sin evidencia temporal. No se usa
creación como modificación ni se corrige WIP a Pendiente. Sin marca de origen,
se procesan todas las filas entregadas; la extracción debe garantizar su cobertura.

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
.venv\Scripts\python.exe -m pytest -m "not integration" -v
```

dry-run valida entrada y plan de extracción; no prueba conflictos contra la base,
la fact, la persistencia de auditoría ni el modelo físico.

## Cargar a una base autorizada y compatible

Definir las cinco variables DB_HOST, DB_PORT, DB_NAME, DB_USER y DB_PASSWORD.
No hay destino ni credenciales predeterminados; no se carga .env automáticamente.
.env.example es solo una plantilla. No registrar contraseñas en comandos compartidos.

```powershell
.venv\Scripts\python.exe scr/etl_original.py --excel tests/fixtures/galaxy_tickets_abiertos_pruebas.xlsx
```

El archivo es un snapshot completo por ticket: los NULL explícitos reemplazan
valores anteriores y permiten reaperturas. ON CONFLICT conserva ticket_key y
no modifica tablas ML. En el flujo operacional se usa la huella y evidencia de corte/modificación;
los snapshots contradictorios sin evidencia suficiente se rechazan.

La CLI operacional no acepta --desde/--hasta porque filtraban creación.
Usar --columna-modificacion únicamente con marca real adicional del origen;
sin ella no se filtra el archivo por antigüedad. --truncate está deshabilitado.

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
para ejecutarla. [Resultados realmente ejecutados](docs/ITERACION_2_RESULTADOS.md).

## Documentación

- [Agente operacional de las 21:00 — Iteración 4](docs/ITERACION_4_AGENTE_OPERACIONAL.md)
- [Contrato de entrada y modelo](docs/CONTRATO_FISICO.md)
- [Cambios, decisiones y limitaciones](docs/ENDURECIMIENTO.md)
- [Fixture original preservado](docs/FIXTURE.md)
- [Pruebas y comandos](docs/PRUEBAS.md)

Solo datos sintéticos. No se incluyen credenciales, dumps ni entornos virtuales.
El autor aún no ha seleccionado licencia de reutilización.
