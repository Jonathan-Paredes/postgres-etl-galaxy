-- =====================================================================
-- ESQUEMA ESTRELLA - Mesa de Servicio Galaxy Mining
-- Grano del hecho: 1 fila = 1 ticket (Numero_ticket)
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS galaxy_dw;
SET search_path TO galaxy_dw;

-- ---------------------------------------------------------------------
-- DIMENSIONES
-- ---------------------------------------------------------------------

-- Dimensión de fecha (estándar, una fila por día). Cubre creación,
-- respuesta y cierre mediante roleplaying (3 FKs en el hecho apuntan aquí).
CREATE TABLE dim_fecha (
    fecha_key        INT PRIMARY KEY,          -- formato YYYYMMDD
    fecha             DATE NOT NULL UNIQUE,
    anio              SMALLINT NOT NULL,
    mes               SMALLINT NOT NULL,
    nombre_mes        VARCHAR(20) NOT NULL,
    dia               SMALLINT NOT NULL,
    trimestre         SMALLINT NOT NULL,
    dia_semana        SMALLINT NOT NULL,        -- 1=lunes ... 7=domingo
    nombre_dia_semana VARCHAR(15) NOT NULL,
    es_fin_semana     BOOLEAN NOT NULL
);

-- Equipo minero afectado (camión, pala, perforadora, etc.)
CREATE TABLE dim_equipo (
    equipo_key    SERIAL PRIMARY KEY,
    equipo_codigo VARCHAR(60) NOT NULL UNIQUE,   -- ej. 'CAMION 785'
    tipo_equipo   VARCHAR(40)                    -- ej. 'CAMION'
);

-- Sitio / ubicación física
CREATE TABLE dim_sitio (
    sitio_key    SERIAL PRIMARY KEY,
    sitio_nombre VARCHAR(60) NOT NULL UNIQUE
);

-- Prioridad del ticket
CREATE TABLE dim_prioridad (
    prioridad_key SERIAL PRIMARY KEY,
    prioridad     VARCHAR(20) NOT NULL UNIQUE
);

-- Estado del ticket (histórico -> hoy solo 'Resuelto', pero se modela
-- para soportar estados futuros: Abierto, En Proceso, Escalado, etc.)
CREATE TABLE dim_estado (
    estado_key SERIAL PRIMARY KEY,
    estado     VARCHAR(30) NOT NULL UNIQUE
);

-- Categoría del ticket: tipo (Incidente/Requerimiento) + subsistema
-- (dimensión "junk" -- ambos se definen juntos al abrir el ticket)
CREATE TABLE dim_categoria_ticket (
    categoria_ticket_key SERIAL PRIMARY KEY,
    tipo_ticket           VARCHAR(20) NOT NULL,   -- Incidente / Requerimiento
    tipo_requerimiento    VARCHAR(60) NOT NULL,   -- subsistema afectado
    UNIQUE (tipo_ticket, tipo_requerimiento)
);

-- Clasificación de la falla al ABRIR el ticket (dimensión junk)
CREATE TABLE dim_solicitud_falla (
    solicitud_falla_key SERIAL PRIMARY KEY,
    tipo_solicitud        VARCHAR(60) NOT NULL,
    tipo_falla             VARCHAR(60) NOT NULL,
    UNIQUE (tipo_solicitud, tipo_falla)
);

-- Clasificación de la falla al CERRAR el ticket
-- (es también el target del modelo BERT)
CREATE TABLE dim_falla_cierre (
    falla_cierre_key  SERIAL PRIMARY KEY,
    tipo_falla_cierre VARCHAR(80) NOT NULL UNIQUE
);

-- Cómo/cuándo se originó el ticket (dimensión junk)
CREATE TABLE dim_apertura (
    apertura_key  SERIAL PRIMARY KEY,
    modo_apertura VARCHAR(60) NOT NULL,
    origen         VARCHAR(20) NOT NULL,   -- Turno Z1 / Turno Z2
    UNIQUE (modo_apertura, origen)
);

