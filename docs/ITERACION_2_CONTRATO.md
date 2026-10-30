# Contrato de iteración 2 (antes de implementación)

Base inspeccionada: commit 0e8582a de feature/etl-hardening-open-tickets, PR #1
abierto en borrador, sin merge. Se revisaron código, tests, DDL baseline y la
migración 03. No se inspeccionó ni modificó Galaxy real. El modelo se recrea
exclusivamente en PostgreSQL descartable para validar las migraciones.

## Nuevo modelo aditivo propuesto

- etl_lotes: UUID PK, inicio/fin/corte TIMESTAMPTZ, nombre y SHA256 de archivo,
  filas recibidas/insertadas/actualizadas/sin cambios, alertas detectadas,
  estado, error_codigo, ventana y política de conflictos. Inicio separado para
  registrar fallos; tickets, versiones, alertas y éxito de lote son atómicos.
- etl_ticket_version: numero_ticket TEXT PK/FK al hecho, huella del contenido,
  último corte observado TIMESTAMPTZ, modificación de origen TIMESTAMPTZ NULL,
  último lote FK. No se inventa modificación a partir de creación o ingesta.
- alertas_operacionales: ID BIGSERIAL, numero_ticket FK al hecho, regla, corte,
  estado original observado, primer lote FK y fecha de detección. UNIQUE en
  (numero_ticket, regla, fecha_corte). INSERT DO NOTHING conserva evidencia
  original; no se actualiza por cambios posteriores ni contiene notificación.

La migración 04 solo crea tablas, índices y constraints nuevas; no elimina
filas ni cambia columnas de negocio existentes. No se ejecuta desde el ETL.

## Contratos temporales y de actualización

El corte debe ser consciente de zona y corresponder exactamente a las 05:30
en America/Santiago. La ventana inicia siete días civiles antes (configurable),
conservando 05:30 local incluso si cambia el offset por horario de verano.

Una ventana es un contrato de extracción, no prueba de última modificación.
Si el archivo carece de marca de modificación, se procesan todas las filas
entregadas: nunca se descartan por antigüedad de creación. Si existe una
columna de modificación configurada, se filtra por esa columna y se conserva
su significado. Para actualizaciones fuera de ventana: reconciliación completa
periódica y extracción de tickets activos por el sistema origen; no se puede
garantizar recuperación desde Excel sin esa información.

Un snapshot contradictorio sin marca de modificación de origen se rechaza por
defecto (lote fallido, sin sobrescrituras). Se permite una política explícita de
snapshot confirmado al corte para fuentes que acreditan esa observación; exige
corte estrictamente posterior. Corte anterior o mismo corte contradictorio se
rechazan siempre. Marca real anterior o igual con contenido distinto se rechaza.
Si el contenido es idéntico, un reproceso antiguo no regresa el último corte.

## Separación de responsabilidades

WIP se conserva como fue recibido, se normaliza solo para evaluar regla
WIP_EN_CORTE_0530 y no bloquea el lote. En progreso/En proceso son alias
compatibles de WORK_IN_PROGRESS. La restricción preliminar de Cancelado fue
corregida en iteración 3: es legítimo y normaliza a CANCELADO, sin alerta WIP.
Ver ITERACION_3_CONTRATO_ESTADOS.md. No se agregan otros estados sin confirmación.

WIP >2h queda pendiente de una marca real de entrada al estado del sistema
operacional; no se usa creación, respuesta, duración ni Tiempo_abierto como
sustitutos. Abiertos >3 días queda pendiente de definición de abierto y trato
de pendientes/cancelados/suspendidos. No se implementan ambas reglas ahora.
