# Iteración 4 — resultados ejecutados

Fecha local: 29 de octubre de 2026, America/Santiago.
Rama: feature/etl-hardening-open-tickets. Base: d9213b7.

## Batería real

Primera ejecución completa: 166 aprobadas y 12 errores al preparar el origen
nuevo. El operador SQL % del fixture se interpretaba como formato del driver
al usar exec_driver_sql con parámetros vacíos. Se corrigió el montaje del
fixture mediante SQLAlchemy text(), sin cambiar sus datos ni escenarios, y se
repitió toda la batería. Ese intento no se declara aprobado.

- Unitarias: **119 aprobadas**, 59 integraciones deseleccionadas en esa ejecución
  de enfoque; no se declararon allí aprobadas.
- Batería completa: **178 aprobadas, 0 fallidas, 0 omitidas**,
  **119 unitarias y 59 integraciones PostgreSQL**, 195.434 s según JUnit.
- Se conservan los 138 casos de iteración 3 y se ejecutan 40 nuevos
  (28 unitarios, 12 PostgreSQL). Ningún test anterior fue editado.
- JUnit: [ITERACION_4_JUNIT.xml](ITERACION_4_JUNIT.xml).

PostgreSQL **17.11 real descartable**, distribución portátil oficial, puerto y
contraseña aleatorios. El runner detuvo su instancia al terminar. Se crearon y
eliminaron únicamente bases UUID de prueba. Docker no se ejecutó.
El tiempo de inicialización del cluster no está incluido en el tiempo JUnit.

Entorno realmente usado: Python 3.12.5, pandas 3.0.6, SQLAlchemy 2.1.4,
psycopg2 2.9.13, openpyxl 3.1.5, pytest 9.2.0, Matplotlib 3.11.2,
NumPy 2.5.4 y tzdata 2026.6. Las dependencias adicionales se instalaron en
directorios de prueba del workspace; no se modificó el entorno del proyecto original.

Comando de batería: `python scripts/run_tests.py --postgres-bin <portatil>/pgsql/bin`.
Dependencias: `python -m pip install -r requirements-test.txt`.

## Evidencia por requisito

| Requisito | Casos ejecutados |
| --- | --- |
| Conteos y tipos | Instantánea SQL de 20 tickets; 18 activos, Incident 11/2/1 y Service Request 2/1/1 |
| Componentes dinámicos | Distribución exacta y componente nuevo insertado solo en base descartable |
| WIP exclusivamente | Cinco estados, alias históricos y estados cerrados/cancelados sin falsa alerta |
| Fuente preservada | Filas y observaciones antes/después iguales; escritura con motor lector rechazada por PostgreSQL |
| Una instantánea | Una consulta de tickets parametrizada; modificación posterior a lectura no cambia gráfico/mensaje |
| Gráfico y mensaje | Valores de barras iguales a matrices agregadas; CLI real y PNG válido |
| Error y recuperación | Puerto local sin servidor: auditoría FALLIDO con lectura NULL, sin salida; reintento válido completo |
| Idempotencia | Mismo corte en Santiago/UTC: mismos bytes PNG/TXT/JSON y dos evidencias originales sin duplicación |
| Historial | Dos cortes guardan cuatro evidencias; cierre posterior no borra las previas |
| Cambios después de 05:30 | Snapshot temprano sin WIP, corte 21:00 con WIP; fact DW vacía y nunca usada por lector |
| Sin activos | Lectura exitosa, gráfico válido vacío, cero alertas |
| Zona horaria | Offsets UTC equivalentes en verano/invierno; rechazo de fecha ingenua o corte distinto de 21:00 |
| Errores al generar | Sin publicación parcial; auditoría de etapa fallida y evidencia válida conservada |
| Contradicción histórica | Reintento del mismo corte con otra huella rechazado sin reemplazar evidencia |

## Artefacto realmente generado

La prueba de CLI ejecutó el agente contra PostgreSQL y exportó
[PNG](../examples/iteracion4/reporte.png),
[mensaje](../examples/iteracion4/mensaje.txt),
[datos](../examples/iteracion4/datos_reporte.json) y
[auditoría](../examples/iteracion4/auditoria.json).
WIP detectados: I-014 y SR-004. Regla: WIP_EN_RESUMEN_2100.
La auditoría contiene la hora efectiva de observación y el UUID de esa ejecución;
el corte histórico es 2025-03-06 21:00 America/Santiago. Su directorio temporal se
sustituyó por una etiqueta en la copia pública; no se publicaron secretos.
Los valores 11/2/1 pertenecen al fixture, no a la lógica de producción.

## Integridad y límites

Excel original idéntico byte a byte, SHA256
aa2da025cef3321cae8036cc94e44522a067d1f74c48e457ef74cce88528093a.
No se editaron scripts de migración previos ni el modelo físico de Galaxy.
El SQL nuevo crea exclusivamente la fuente sintética de pruebas.
El cambio compartido es el predicado es_wip, con regresión completa aprobada.

Sin conexión o cambios a Galaxy real, migración productiva, --truncate, merge
o modificación de main. PR #1 debe permanecer en borrador. No se ejecutaron
Luigi, WhatsApp, correo, Power Alert ni modelos de lenguaje. No se implementaron
reglas WIP >2 horas o abiertos >3 días. El adaptador real, su DDL y sus permisos
quedan pendientes; reconstruir cortes exige historial operacional.
Persistencia local SQLite y reconciliación ante apagados abruptos se describen
en [arquitectura](ITERACION_4_AGENTE_OPERACIONAL.md).
