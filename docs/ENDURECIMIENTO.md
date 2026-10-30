# Endurecimiento del ETL

Se preservan once dimensiones, un hecho y sus nombres, claves y granularidad.
es_incidente sigue siendo Tipo_ticket == Incidente. Las dimensiones conservan
DO NOTHING; no se implementan nuevas reglas SCD. La propuesta física se
justifica en CONTRATO_FISICO.md y no se ejecuta automáticamente.

- Validación de columnas previa a fechas. Fecha no vacía inválida se rechaza;
  ISO no intercambia mes/día. Creación obligatoria, respuesta y cierre anulables.
- No hay fechas, soluciones, operadores ni duraciones finales imputados.
- Estado, secuencia de fechas y campos de cierre deben ser consistentes.
- Rango inclusivo: creación >= desde y creación < hasta + un día.
- Upsert por numero_ticket conserva ticket_key y no toca tablas ML.
- Staging TEMP ON COMMIT DROP con UUID y tipos del destino.
- Lock advisory transaccional serializa este ETL en la misma base; los clientes
  que no toman ese lock no quedan serializados. Se prioriza consistencia frente
  a paralelismo de escritura.
- Credenciales/destino explícitos. URL.create maneja caracteres reservados.
- Se rechaza --truncate y se elimina la función de borrado por período.
- Preflight detiene cargas a un modelo incompatible sin migrarlo.

## Semántica de actualización

Cada fila es un snapshot completo, no un parche de campos. NULL explícito
reemplaza el valor anterior y permite reaperturas. No se borran otros tickets.
Sin timestamp/versionado de origen no puede resolverse cuál snapshot es más
reciente: la última carga que toma el lock prevalece. No se promete protección
contra archivos fuera de orden.

El rango filtra fecha de creación, no de última actualización. Para actualizar
todos los snapshots recibidos de tickets antiguos, cargar sin --desde/--hasta.
Tiempo_abierto y duracion_min son campos distintos; no se infieren entre sí.
Un archivo inválido se rechaza atómicamente, sin descartes silenciosos.

## Modelo y consumidores

Cambiar numero_ticket de INT a TEXT exige revisar consumidores que lo traten
como número. PK, UNIQUE y FKs se conservan. Tablas ML referencian ticket_key:
no se rompe la referencia, pero una predicción antigua puede dejar de reflejar
el ticket actualizado. La política de recálculo no está en este alcance.

La migración sql/03_open_tickets.sql se ejecuta solo en pruebas descartables.
No aplicarla a Galaxy sin confirmar DDL vigente y revisar consumidores.
dry-run valida extracción/dimensiones; no sustituye integración de la fact.
