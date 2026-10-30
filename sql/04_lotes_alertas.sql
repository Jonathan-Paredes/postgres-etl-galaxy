-- Migración aditiva. Requiere baseline + 03_open_tickets.sql revisados.
-- Nunca se ejecuta automáticamente ni sobre Galaxy durante las pruebas.
BEGIN;
CREATE TABLE galaxy_dw.etl_lotes (
    lote_id UUID PRIMARY KEY,
    fecha_inicio TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    fecha_fin TIMESTAMPTZ,
    fecha_corte TIMESTAMPTZ NOT NULL,
    archivo_origen TEXT NOT NULL,
    hash_archivo CHAR(64) NOT NULL,
    ventana_desde TIMESTAMPTZ NOT NULL,
    solapamiento_dias INT NOT NULL CHECK (solapamiento_dias > 0),
    modo_extraccion TEXT NOT NULL,
    columna_modificacion TEXT,
    politica_conflicto TEXT NOT NULL CHECK (politica_conflicto IN ('RECHAZAR','SNAPSHOT_CONFIRMADO')),
    filas_recibidas INT NOT NULL CHECK (filas_recibidas >= 0),
    filas_seleccionadas INT NOT NULL DEFAULT 0 CHECK (filas_seleccionadas >= 0),
    filas_insertadas INT NOT NULL DEFAULT 0 CHECK (filas_insertadas >= 0),
    filas_actualizadas INT NOT NULL DEFAULT 0 CHECK (filas_actualizadas >= 0),
    filas_sin_cambios INT NOT NULL DEFAULT 0 CHECK (filas_sin_cambios >= 0),
    alertas_detectadas INT NOT NULL DEFAULT 0 CHECK (alertas_detectadas >= 0),
    alertas_nuevas INT NOT NULL DEFAULT 0 CHECK (alertas_nuevas >= 0),
    estado_ejecucion TEXT NOT NULL CHECK (estado_ejecucion IN ('INICIADO','COMPLETADO','FALLIDO')),
    error_codigo TEXT,
    CHECK (fecha_corte >= ventana_desde),
    CHECK (estado_ejecucion <> 'COMPLETADO' OR
           filas_seleccionadas = filas_insertadas + filas_actualizadas + filas_sin_cambios)
);

CREATE TABLE galaxy_dw.etl_ticket_version (
    numero_ticket TEXT PRIMARY KEY REFERENCES galaxy_dw.fact_tickets(numero_ticket),
    hash_contenido CHAR(64) NOT NULL,
    ultimo_corte TIMESTAMPTZ NOT NULL,
    modificacion_origen TIMESTAMPTZ,
    lote_id UUID NOT NULL REFERENCES galaxy_dw.etl_lotes(lote_id)
);

CREATE TABLE galaxy_dw.alertas_operacionales (
    alerta_id BIGSERIAL PRIMARY KEY,
    numero_ticket TEXT NOT NULL REFERENCES galaxy_dw.fact_tickets(numero_ticket),
    codigo_regla TEXT NOT NULL,
    fecha_corte TIMESTAMPTZ NOT NULL,
    estado_observado TEXT NOT NULL,
    lote_id UUID NOT NULL REFERENCES galaxy_dw.etl_lotes(lote_id),
    fecha_deteccion TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (numero_ticket, codigo_regla, fecha_corte)
);
CREATE INDEX idx_alertas_corte ON galaxy_dw.alertas_operacionales(fecha_corte, codigo_regla);
COMMENT ON TABLE galaxy_dw.alertas_operacionales IS
    'Evidencia histórica de incumplimientos; no contiene estado de notificación o seguimiento.';
COMMENT ON COLUMN galaxy_dw.etl_ticket_version.modificacion_origen IS
    'Marca real informada por origen; nunca equivale a fecha de ingesta ni de creación.';
COMMIT;
