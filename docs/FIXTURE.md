# Fixture original

tests/fixtures/galaxy_tickets_abiertos_pruebas.xlsx se copia byte a byte del
archivo entregado por el autor, conservando Sheet1 y Escenarios.

| Ticket | Estado | Respuesta | Cierre | Duración final |
| --- | --- | --- | --- | --- |
| OPEN-001 | Abierto | NULL | NULL | NULL |
| OPEN-002 | En progreso | Informada | NULL | NULL |
| OPEN-003 | Pendiente | NULL | NULL | NULL |
| CLOSED-001 | Cerrado | Informada | Informado | 60 |

Tiempo_abierto está ausente en todas las filas y se mantiene NULL. Los textos
y dimensiones de cierre ausentes permanecen NULL. La hoja Escenarios exige
repetir OPEN-001 sin duplicar; la integración repite el archivo completo.
Cambios de estado, reapertura, límite de fecha, rollback y concurrencia son
variantes creadas en memoria; nunca sobrescriben el Excel.
