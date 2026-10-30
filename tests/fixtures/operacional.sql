-- SOLO fuente sintética descartable. No es migración de Galaxy ni del DW.
CREATE SCHEMA operacional;
CREATE TABLE operacional.ticket_versiones (
    numero_ticket TEXT NOT NULL,
    tipo_ticket TEXT NOT NULL,
    componente TEXT NOT NULL,
    estado TEXT NOT NULL,
    observaciones TEXT,
    fecha_creacion TIMESTAMPTZ NOT NULL,
    fecha_modificacion TIMESTAMPTZ NOT NULL,
    PRIMARY KEY(numero_ticket,fecha_modificacion),
    CHECK(fecha_modificacion>=fecha_creacion)
);
CREATE INDEX idx_operacional_corte ON operacional.ticket_versiones(fecha_modificacion,numero_ticket);

-- Los 11 pendientes / 2 abiertos / 1 WIP son SOLO este fixture de Incident.
INSERT INTO operacional.ticket_versiones
SELECT 'I-'||lpad(n::text,3,'0'),'Incident',
       CASE n%4 WHEN 0 THEN 'Radios TETRA' WHEN 1 THEN 'Redes' WHEN 2 THEN 'Enlaces' ELSE 'CCTV' END,
       CASE WHEN n<=11 OR n=14 THEN 'Pendiente' ELSE 'Abierto' END,
       'Observación sintética; relacionado con ticket I-003.  Mantener texto.',
       '2025-03-06T01:00:00-03:00','2025-03-06T02:00:00-03:00'
FROM generate_series(1,14) AS n;
INSERT INTO operacional.ticket_versiones VALUES
 ('I-014','Incident','Enlaces','Work in Progress','Cambio posterior al ETL 05:30; referencia I-003.','2025-03-06T01:00:00-03:00','2025-03-06T20:55:00-03:00'),
 ('SR-001','Service Request','Aplicaciones','Pendiente','Solicitud sintética 1.','2025-03-06T01:00:00-03:00','2025-03-06T02:00:00-03:00'),
 ('SR-002','Service Request','Redes','Pendiente','Solicitud sintética 2.','2025-03-06T01:00:00-03:00','2025-03-06T02:00:00-03:00'),
 ('SR-003','Service Request','Telefonía','Abierto','Solicitud sintética 3.','2025-03-06T01:00:00-03:00','2025-03-06T02:00:00-03:00'),
 ('SR-004','Service Request','Aplicaciones','Abierto','Todavía abierto a las 05:30.','2025-03-06T01:00:00-03:00','2025-03-06T02:00:00-03:00'),
 ('SR-004','Service Request','Aplicaciones','Work in Progress','WIP observado sin duración mínima.','2025-03-06T01:00:00-03:00','2025-03-06T20:45:00-03:00'),
 ('I-015','Incident','Radios TETRA','Cerrado','Cierre legítimo; no incumplimiento.','2025-03-06T01:00:00-03:00','2025-03-06T18:00:00-03:00'),
 ('SR-005','Service Request','Telefonía','Cancelado','Duplicado de SR-002. Observación original.','2025-03-06T01:00:00-03:00','2025-03-06T18:00:00-03:00'),
 -- Esta versión futura no puede alterar el reporte histórico de las 21:00.
 ('I-001','Incident','Redes','Cerrado','Cerrado después del reporte.','2025-03-06T01:00:00-03:00','2025-03-06T21:30:00-03:00');
