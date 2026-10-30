# Iteración 2 — resultados e integridad

Fecha: 29 de octubre de 2026 (America/Santiago). Rama
feature/etl-hardening-open-tickets. PR #1 continúa en borrador; no hay merge.

## Ejecuciones reales

1. Antes de modificar el código: **52 aprobadas**, 0 fallidas, 0 omitidas,
   PostgreSQL 17.11 portátil descartable; 29,24 s de pytest. Evidencia en
   ITERACION_2_BASELINE_JUNIT.xml.
2. Primera batería ampliada: **96 aprobadas**, 0 fallidas, 0 omitidas;
   65,15 s. Después se añadieron la prohibición explícita de usar creación como
   modificación, trazabilidad del nombre de columna de origen y coherencia de
   modificación respecto de creación.
3. Batería final: **100 aprobadas**, 0 fallidas, 0 omitidas; **69 unitarias y
   31 integración PostgreSQL real**, 69,89 s de pytest. Contiene los mismos
   52 tests anteriores y 48 nuevos. Evidencia en ITERACION_2_JUNIT.xml.

El tiempo de inicialización del cluster está fuera de esos tiempos. Entorno:
Python 3.12.5, pandas 3.0.6, SQLAlchemy 2.1.4, psycopg2 2.9.13, openpyxl 3.1.5,
pytest 9.2.0. Comando del repositorio:

```text
python scripts/run_tests.py --postgres-bin <directorio-portatil>/pgsql/bin
```

Se ejecutó también el dry-run de la CLI original (ahora flujo operacional), con
corte 2025-03-06T05:30:00-03:00: cuatro recibidas, cuatro seleccionadas, ventana
desde 2025-02-27T05:30:00-03:00, salida 0 y sin escrituras. git diff --check sin
errores. El fixture Excel original sigue idéntico byte a byte, incluidas sus hojas.

## Matriz obligatoria (todos aprobados)

| # | Escenario | Test PostgreSQL ejecutado |
| --- | --- | --- |
| 1 | Pendiente sin WIP | test_pendiente_y_cerrado_sin_alerta[2] |
| 2 | Cerrado sin WIP | test_pendiente_y_cerrado_sin_alerta[3] |
| 3 | WIP cinco minutos | test_wip_cinco_minutos_o_tres_horas_misma_regla[5] |
| 4 | WIP tres horas | test_wip_cinco_minutos_o_tres_horas_misma_regla[180] |
| 5 | WIP no bloquea lote | test_wip_no_bloquea_resto |
| 6 | WIP conserva texto original | test_wip_cinco_minutos_o_tres_horas_misma_regla[5] |
| 7 | Mismo corte sin duplicado | test_reprocesar_mismo_corte_sin_duplicados |
| 8 | Días distintos conservan evidencia | test_dias_distintos_evidencia_historica |
| 9 | Cerrar conserva evidencia WIP | test_wip_luego_cerrado_conserva_evidencia |
| 10 | Límite inclusivo de siete días | test_siete_dias_borde_y_ticket_antiguo_recibido |
| 11 | Carga parcial no elimina otros | test_carga_parcial_preserva_otros |
| 12 | Archivo antiguo no sobrescribe | test_archivo_antiguo_no_sobrescribe |
| 13 | Rollback datos/lotes/alertas | test_rollback_integral_ante_fallo_alertas |

Además: versiones de origen comparables, bloqueo de cambios sin evidencia,
UUID de lote idempotente, eventos futuros rechazados, protección contra bypass
histórico, reconciliación completa, marcas que no retroceden y modificación
anterior a creación. Unitarias incluyen DST de Santiago, normalización sin
modificar original, y marca real separada de creación/respuesta/cierre.

## Integridad e idempotencia

- Lote final COMPLETADO se confirma junto con tickets, versiones y alertas.
- Fallo inducido después de escribir el hecho y antes de alertas: hecho,
  versiones y alertas revertidos; lote FALLIDO conservado con fin y contadores
  comprometidos en cero. Ese registro de fallo es intencional, no una alerta huérfana.
- Repetir corte detecta WIP pero agrega cero evidencias nuevas; UNIQUE protege
  por ticket/regla/corte y conserva primer lote/estado/detección.
- Corte diferente permite nueva evidencia; cerrar después no borra la anterior.
- Cargas parciales conservan filas no incluidas; siguen vigentes PK y FKs ML.
- Archivos contradictorios más antiguos o del mismo corte son rechazados;
  tampoco se acepta el simple orden de llegada con corte posterior sin evidencia.
- Se usa un snapshot completo por ticket, no actualizaciones parciales de campos.

Ejemplo ejecutado en examples/alertas_corte_0530.json: cuatro tickets cargados y
dos alertas (Work in Progress y En progreso), con UUID, corte y detección reales
del servidor de pruebas. El archivo origen del ejemplo es un nombre sintético de
test; el test opera con DataFrame y huella de su serialización. La CLI de archivos
sí calcula SHA256 sobre exactamente los bytes que parsea (prueba unitaria ejecutada).

## Archivos y justificación

| Archivo | Cambio |
| --- | --- |
| scr/corte_operacional.py | Configuración 05:30 Santiago, solapamiento y DST, sin Luigi |
| scr/alertas_operacionales.py | Regla determinista WIP independiente del ETL |
| scr/carga_operacional.py | Carga auditada, selección incremental y conflictos de versiones |
| scr/etl_original.py | Admite WIP original; CLI delega; impide bypass si hay tablas de auditoría |
| sql/04_lotes_alertas.sql | Migración aditiva de lotes, versiones y evidencia |
| tests/test_operacional_unit.py | Casos de reglas, ventana, marcas y configuración |
| tests/test_operacional_postgres.py | Integración de los trece escenarios y protecciones adicionales |
| requirements-runtime.txt | tzdata para ZoneInfo en Windows |
| docs/ITERACION_2*.md y XML | Contrato previo, políticas y resultados ejecutados |
| README y documentos históricos | Enlaces y distinción entre política histórica y operacional |
| examples/alertas_corte_0530.json | Ejemplo producido por PostgreSQL descartable |

## Límites pendientes

- No se modificó Galaxy, main ni se ejecutó --truncate. Migraciones solo en
  bases UUID del cluster descartable, detenido y limpiado al terminar.
- No se probó Docker en esta ejecución ni un scheduler Luigi real, el origen
  operacional, Power BI, agentes LLM o notificaciones. No se añadieron esas APIs.
- La cobertura del origen no está garantizada por un Excel: recuperación fuera
  de ventana requiere extracción de tickets activos y reconciliación completa.
- Snapshot confirmado es una declaración explícita del operador, no una firma
  ni prueba automática de autenticidad. No usarlo para renombrar archivos antiguos.
- Solo se guarda la última versión aceptada del ticket; no se añadió historial
  completo de cada campo. Las alertas sí son evidencia histórica independiente.
- Estados sin correspondencia, WIP >2h y abiertos >3 días requieren definición
  y datos adicionales. No se calculan a partir de marcas sustitutas.
- Un proceso interrumpido puede dejar INICIADO: requiere recuperación manual.
  Errores al abrir archivo/preflight quedan fuera del registro SQL de ejecución.
- No se configuraron roles append-only ni auditoría por triggers de SQL externo.
  Todos los escritores operacionales deben usar la vía auditada.
- Los resultados y hashes de HARDENING_* son históricos de iteración 1; el
  manifiesto actual es ITERACION_2_MANIFEST.json (contenido Git, LF para código).

Para reproducir y consultar evidencia: ver ITERACION_2.md. No ejecutar las
migraciones contra una base existente sin revisar y autorizar ese despliegue.
