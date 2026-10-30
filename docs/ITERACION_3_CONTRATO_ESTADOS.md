# Iteración 3 — contrato de estados confirmado por operación

## Contrato vigente

| Estado recibido | Se carga/actualiza | WIP_EN_CORTE_0530 |
| --- | --- | --- |
| Cerrado | Sí, con integridad y versionado | No |
| Abierto | Sí, con integridad y versionado | No |
| Pendiente | Sí, con integridad y versionado | No |
| Cancelado | Sí, con integridad y versionado | No |
| Work in Progress | Sí, sin corregirlo ni bloquear el lote por ser WIP | Sí |

Todos son legítimos. Solo WORK_IN_PROGRESS normalizado genera la infracción
de entrega a las 05:30 America/Santiago. Normalizar para evaluar la regla no
reemplaza el valor original: dimensiones, hecho y evidencia conservan el texto
recibido, también espacios/capitalización dentro del tamaño físico existente.
No se deduce el estado desde observaciones o referencias a otros tickets.

## Cancelaciones y observaciones

Cancelado se reconoce expresamente como CANCELADO. No se trata como estado
desconocido, Pendiente, Cerrado ni Resuelto. No requiere fabricar fecha de cierre,
respuesta, solución, duración, operador o clasificación final. Los datos de
cierre pueden faltar; si vienen se conservan y deben respetar tipos y cronología.

Asunto, Nota_cierre y Solucion son campos TEXT del modelo existente. Se conservan
literalmente, incluyendo referencias a tickets relacionados, acentos, saltos de
línea y espacios internos. Para Cancelado se permiten notas y otros datos de
cancelación informados sin exigir una fecha de cierre ausente: una observación
no prueba ese evento. No se concatena, resume ni extrae una relación artificial.
No se ha incorporado una nueva columna de observaciones ni alterado el Excel.

Cerrado (y el histórico Resuelto) mantienen la validación de cierre y sus campos
obligatorios. Las validaciones anteriores de los demás estados se conservan.
Timestamps válidos, creación obligatoria, duraciones no negativas y claves
obligatorias continúan aplicando. Aceptar el estado no autoriza violar el
versionado: un snapshot contradictorio antiguo continúa siendo rechazado.

## Compatibilidad histórica analizada

No se incorporan más estados de negocio. Los valores preexistentes Resuelto y
Escalado, y los alias En progreso, En proceso, WIP y WORK_IN_PROGRESS, ya estaban
aceptados en la rama y en sus fixtures/tests. Se conservan para no romper cargas
históricas: Resuelto conserva semántica de cierre y los alias de WIP conservan
la misma alerta. Escalado no adquiere una regla operacional nueva. No se afirma
que esos nombres formen parte de los cinco estados actuales de operación.
Una eventual deprecación requiere análisis y autorización separados.

Suspendido, Reabierto, En revisión y otros estados no reconocidos no se
incorporan silenciosamente. Su correspondencia requiere autorización.

## Revisión técnica y modelo físico

- etl_original.py: añade categoría Cancelado y separa su integridad opcional
  de la obligación de cierre de Cerrado/Resuelto. No altera el texto fuente.
- alertas_operacionales.py: añade correspondencia CANCELADO; el único disparador
  sigue siendo WORK_IN_PROGRESS. No cambia la unicidad ticket/regla/corte.
- carga_operacional.py: revisado sin cambios: delega la validación, incluye los
  textos originales en la huella y evalúa el motor puro después de cargar.
  Se conservan transacción, auditoría, rechazo de versiones antiguas y política
  explícita de snapshots. Las alertas previas no se actualizan ni eliminan.
- dim_estado: VARCHAR(30), PK sustituta y UNIQUE(estado); no es un enum cerrado.
  Las dimensiones ya incorporan el estado literal por upsert. Se comprueba
  inserción/actualización real en PostgreSQL, sin migración nueva ni ALTER TABLE.

Los scripts SQL 03 y 04 solo se usan para recrear las bases descartables de tests.
Galaxy y main no se modifican. El PR #1 permanece en borrador, sin merge.

## Cambio de una expectativa anterior

La batería de iteración 2 contenía una prueba que exigía
normalizar_estado('Cancelado') == 'NO_CONFIRMADO'. Mantener esa expectativa sería
contradecir la regla confirmada por operación. Se reemplaza por el mismo caso
con resultado CANCELADO y nombre coherente; no se elimina cobertura. Las otras
99 pruebas anteriores permanecen sin cambios y se ejecutan con las nuevas.
Los JUnit históricos originales se conservan y no se reescriben como si hubieran
probado el contrato nuevo.

## Ejecutar y verificar

```powershell
python -m pip install -r requirements-test.txt
python scripts/run_tests.py
# Alternativa con PostgreSQL portátil, sin Docker
python scripts/run_tests.py --postgres-bin C:\ruta\pgsql\bin
```

El runner inicia su propia instancia y bases UUID, sin .env ni credenciales de
Galaxy. JUnit real en test-results/junit.xml. Resultados publicados en
ITERACION_3_RESULTADOS.md y ITERACION_3_JUNIT.xml; baseline en
ITERACION_3_BASELINE_JUNIT.xml. Ejemplo ejecutado en examples/estados_confirmados.json.
Luigi, el origen operacional y el despliegue productivo no se ejecutan aquí.
