# Plan de pruebas del ETL

Las verificaciones ejecutadas se registran en VALIDACION.md. La siguiente matriz es trabajo pendiente; no implica aprobación.

| Nivel | Caso | Resultado esperado |
| --- | --- | --- |
| Extracción | CSV UTF-8 y punto y coma; Excel Sheet1 | Mismas filas y tipos de fecha |
| Extracción | Duplicados por Numero_ticket | Rechazo explícito |
| Extracción | Columna ausente, fecha inválida y archivo inexistente | Error controlado y explicativo |
| Transformación | Dimensiones repetidas, claves compuestas y operadores | Valores únicos y mapeo correcto |
| Transformación | Fechas nulas y equipo/sitio ausentes | Política definida y comprobada |
| Rango | Último día a 00:00, 12:00 y 23:59 | Incluir todo el día final; fallo conocido a corregir |
| Carga aislada | Primera carga | Filas esperadas y claves válidas |
| Carga aislada | Repetir el mismo rango completo | Sin duplicados y mismos conteos |
| Carga aislada | Repetir sin rango | Evidenciar duplicados o conflicto según constraints |
| Carga aislada | Archivo parcial para un rango existente | Evitar pérdida involuntaria: definir estrategia |
| Transacción | Fallo inducido después de dimensiones | Estado previo preservado por rollback |
| Concurrencia | Dos cargas simultáneas | Evidenciar colisión de staging y definir solución |
| Desarrollo aislado | truncate con tablas ML | Solo en base descartable; comprobar alcance CASCADE |

## Orden recomendado

1. Incorporar scripts SQL reales y preparar una base descartable independiente.
2. Corregir los casos conocidos de fechas y validar transformaciones con fixtures sintéticos.
3. Probar primera carga, repetición por rango y rollback.
4. Comparar conteos y claves con SQL de control.
5. Registrar versión, fecha, entrada, comando, resultado y evidencia sin credenciales.

No usar la base existente como objetivo de pruebas destructivas. Las pruebas de integración quedan pendientes mientras no se cuente con la instancia y el DDL.
