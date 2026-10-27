# Modelo y contrato de datos

## Entrada

Un ticket por fila. Numero_ticket debe ser único dentro del archivo. Excel requiere hoja Sheet1; CSV detecta separador con motor Python y prueba utf-8, latin-1 y cp1252 en ese orden. Fechas interpretadas con dayfirst=True.

Columnas requeridas:

```text
Numero_ticket, Fecha_creacion_ticket, Fecha_respuesta, Fecha_cierre,
Estado, Prioridad, Tiempo_abierto, Tipo_ticket, Tipo_requerimiento,
Asunto, Nota_cierre, Solucion, Operador_apertura, Modo_apertura,
Origen, Tipo_solicitud, Tipo_falla, Tipo_falla_cierre, Operador_cierre,
Equipo, Tipo, Clasificación, Sitio, Duración (minutos)
```

## Dimensiones

| Dimensión | Clave natural |
| --- | --- |
| dim_fecha | fecha_key, entero YYYYMMDD |
| dim_equipo | equipo_codigo |
| dim_sitio | sitio_nombre |
| dim_prioridad | prioridad |
| dim_estado | estado |
| dim_clasificacion | clasificacion |
| dim_falla_cierre | tipo_falla_cierre |
| dim_categoria_ticket | tipo_ticket + tipo_requerimiento |
| dim_solicitud_falla | tipo_solicitud + tipo_falla |
| dim_apertura | modo_apertura + origen |
| dim_operador | operador_nombre |

El código espera constraints UNIQUE compatibles con ON CONFLICT. Para dimensiones diferentes de fecha, las claves sustitutas las asigna PostgreSQL. DO NOTHING conserva valores ya existentes: no es actualización de atributos ni implementación SCD tipo 2.

## Hecho

`fact_tickets`: granularidad de ticket de origen. Incluye tres claves de fecha, timestamps, claves de dimensiones, dos roles de operador (apertura/cierre), asunto, nota de cierre, solución, tiempos en minutos y es_incidente.

Equipo y sitio pueden no tener clave; el resto de las claves se valida como no nulo. Las duraciones se copian desde el origen; el ETL no incorpora la regla de descarte de más de 30 días utilizada por los agregados del agente.

## Transacción

Una ejecución de carga abre engine.begin(): dimensiones, mapeos, construcción de hechos y escritura están dentro de la transacción. Ante excepción, SQLAlchemy solicita rollback. Falta demostrar atomicidad con pruebas de integración. Las tablas staging se crean con to_sql(if_exists=replace) y después se eliminan.

## Integración con el agente

El ETL escribe en galaxy_dw y el agente consulta una parte de ese esquema. Para distribuir una demo completa faltan DDL, permisos de roles, configuración Docker y un flujo de inicialización probado. No se inspeccionó una base activa durante la documentación.
