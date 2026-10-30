"""Conexión explícita; no hay credenciales ni destino predeterminados."""
import os
from sqlalchemy import create_engine
from sqlalchemy.engine import URL, Engine


def get_engine() -> Engine:
    names = ("DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD")
    missing = [n for n in names if not os.environ.get(n, "").strip()]
    if missing:
        raise ValueError("Configurar variables PostgreSQL: " + ", ".join(missing))
    try:
        port = int(os.environ["DB_PORT"])
        if not 1 <= port <= 65535:
            raise ValueError()
    except ValueError as exc:
        raise ValueError("DB_PORT debe ser un puerto válido") from exc
    url = URL.create("postgresql+psycopg2", username=os.environ["DB_USER"],
                     password=os.environ["DB_PASSWORD"], host=os.environ["DB_HOST"],
                     port=port, database=os.environ["DB_NAME"])
    return create_engine(url, pool_pre_ping=True, hide_parameters=True,
                         connect_args={"connect_timeout": 10,
                                       "options": "-c statement_timeout=60000 -c lock_timeout=30000"})