-- Bucket de duración de la atención
CREATE TABLE dim_clasificacion (
    clasificacion_key SERIAL PRIMARY KEY,
    clasificacion       VARCHAR(40) NOT NULL UNIQUE
);

-- Operador (técnico). Se usa dos veces en el hecho (rol-playing):
-- apertura y cierre.
CREATE TABLE dim_operador (
    operador_key    SERIAL PRIMARY KEY,
    operador_nombre VARCHAR(40) NOT NULL UNIQUE
);

-- ---------------------------------------------------------------------
-- TABLA DE HECHOS
-- ---------------------------------------------------------------------

CREATE TABLE fact_tickets (
    ticket_key             BIGSERIAL PRIMARY KEY,
    numero_ticket           INT NOT NULL UNIQUE,

    -- Fechas (roleplaying sobre dim_fecha)
    fecha_creacion_key      INT NOT NULL REFERENCES dim_fecha(fecha_key),
    fecha_respuesta_key     INT NOT NULL REFERENCES dim_fecha(fecha_key),
    fecha_cierre_key        INT NOT NULL REFERENCES dim_fecha(fecha_key),

    -- Marca de tiempo completa (para cálculos finos que el día no captura)
    ts_creacion             TIMESTAMP NOT NULL,
    ts_respuesta            TIMESTAMP NOT NULL,
    ts_cierre               TIMESTAMP NOT NULL,

    -- Dimensiones
    equipo_key              INT REFERENCES dim_equipo(equipo_key),        -- nullable (458 tickets sin equipo)
    sitio_key                INT REFERENCES dim_sitio(sitio_key),          -- nullable
    prioridad_key            INT NOT NULL REFERENCES dim_prioridad(prioridad_key),
    estado_key                INT NOT NULL REFERENCES dim_estado(estado_key),
    categoria_ticket_key     INT NOT NULL REFERENCES dim_categoria_ticket(categoria_ticket_key),
    solicitud_falla_key      INT NOT NULL REFERENCES dim_solicitud_falla(solicitud_falla_key),
    falla_cierre_key          INT NOT NULL REFERENCES dim_falla_cierre(falla_cierre_key),
    apertura_key              INT NOT NULL REFERENCES dim_apertura(apertura_key),
    clasificacion_key         INT NOT NULL REFERENCES dim_clasificacion(clasificacion_key),
    operador_apertura_key    INT NOT NULL REFERENCES dim_operador(operador_key),
    operador_cierre_key       INT NOT NULL REFERENCES dim_operador(operador_key),

    -- Texto libre (degenerado; insumo directo para NLP/BERT)
    asunto        TEXT,
    nota_cierre   TEXT,
    solucion      TEXT,

    -- Métricas
    tiempo_abierto_min  INT NOT NULL,       -- minutos totales del ticket
    duracion_min         NUMERIC(10, 2),     -- solo 29/961 tickets la traen
    es_incidente          BOOLEAN NOT NULL   -- true si Tipo_ticket = 'Incidente' (== "falla")
);

CREATE INDEX idx_fact_tickets_equipo   ON fact_tickets(equipo_key);
CREATE INDEX idx_fact_tickets_sitio    ON fact_tickets(sitio_key);
CREATE INDEX idx_fact_tickets_fecha    ON fact_tickets(fecha_creacion_key);
CREATE INDEX idx_fact_tickets_incidente ON fact_tickets(es_incidente);

COMMENT ON TABLE fact_tickets IS 'Hecho: un ticket de mesa de servicio de Galaxy Mining. Grano = 1 fila por Numero_ticket.';
COMMENT ON COLUMN fact_tickets.es_incidente IS 'Derivado de Tipo_ticket=Incidente. Usado como variable objetivo del modelo XGBoost de predicción de fallas.';
