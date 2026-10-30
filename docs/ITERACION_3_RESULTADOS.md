# Iteración 3 — resultados del contrato de estados

Fecha: 29 de octubre de 2026, America/Santiago.
Rama exclusiva: feature/etl-hardening-open-tickets. Base: ea33dd8.

## Ejecuciones reales y regresión

- Antes de corregir: **100 aprobadas**, 0 fallidas, 0 omitidas, PostgreSQL real;
  79,97 s de pytest. ITERACION_3_BASELINE_JUNIT.xml conserva esa ejecución.
- Unitarias ampliadas: **91 aprobadas**, con 47 integraciones deseleccionadas
  intencionalmente en esa ejecución de enfoque; no se declararon allí aprobadas.
- Batería completa final: **138 aprobadas, 0 fallidas, 0 omitidas**, en 117,11 s
  de pytest: **91 unitarias y 47 integración PostgreSQL 17.11 descartable**.
  ITERACION_3_JUNIT.xml entrega todos los casos y sus tiempos reales.

De los 100 casos anteriores, 99 siguen con el mismo nombre y expectativa. Uno
exigía que Cancelado fuera NO_CONFIRMADO y se actualizó a CANCELADO conforme a
la regla confirmada, renombrándolo sin eliminar cobertura. Se ejecutaron esos
100 casos adaptados y **38 nuevos** (22 unitarios, 16 PostgreSQL). No se afirma
que la expectativa antigua contradictoria haya pasado sin cambiarla.

## Contrato confirmado y evidencia

| Requisito | Verificación ejecutada |
| --- | --- |
| Insertar los cinco estados | Cinco casos PostgreSQL, uno por estado |
| Actualizar a los cinco estados | Cinco casos PostgreSQL conservando ticket_key |
| Solo WIP dispara alerta | Cinco casos unitarios, cinco inserciones y lote mixto |
| Abierto se acepta sin alerta | Inserción, actualización y lote mixto |
| Cancelado y observaciones | Con/sin cierre; Asunto, Nota_cierre y Solucion exactos |
| Referencias a otros tickets | Texto CLOSED-001/REL-0007, acentos, doble espacio y salto de línea preservados |
| No bloquear lote por WIP | Cinco filas recibidas/seleccionadas/insertadas, una alerta |
| Historial tras cambiar estado | WIP a Cancelado mantiene estado observado, corte y primer lote de la evidencia |
| Idempotencia | Repetir Cancelado deja una fila y cero alertas nuevas; suites anteriores también se repiten |
| Protección contra archivos antiguos | Intento de regresar Cancelado a WIP antiguo rechazado sin perder nota ni PK |
| Compatibilidad histórica | Resuelto, Escalado y alias WIP conservados con tests explícitos |
| No añadir estados nuevos | Suspendido, Reabierto y En revisión rechazados como desconocidos |

## Código y revisión de modelo

- scr/etl_original.py: admite Cancelado como categoría propia. Cierre/respuesta
  no se inventan; información opcional y observaciones originales se conservan.
  Las reglas previas de Cerrado/Resuelto y de otros estados no cambian.
- scr/alertas_operacionales.py: normaliza Cancelado a CANCELADO. Sigue generando
  WIP_EN_CORTE_0530 exclusivamente para WORK_IN_PROGRESS normalizado.
- tests/test_operacional_unit.py: una expectativa obsoleta corregida.
- tests/test_estados_unit.py y test_estados_postgres.py: 38 casos nuevos.
- carga_operacional.py: revisado, sin cambios; versión, auditoría, transacción y
  huella de textos originales mantienen su comportamiento y la regresión pasa.
- Dimensiones: dim_estado ya es VARCHAR(30) con PK/UNIQUE, no enum cerrado.
  Las inserciones y consultas reales verificaron valores originales y tipo.
  No se necesitó migración nueva ni se modificaron los scripts SQL existentes.
- Documentación: contrato definitivo y corrección de la restricción errónea de
  Cancelado en los textos de iteración 2. Los resultados/JUnit históricos se
  conservan como evidencia de su versión, no como contrato actual.

Ejemplo ejecutado: examples/estados_confirmados.json. Incluye los cinco estados
literalmente y una sola alerta, para IT3-005 Work in Progress, en un lote sintético.

## Reproducción

Python 3.12.5, pandas 3.0.6, SQLAlchemy 2.1.4, psycopg2 2.9.13, openpyxl 3.1.5,
pytest 9.2.0. El runner crea y detiene su propia instancia y bases UUID.

```text
python scripts/run_tests.py --postgres-bin <directorio-portatil>/pgsql/bin
```

Para Docker, ruta disponible del runner (no probada en esta ejecución):
`python scripts/run_tests.py`. Ver ITERACION_3_CONTRATO_ESTADOS.md.
El inicio del cluster no se incluye en los segundos de pytest informados.

## Seguridad y límites

No se conectó ni modificó Galaxy real. No se ejecutó --truncate ni una migración
productiva; solo se recrearon los esquemas previos en bases descartables. No se
tocó main ni se hizo merge. PR #1 permanece en borrador.

El fixture original permanece idéntico byte a byte. Estados y textos se
conservan literalmente; la normalización solo se usa para validar/clasificar.
Los campos de observaciones cubiertos son los existentes del contrato: Asunto,
Nota_cierre y Solucion. No se añadió una columna de observaciones distinta.
Integridad temporal y versionado siguen vigentes: un estado legítimo no habilita
fechas inconsistentes, duraciones negativas ni sobrescrituras antiguas.
Se preserva compatibilidad previa sin declarar Resuelto/Escalado estados nuevos
del contrato operacional. No se ejecutaron Luigi ni el origen de tickets.

La regla WIP >2h y las consultas de abiertos >3 días siguen fuera de alcance;
no se introducen notificaciones ni correcciones automáticas de estado.
