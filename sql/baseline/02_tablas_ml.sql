-- =====================================================================
-- TABLAS DE MACHINE LEARNING
-- Extienden el esquema estrella con resultados de modelos entrenados
-- fuera de la base (Python) y cargados de vuelta a Postgres.
-- =====================================================================

SET search_path TO galaxy_dw;

-- ---------------------------------------------------------------------
-- Registro genérico de modelos entrenados (versión, métricas, fecha)
-- ---------------------------------------------------------------------
CREATE TABLE ml_modelos (
    modelo_key      SERIAL PRIMARY KEY,
    nombre_modelo    VARCHAR(60) NOT NULL,      -- 'bert_nota_cierre' | 'xgboost_fallas'
    version           VARCHAR(20) NOT NULL,
    fecha_entrenamiento TIMESTAMP NOT NULL DEFAULT now(),
    parametros         JSONB,                    -- hiperparámetros usados
    metricas            JSONB,                    -- accuracy, f1, auc, etc.
    ruta_artefacto      TEXT,                     -- path/URI al modelo serializado
    UNIQUE (nombre_modelo, version)
);

-- ---------------------------------------------------------------------
-- BERT: clasificación del texto de Nota_cierre -> Tipo_falla_cierre
-- ---------------------------------------------------------------------
CREATE TABLE ml_bert_nota_cierre_pred (
    pred_key                BIGSERIAL PRIMARY KEY,
    ticket_key                BIGINT NOT NULL REFERENCES fact_tickets(ticket_key),
    modelo_key                 INT NOT NULL REFERENCES ml_modelos(modelo_key),

    falla_cierre_real_key      INT REFERENCES dim_falla_cierre(falla_cierre_key),   -- etiqueta real (si se conoce)
    falla_cierre_predicha_key  INT NOT NULL REFERENCES dim_falla_cierre(falla_cierre_key),

    probabilidad               NUMERIC(6, 5) NOT NULL,   -- prob. de la clase predicha (0-1)
    distribucion_probabilidades JSONB,                    -- {clase: prob, ...} softmax completo
    es_correcta                  BOOLEAN,                  -- predicha == real (si se conoce la real)
    fecha_prediccion              TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (ticket_key, modelo_key)
);

CREATE INDEX idx_bert_pred_ticket ON ml_bert_nota_cierre_pred(ticket_key);

COMMENT ON TABLE ml_bert_nota_cierre_pred IS
  'Predicciones de un modelo BERT (fine-tuned) que clasifica el texto de nota_cierre en una clase de dim_falla_cierre.';

-- ---------------------------------------------------------------------
-- XGBoost: predicción de si un ticket será una falla (Incidente)
-- usando solo variables conocidas al momento de apertura del ticket
-- ---------------------------------------------------------------------
CREATE TABLE ml_xgboost_falla_pred (
    pred_key            BIGSERIAL PRIMARY KEY,
    ticket_key            BIGINT NOT NULL REFERENCES fact_tickets(ticket_key),
    modelo_key             INT NOT NULL REFERENCES ml_modelos(modelo_key),

    es_incidente_real       BOOLEAN,          -- etiqueta real (si se conoce, ej. en backtesting)
    prob_falla                NUMERIC(6, 5) NOT NULL,   -- probabilidad predicha de ser Incidente
    es_incidente_predicho    BOOLEAN NOT NULL,          -- umbral aplicado (default 0.5)
    es_correcta               BOOLEAN,
    fecha_prediccion           TIMESTAMP NOT NULL DEFAULT now(),

    UNIQUE (ticket_key, modelo_key)
);

CREATE INDEX idx_xgb_pred_ticket ON ml_xgboost_falla_pred(ticket_key);

COMMENT ON TABLE ml_xgboost_falla_pred IS
  'Predicciones de un modelo XGBoost que estima la probabilidad de que un ticket sea una falla (Incidente) usando solo variables disponibles al abrir el ticket.';

-- ---------------------------------------------------------------------
-- Importancia de variables de XGBoost (para el dashboard/presentación)
-- ---------------------------------------------------------------------
CREATE TABLE ml_xgboost_feature_importance (
    modelo_key   INT NOT NULL REFERENCES ml_modelos(modelo_key),
    feature       VARCHAR(80) NOT NULL,
    importancia   NUMERIC(10, 6) NOT NULL,
    PRIMARY KEY (modelo_key, feature)
);
