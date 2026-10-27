"""
Conexión a PostgreSQL para el ETL.

Centraliza la creación del engine de SQLAlchemy a partir de variables
de entorno, con valores por defecto para desarrollo local (Docker).
"""
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from logger import get_logger

log = get_logger(__name__)


def get_engine() -> Engine:
    """
    Devuelve un Engine de SQLAlchemy hacia Postgres.

    Configuración por variables de entorno (con defaults para dev local):
      - DB_HOST      (default: localhost)
      - DB_PORT      (default: 5432)
      - DB_NAME      (default: Galaxy_mina)
      - DB_USER      (default: postgres)
      - DB_PASSWORD  (default: password)

    El engine usa pool_pre_ping para reconectar si la conexión se cayó,
    y echo=False para no spamear los logs con cada SQL.
    """
    host = os.getenv("DB_HOST", "localhost")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME", "Galaxy_mina")
    user = os.getenv("DB_USER", "postgres")
    password = os.getenv("DB_PASSWORD", "password")

    url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{name}"

    log.info("Conectando a Postgres: %s@%s:%s/%s", user, host, port, name)

    return create_engine(
        url,
        pool_pre_ping=True,   # verifica la conexión antes de usarla
        echo=False,           # True para ver todo el SQL (útil al depurar)
        future=True,
    )