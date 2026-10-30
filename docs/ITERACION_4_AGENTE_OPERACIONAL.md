# Iteración 4 — Agente operacional de las 21:00

## Arquitectura y alcance

Agente Python determinista, sin LLM. Consulta directamente PostgreSQL operacional
sintético; no consulta el Data Warehouse ni utiliza las credenciales DB_* del ETL.
La inspección previa y la reutilización se documentan en
[componentes reutilizables](ITERACION_4_COMPONENTES_REUTILIZABLES.md).

Flujo: `fuente_operacional` → instantánea inmutable → `reporte_operacional` →
PNG, mensaje y JSON. `agente_reportabilidad` coordina el flujo y
`auditoria_reportes` conserva auditoría y evidencias en SQLite local independiente.
El único cambio compartido con el ETL es extraer el predicado `es_wip` de su
normalización existente; el contrato de estados y la regla de las 05:30 se conservan.

Ambos paneles y el mensaje muestran **tickets activos**: Pendiente, Abierto y
Work in Progress, separados en Incident y Service Request. Cerrado y Cancelado
se leen y auditan, pero se excluyen de estos conteos. Se conserva compatibilidad
con las normalizaciones históricas; no se agregan estados. El estado y las
observaciones originales permanecen intactos en el origen y la instantánea.
No se copian observaciones completas a los registros de auditoría.

Los componentes provienen de los datos. Incident usa salmón y Service Request
azul; WIP tiene borde/trama y etiqueta rojos. Un conjunto sin activos produce
un gráfico explícitamente vacío y un mensaje con ceros, únicamente después de
una consulta exitosa.

## Contrato de fuente y lectura histórica

[operacional.sql](../tests/fixtures/operacional.sql) crea solamente el origen
sintético `operacional.ticket_versiones`. Sus columnas son numero_ticket,
tipo_ticket, componente, estado, observaciones, fecha_creacion y
fecha_modificacion. La clave es (numero_ticket, fecha_modificacion); las fechas
son timestamptz y modificación no puede anteceder a creación.

La consulta parametrizada selecciona la última versión por ticket con creación
y modificación **menores o iguales** al corte. El índice y la clave hacen
determinista la selección. Una transacción REPEATABLE READ de solo lectura
obtiene todos los tickets una vez; no hay consultas separadas por gráfico.
La hora efectiva de observación proviene de PostgreSQL. El corte debe ser una
fecha consciente de zona horaria equivalente exactamente a las 21:00 en
America/Santiago; tzdata resuelve los cambios estacionales. Internamente los
identificadores de corte se normalizan a UTC.

Este adaptador necesita historial de versiones: una tabla que solo guarda el
estado actual no permite reconstruir por sí sola un corte pasado. No se ha
validado un esquema operacional real ni se ofrece una migración productiva.
No se crea ni modifica ningún objeto de Galaxy desde el agente.

## Evidencias, auditoría y reintentos

Solo WIP genera `WIP_EN_RESUMEN_2100`, distinta de WIP_EN_CORTE_0530.
No se exige antigüedad mínima ni se altera ningún ticket. SQLite registra el
ticket, estado literal, corte, hora real de observación y primera ejecución.
La unicidad es (fuente, ticket, regla, corte); los cortes siguientes conservan
su propio historial. La etiqueta fuente debe identificar establemente el mismo
origen, sin URL, datos personales ni secretos.

La huella de la instantánea incluye datos originales y corte, pero no la hora
de observación. Un reintento idéntico no duplica evidencias. Si el origen cambia
retroactivamente el contenido del mismo corte, se registra un conflicto y no
se reemplazan sus evidencias ni se publica un informe contradictorio.

Cada ejecución tiene UUID, corte, fuente, inicio/fin, cantidad leída, conteos,
WIP, huella, resultados de gráfico/mensaje y código de error. Una consulta
fallida deja cantidad leída NULL, estado FALLIDO y ningún informe publicado.
Los errores no incluyen excepciones crudas con credenciales. Las evidencias
de una lectura válida persisten aunque luego falle el renderizado.

Los tres artefactos se preparan en un directorio temporal y se publican juntos
mediante renombrado dentro del mismo directorio padre. Una excepción manejada
elimina únicamente la salida UUID de esa ejecución. SQLite y el sistema de
archivos no forman una transacción distribuida: un cierre abrupto entre el
renombrado y la auditoría puede dejar un directorio huérfano o una ejecución
INICIADO. La reconciliación automática de esos casos queda pendiente.
La auditoría local debe conservarse y respaldarse; borrarla pierde el historial
de idempotencia. El almacenamiento debe tener permisos restringidos.

## Dependencias y configuración

Python 3.10 o superior; instalar `requirements-test.txt` (incluye runtime).
Matplotlib se ejecuta con backend Agg y no requiere escritorio. PostgreSQL y
psycopg2/SQLAlchemy proveen el origen; SQLite pertenece a Python. Usar un usuario
operacional con SELECT solamente en una integración futura. Además de esa
restricción de permisos, el motor configura la transacción como read only,
timeout de conexión de 5 segundos y de consulta de 10 segundos.

Se exigen OP_DB_HOST, OP_DB_PORT, OP_DB_NAME, OP_DB_USER y OP_DB_PASSWORD.
No se lee .env, no hay contraseña predeterminada ni fallback a DB_*.
Configurar esos valores mediante el mecanismo de secretos del entorno; no
escribir contraseñas en comandos compartidos o archivos versionados.

Ejemplo de invocación, **solo con un origen sintético ya preparado**:

```powershell
python scr/agente_reportabilidad.py --corte 2025-03-06T21:00:00-03:00 --fuente-id mesa-sintetica --auditoria reportes_operacionales/auditoria.sqlite3 --salida reportes_operacionales/salidas
```

El comando devuelve JSON con UUID y directorio o un error y código de salida 1.
El directorio exitoso contiene reporte.png, mensaje.txt y datos_reporte.json.
No se programa ejecución ni se envían mensajes.

## Reproducción segura y ejemplos

```powershell
python -m pip install -r requirements-test.txt
python scripts/run_tests.py --postgres-bin C:/ruta/pgsql/bin
# Alternativa con Docker disponible:
python scripts/run_tests.py
```

El runner genera credenciales, puerto y bases temporales y detiene su propia
instancia al terminar. No lee .env ni utiliza Galaxy. La integración crea la
fuente desde el SQL sintético y usa un motor de lectura separado. El test de
CLI real exporta un ejemplo en test-results/iter4-ejemplo y el runner genera
test-results/junit.xml. Pytest directo sin TEST_PG_URL omite integración;
no equivale a ejecutar la batería completa.

El fixture contiene 20 tickets al corte: 18 activos, con Incident 11 pendientes,
2 abiertos y 1 WIP; Service Request 2 pendientes, 1 abierto y 1 WIP. Son valores
del escenario de prueba, nunca constantes del agente. Hay WIP posteriores a
las 05:30 y un cierre posterior a las 21:00 que no altera el corte histórico.
Los ejemplos publicados están en [examples/iteracion4](../examples/iteracion4).
Resultados reales y versiones: [evidencia de ejecución](ITERACION_4_RESULTADOS.md).

## Límites de esta entrega

Sin Luigi, WhatsApp, correo, Power Alert, modelos de lenguaje, reglas de dos
horas/tres días, despliegue o conexión productiva. No se cambió el fixture Excel
original. No se modificó main ni se realizó merge; PR #1 permanece en borrador.
El SQL operacional es una fuente descartable de pruebas, no un DDL autorizado
para producción. No se ejecutaron migraciones productivas ni --truncate.
