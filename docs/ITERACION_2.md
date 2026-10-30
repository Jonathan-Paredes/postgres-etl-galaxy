# Iteración 2: corte, auditoría y evidencia operacional

## Ejecución diaria y extracción

El contrato del cliente es 05:30 America/Santiago, con siete días civiles de
solapamiento por defecto. ConfiguracionCorte permite cambiar el solapamiento y
calcula el último corte efectivo a partir de una referencia consciente de zona.
Las 05:30 locales se conservan con cambios de horario de verano; siete días no
siempre equivalen a 168 horas UTC. No se instala Luigi ni ningún scheduler.

Un futuro task Luigi debe obtener el plan con ConfiguracionCorte.ventana(corte),
pedir al origen datos modificados dentro de esa ventana y pasar el archivo y el
mismo corte al cargador. Programar la tarea en Santiago es responsabilidad del
scheduler; retrasar la ejecución no cambia la hora efectiva del corte declarado.

Con --columna-modificacion se usa una columna REAL adicional al contrato Excel;
sus valores deben ser ISO o timestamps inequívocos. Sin offset significan hora
Santiago; horas ambiguas/inexistentes se rechazan. No se permiten creación,
respuesta, cierre ni otras columnas de negocio como sustitutos. Modificación
posterior al corte o anterior a creación se rechaza. La ventana incluye ambos
instantes límite; --completo no aplica el límite inferior, pero sí el corte.

Sin marca de origen se procesan TODAS las filas del archivo, incluso tickets
creados hace años. La ventana se registra como contrato para extracción, no se
fabrica una fecha de modificación ni se filtra por creación. Recuperación de
cambios antiguos fuera de ventana requiere reconciliación completa periódica
y/o extracción de tickets activos desde el origen. El Excel por sí solo no
garantiza que esos tickets lleguen. El modo completo permite procesarlos.

## Reglas y estados

alertas_operacionales.py es un motor puro: recibe registros y devuelve
incumplimientos. WIP_EN_CORTE_0530 se evalúa solo en un corte válido y no depende
de duración, fecha de respuesta ni tiempo abierto. Work in Progress, WIP,
WORK_IN_PROGRESS, En progreso y En proceso normalizan a WORK_IN_PROGRESS;
el estado guardado en la dimensión/hecho y la evidencia conservan el texto
original. No se cambia WIP por Pendiente y no se bloquea el lote por esta regla.

Contrato corregido por operación en iteración 3: Cerrado, Abierto, Pendiente,
Cancelado y Work in Progress son estados legítimos. Solo Work in Progress
dispara WIP_EN_CORTE_0530; los otros cuatro no generan esa alerta. Se conserva
literalmente el estado y las observaciones. Cancelado ya no se rechaza como
desconocido ni exige inventar cierre para conservar una nota. Ver
[contrato definitivo](ITERACION_3_CONTRATO_ESTADOS.md).
Los valores y alias históricos previamente aceptados conservan compatibilidad;
Suspendido y otros estados no confirmados no se agregan silenciosamente.

WIP superior a dos horas NO está implementado: requiere una marca verificable
de entrada a WIP del sistema operacional. Creación, respuesta, duración final
y Tiempo_abierto no la sustituyen. El test de 5/180 minutos es un escenario
sintético de independencia de duración, no un cálculo del Excel histórico.

Abiertos más de tres días NO está implementado: falta definir estados abiertos,
pendientes, cancelados y suspendidos, y sus reglas temporales. Pertenece al
futuro módulo de consultas, separado de WIP al corte.

## Política contra sobrescritura de versiones

Cada fila sigue siendo un snapshot completo; NULL explícito tiene significado.
Se calcula una huella de los 24 campos de negocio, independiente de ingesta.

| Situación | Política |
| --- | --- |
| Ticket nuevo | Insertar y registrar versión observada |
| Misma huella | Sin cambio; nunca retroceder corte ni marca real conocida |
| Distinta huella y corte anterior/igual | Rechazar el lote con CONFLICTO_VERSION |
| Distinta huella, corte posterior y dos marcas reales comparables | Exigir modificación de origen estrictamente mayor |
| Distinta huella sin dos marcas comparables | Rechazar por defecto |
| Snapshot acreditado explícitamente al corte | --snapshot-confirmado-al-corte permite cambio solo si corte es posterior; no anula marcas reales atrasadas |
| Ticket legado sin trazabilidad | Requiere bootstrap explícito con snapshot confirmado |

La confirmación es una afirmación de procedencia hecha por el operador/origen,
no algo que el ETL deduzca de la hora de llegada ni del nombre del archivo. No
usar ese flag para etiquetar un archivo antiguo como nuevo. La política de
rechazo evita silencios: no descarta solo una fila, falla el lote sin cambios.
Una corrección contradictoria del mismo corte requiere reconciliación explícita
fuera de este flujo; no se sobrescribe la evidencia anterior automáticamente.

