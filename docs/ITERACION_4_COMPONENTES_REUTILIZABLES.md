# Inspección previa a implementación — iteración 4

Rama feature/etl-hardening-open-tickets, base d9213b7 (posterior a iteración 3).
PR #1 abierto en borrador, main intacto. Se revisaron normalización y motor de
alertas, configuración del corte, contrato físico y fixtures/tests PostgreSQL.
Los 138 resultados anteriores son históricos hasta reejecutar la batería final.

## Reutilización y separación

- normalizar_estado de alertas_operacionales.py: reutilizar sin cambiar las
  cinco correspondencias confirmadas ni los alias históricos. Compartir el
  predicado WIP para no duplicar su definición.
- ConfiguracionCorte: reutilizar la zona America/Santiago; su validador exige
  05:30 y NO debe llamarse para fingir un corte de 21:00. La regla nueva valida
  21:00 explícitamente y usa WIP_EN_RESUMEN_2100, sin alterar WIP_EN_CORTE_0530.
- db.get_engine, cargar_lote y tablas galaxy_dw NO son el origen del informe.
  Sus variables DB_* y sus escrituras sirven al ETL/DW. El lector operacional
  tendrá variables OP_DB_* independientes, sin .env ni defaults de credenciales,
  consultas parametrizadas y transacción REPEATABLE READ READ ONLY.
- Motor determinista y generadores reciben una sola instantánea inmutable.
  No hay llamadas a Anthropic/OpenAI ni ningún modelo de lenguaje.
- Runner PostgreSQL descartable y fixtures de regresión se reutilizan sin
  modificar el Excel original. El origen nuevo es operacional.ticket_versiones
  en una base UUID de prueba, no galaxy_dw. Sus versiones permiten recuperar
  estado al corte aunque existan cambios después de 05:30 o después de 21:00.

## Decisiones de persistencia y ámbito

Auditoría/evidencias se guardan en SQLite local separada de PostgreSQL origen.
Así todas las conexiones del agente a PostgreSQL pueden ser de solo lectura.
No se escriben etl_lotes ni las alertas del DW. SQLite impone unicidad por
fuente/ticket/regla/corte; los cortes se normalizan a UTC para comparar offsets.
Una instantánea contradictoria del mismo corte se rechaza, sin reemplazar la
evidencia previa. Las observaciones válidas permanecen como evidencia aunque
falle después el render: el fallo se registra, no se finge un informe válido.

Ambos gráficos y el mensaje resumen tickets ACTIVOS: Abierto, Pendiente y WIP.
Los cerrados/cancelados se leen en la instantánea pero no se incluyen en esos
conteos ni producen incumplimiento. Los componentes salen de los activos, sin
lista fija. Un origen vacío exitoso se diferencia de una consulta fallida.

Los binarios se producen primero en un directorio temporal y se publican solo
si gráfico, mensaje y datos de verificación se generaron. La publicación en
filesystem y la auditoría SQLite no constituyen una transacción distribuida:
un corte abrupto requiere reconciliar ejecuciones INICIADO. No hay despliegue,
scheduler, envíos reales, Power Alert ni reglas de antigüedad.
