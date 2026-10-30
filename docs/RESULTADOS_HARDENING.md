# Resultados ejecutados — ETL abierto/cerrado

Fecha local: 29 de octubre de 2026. Rama feature/etl-hardening-open-tickets.

## Resultado final

**52 aprobadas, 0 fallidas, 0 omitidas:** 41 unitarias y 11 de integración con
PostgreSQL 17.11 real, en instancia portátil descartable. Código de salida 0.
Pytest reportó 27,57 segundos para la batería (no incluye inicialización del
cluster). JUnit adjunto en HARDENING_JUNIT.xml y hashes en HARDENING_MANIFEST.json.

Comando del repositorio:

```text
python scripts/run_tests.py --postgres-bin <directorio-portatil>/pgsql/bin
```

Se usó Python 3.12.5 con dependencias del entorno local del ETL y pytest instalado
en un directorio separado del workspace (PYTHONPATH); no se modificó el entorno
original. Versiones realmente utilizadas:

- pandas: 3.0.6
- SQLAlchemy: 2.1.4
- psycopg2: 2.9.13
- openpyxl: 3.1.5
- pytest: 9.2.0

## Aislamiento

Docker no estaba disponible. Se usó el ZIP oficial PostgreSQL para Windows,
distribuido por EDB y enlazado desde la [página de PostgreSQL](https://www.postgresql.org/download/windows/).
Fuente binaria: https://get.enterprisedb.com/postgresql/postgresql-17.11-3-windows-x64-binaries.zip.
El runner creó su propio cluster temporal, puerto local aleatorio, credenciales
generadas y una base UUID nueva por prueba de integración. Esas bases se
eliminaron y el cluster se detuvo al terminar; la carpeta temporal se limpió.
No se leyó .env ni se conectó a la Galaxy existente. No se ejecutó --truncate.

## Evidencia funcional

- El fixture original se cargó con sus 4 tickets y 2 hojas intactas.
- Tres tickets no terminales conservaron cierre, solución y duración final NULL.
- OPEN-002 conservó su respuesta; CLOSED-001 conservó cierre y duración 60.
- Tiempo_abierto siguió NULL en las cuatro filas, sin sustituirlo por duración.
- Repetir el fixture conservó exactamente filas, PK y valores.
- Actualizar OPEN-001 a cerrado y luego reabrir conservó ticket_key y una FK ML.
- Carga parcial del período no borró los otros tres tickets.
- Se incluyó un ticket creado a las 23:59:59.999999 del último día.
- Fallo inducido después de dimensiones revirtió datos y staging.
- Dos cargas iguales y dos cargas distintas concurrentes no mezclaron filas.
- Un abierto sin equipo, sitio ni clasificación conservó las claves NULL.
- El DDL original incompatible fue rechazado antes de escribir dimensiones.
- Migrar un identificador numérico existente conservó su valor y ticket_key.

## Ejecuciones previas y corrección

Primera ejecución unitaria: 33 aprobadas y 1 fallida por preparación incorrecta
del caso que insertaba texto inválido en una serie datetime. Se corrigió el test.
Primera integración: 40 aprobadas y 3 fallidas por merges con tipos distintos
cuando una carga tenía solo campos de cierre nulos. Se corrigió normalizando
claves naturales como string anulable tanto en fuente como en mapeos. Se amplió
la cobertura y la ejecución final completa dio las 52 aprobadas indicadas arriba.

También se ejecutó CLI --dry-run con el Excel original: salida 0, cuatro filas
y once dimensiones; sin conexión PostgreSQL. git diff --check sin errores.

## Límites pendientes

No se ejecutó el modo Docker, ni migración en Galaxy, ni integración con sus
consumidores. El DDL encontrado está conservado como baseline y la migración
es propuesta: confirmar versión instalada antes de cualquier despliegue.
Snapshots completos sin versión: el último en tomar el lock prevalece; no hay
historial de cada modificación ni protección contra archivos obsoletos.
Las predicciones ML referenciadas no se recalculan automáticamente.