## Transacción, lotes y alertas

Migración 04 crea etl_lotes, etl_ticket_version y alertas_operacionales. Ver
ITERACION_2_CONTRATO.md y sql/04_lotes_alertas.sql; no cambia las tablas de negocio.
No se aplica desde el cargador ni sobre Galaxy durante las pruebas.

1. Se verifica el modelo y registra lote INICIADO en una transacción breve.
2. Bajo el mismo advisory lock del ETL anterior se validan y comparan versiones.
3. Dimensiones, hechos, versiones, alertas y lote COMPLETADO se confirman juntos.
4. Si falla, se revierten todas esas escrituras y el lote pasa a FALLIDO con
   error_codigo y contadores de escrituras comprometidas en cero.

Fecha de inicio/fin y detección se obtienen del servidor de pruebas; el corte
es el efectivo declarado. Ninguna es fecha de modificación del ticket. El hash
de archivo se calcula sobre los mismos bytes usados al parsear el archivo.
Contadores: recibidas = filas leídas; seleccionadas = después de la ventana;
insertadas/actualizadas/sin cambios suman seleccionadas en lotes completados.
alertas_detectadas cuenta los incumplimientos evaluados; alertas_nuevas solo
las evidencias insertadas. Repetir el corte puede detectar de nuevo sin duplicar.

UNIQUE(numero_ticket,codigo_regla,fecha_corte) evita duplicar evidencia, y permite
otra en cada día. ON CONFLICT DO NOTHING conserva primer lote, texto y detección.
No se borran alertas al cerrar el ticket. No existe estado de WhatsApp,
notificación, acuse ni seguimiento en esa tabla: debe vivir separado en el futuro.

Reusar lote_id con el mismo contrato completado devuelve su resultado sin volver
a escribir. Un lote INICIADO/FALLIDO exige reconciliar y usar otro UUID; no se
declara exitoso. Un proceso abruptamente interrumpido puede dejar INICIADO y
requiere recuperación operacional. Errores al abrir archivo o antes del preflight
no pueden registrarse en ese almacenamiento y deben ser recogidos por el caller.

La API histórica cargar se conserva para reproducir los 52 tests originales en
un esquema de iteración 1; se bloquea si detecta etl_lotes. La CLI original
etl_original.py ahora delega al flujo auditado y ya no acepta --desde/--hasta:
esos argumentos filtraban creación y no representan el nuevo incremental.

No hay triggers de auditoría de modificaciones hechas con SQL externo: todos
los escritores operacionales deben usar el flujo auditado. No se ha configurado
un rol append-only ni probado el esquema real de Galaxy. Las predicciones ML
mantienen sus FKs pero no se recalculan ni se versionan automáticamente.

## Ejecución local sin Galaxy

```powershell
python -m pip install -r requirements-test.txt
python scripts/run_tests.py
# Alternativa sin Docker: binarios PostgreSQL portátiles ya extraídos
python scripts/run_tests.py --postgres-bin C:\ruta\pgsql\bin
```

El runner genera credenciales, cluster, puerto y bases UUID descartables. Nunca
lee .env ni usa el destino Galaxy. Aplícación 04 en cada fixture de integración
solo después del baseline y 03. Test-results/junit.xml contiene resultado real.

```powershell
# Previsualización pura, sin base ni auditoría persistida
python scr/etl_original.py --excel tests/fixtures/galaxy_tickets_abiertos_pruebas.xlsx --fecha-corte 2025-03-06T05:30:00-03:00 --dry-run
```

En un destino de PRUEBAS preparado explícitamente con baseline, 03 y 04,
definir DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD sin valores predeterminados:

```powershell
python scr/carga_operacional.py --excel archivo_sintetico.xlsx --fecha-corte 2025-03-06T05:30:00-03:00
# Fuente que acredita su snapshot al corte (NO usar por simple orden de llegada)
python scr/carga_operacional.py --excel snapshot_confirmado.xlsx --fecha-corte 2025-03-07T05:30:00-03:00 --snapshot-confirmado-al-corte
# Solo si la fuente incorpora esa marca real, no la inventa el ETL
python scr/carga_operacional.py --excel con_modificacion.xlsx --fecha-corte 2025-03-07T05:30:00-03:00 --columna-modificacion Fecha_modificacion_origen --solapamiento-dias 7
```

Consulta de evidencia (solo lectura):

```sql
SELECT numero_ticket, codigo_regla,
       fecha_corte AT TIME ZONE 'America/Santiago' AS corte_local,
       estado_observado, lote_id, fecha_deteccion
FROM galaxy_dw.alertas_operacionales
ORDER BY fecha_corte, numero_ticket;
```

Ejemplo ejecutado: examples/alertas_corte_0530.json. Resultados y matriz de los
13 escenarios obligatorios en ITERACION_2_RESULTADOS.md. No se instaló Luigi,
FastAPI ni ningún servicio de notificaciones; no hay merge ni despliegue.
