# Pruebas del ETL

La batería actual usa el fixture Excel original sin editar y DDL original más
migración propuesta, solo en PostgreSQL descartable. Estado y conteos ejecutados
en RESULTADOS_HARDENING.md. No declarar integración aprobada si pytest la omite.

## Unitarias

python -m pytest tests/test_unit.py -v

Columnas antes de fechas, estados, blancos, datos no parseables, nulos legítimos,
secuencia temporal, cierre no inventado, duplicados, límite inclusivo,
credenciales obligatorias, contraseñas con caracteres reservados y dry-run sin DB.

## PostgreSQL real

python scripts/run_tests.py

O usar --postgres-bin apuntando a los binarios PostgreSQL portátiles oficiales.
No usa una DB de negocio. Cada caso crea una DB UUID nueva desde template1,
aplica baseline y la migración cuando corresponde, y elimina solo esa DB.
Guardia: TEST_PG_URL debe indicar etl_test_control en localhost; el runner genera
la instancia y credenciales. No establecer esa variable hacia un servidor real.

Prueba DDL incompatible sin escrituras, carga de abiertos/cerrados, repetición
idempotente, cambio de estado y reapertura conservando PK y referencias ML,
carga parcial sin pérdida del período, último día con hora, rollback después
de dimensiones, concurrencia y migración preservando identificadores numéricos.

Nunca se llama --truncate. Las variantes se crean en memoria, sin reescribir el
fixture. Los resultados no prueban que el DDL de Galaxy instalado coincida con
los scripts encontrados; esa verificación permanece separada.
