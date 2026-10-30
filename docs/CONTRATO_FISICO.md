# Contrato físico previo al cambio

Inspección: 29 de octubre de 2026. Fuentes: `01_schema_estrella.sql` y
`02_tablas_ml.sql` encontrados en Descargas del autor. Se conservan sin alterar
en `sql/baseline/`. Pendiente confirmar que coincidan con el DDL vigente;
no se consultó ni alteró la base Galaxy. Si difieren, se necesita el DDL real
antes de aplicar una migración allí.

## Tablas y claves requeridas

Se conserva el esquema `galaxy_dw` y sus once dimensiones. Las claves naturales
que usa ON CONFLICT requieren UNIQUE: dim_fecha(fecha_key),
dim_equipo(equipo_codigo), dim_sitio(sitio_nombre), dim_prioridad(prioridad),
dim_estado(estado), dim_clasificacion(clasificacion),
dim_falla_cierre(tipo_falla_cierre), dim_operador(operador_nombre),
dim_categoria_ticket(tipo_ticket,tipo_requerimiento),
dim_solicitud_falla(tipo_solicitud,tipo_falla), dim_apertura(modo_apertura,origen).
Todas conservan su PK y generación SERIAL, salvo fecha_key natural YYYYMMDD.

`fact_tickets.ticket_key` es BIGSERIAL PK; `numero_ticket` es INT NOT NULL UNIQUE.
La granularidad sigue siendo una fila por ticket. ON CONFLICT debe actualizar
la fila conservando ticket_key para no romper referencias de tablas ML.

Columnas del hecho: numero_ticket; fecha_creacion_key, fecha_respuesta_key,
fecha_cierre_key; ts_creacion, ts_respuesta, ts_cierre; equipo_key, sitio_key,
prioridad_key, estado_key, categoria_ticket_key, solicitud_falla_key,
falla_cierre_key, apertura_key, clasificacion_key, operador_apertura_key,
operador_cierre_key; asunto, nota_cierre, solucion; tiempo_abierto_min,
duracion_min y es_incidente. Las claves dimensionales mantienen sus FKs.
Texto libre y duracion_min ya admiten NULL; equipo/sitio son opcionales.

## Incompatibilidades demostradas por el fixture original

1. Identificadores `OPEN-001` y `CLOSED-001` no caben en INT. No se convertirán a
   enteros inventados ni se eliminará su prefijo. Se propone convertir únicamente
   numero_ticket a TEXT conservando su NOT NULL, UNIQUE y valores existentes.
2. Abiertos/pendientes no tienen respuesta ni cierre; en progreso sí tiene
   respuesta pero no cierre. Se propone permitir NULL en fecha_respuesta_key,
   fecha_cierre_key, ts_respuesta, ts_cierre, falla_cierre_key y operador_cierre_key.
3. Tiempo_abierto está ausente incluso en el ticket cerrado. Se propone permitir
   NULL en tiempo_abierto_min para conservar ausencia sin inferirlo de duracion_min.
4. Clasificación puede ser un bucket de duración final aún desconocido:
   clasificacion_key admite NULL cuando no viene en la fuente. No se inserta
   una categoría artificial. El fixture actual sí informa esta clasificación.

La migración propuesta no cambia PK, FKs, índices ni nombres. No añade tablas
de negocio ni valores centinela. Se ejecuta solamente en PostgreSQL descartable
durante los tests; nunca automáticamente desde el ETL ni sobre Galaxy.

## Reglas de entrada explícitas

- Creación y estado siempre requeridos. Respuesta y cierre no se sintetizan.
- Abierto, Pendiente, En progreso/En proceso permiten respuesta/cierre ausentes;
  no se acepta cierre informado mientras el estado continúe no terminal.
- Cerrado/Resuelto exigen cierre informado. Respuesta puede faltar también en
  un terminal: no hay regla previa que permita inventar ese evento.
- Estado desconocido o fechas no vacías inválidas provocan rechazo atómico.
- Campos de cierre, solución y duración final sin cierre son inconsistentes:
  rechazo, nunca borrado silencioso ni fabricación de cierre.
- Entrada es un snapshot completo por ticket, no un parche de campos. NULL
  explícito reemplaza el valor anterior (incluye reaperturas). No se borran
  tickets ausentes del archivo. Sin versión de origen, la última carga que
  obtiene el bloqueo transaccional gana; no hay protección frente a snapshots
  obsoletos. Es una limitación documentada, no una regla temporal inventada.
