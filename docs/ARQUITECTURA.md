# Arquitectura actual

Excel Sheet1 o CSV -> validación atómica del snapshot -> filtro de creación
opcional -> dimensiones -> TEMP staging -> inserción de dimensiones -> mapeos
naturales/sustitutos -> fact -> upsert por numero_ticket -> commit.

Se conserva galaxy_dw: dim_fecha, dim_equipo, dim_sitio, dim_prioridad,
dim_estado, dim_clasificacion, dim_falla_cierre, dim_categoria_ticket,
dim_solicitud_falla, dim_apertura, dim_operador y fact_tickets.
El contrato detallado está en CONTRATO_FISICO.md y el DDL en sql/baseline.

Respuesta/cierre y sus claves son anulables; tiempo_abierto puede faltar.
Creación y las dimensiones de apertura siguen siendo obligatorias. No se
generan fechas centinela ni operadores ficticios. El cierre informado se
valida contra el estado y la secuencia temporal.

El motor valida el esquema antes de escribir. La transacción toma un lock
advisory para serializar este ETL; staging UUID es temporal y local a la sesión.
Upsert conserva ticket_key para no romper referencias de predicciones ML.
No actualiza predicciones; pueden requerir recálculo tras cambiar el ticket.

El agente sigue consultando las mismas tablas. Debe revisarse por separado
que sus consumidores manejen numero_ticket como texto y fechas nulas.
