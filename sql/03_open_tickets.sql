-- PROPUESTA revisada contra el DDL en sql/baseline.
-- Ejecutar SOLO en una base descartable hasta confirmar el DDL de destino.
-- Nunca invocada automáticamente por el ETL. No elimina registros ni FKs.
BEGIN;
ALTER TABLE galaxy_dw.fact_tickets
    ALTER COLUMN numero_ticket TYPE TEXT USING numero_ticket::text,
    ALTER COLUMN fecha_respuesta_key DROP NOT NULL,
    ALTER COLUMN fecha_cierre_key DROP NOT NULL,
    ALTER COLUMN ts_respuesta DROP NOT NULL,
    ALTER COLUMN ts_cierre DROP NOT NULL,
    ALTER COLUMN falla_cierre_key DROP NOT NULL,
    ALTER COLUMN operador_cierre_key DROP NOT NULL,
    ALTER COLUMN clasificacion_key DROP NOT NULL,
    ALTER COLUMN tiempo_abierto_min DROP NOT NULL;
COMMIT;
