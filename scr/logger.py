"""
Configuración centralizada de logging para el ETL.

Escribe en consola y, opcionalmente, en un archivo (logs/etl.log).
Uso:
    from logger import get_logger
    log = get_logger(__name__)
"""
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMATO = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"

_configurado = False


def _configurar_root() -> None:
    """Configura el logger raíz una sola vez (evita handlers duplicados)."""
    global _configurado
    if _configurado:
        return

    nivel = os.getenv("LOG_LEVEL", "INFO").upper()
    root = logging.getLogger()
    root.setLevel(nivel)

    formatter = logging.Formatter(FORMATO, FORMATO_FECHA)

    # Consola
    consola = logging.StreamHandler(sys.stdout)
    consola.setFormatter(formatter)
    root.addHandler(consola)

    # Archivo (rotativo: 5 MB x 3 respaldos). Desactivar con LOG_TO_FILE=0
    if os.getenv("LOG_TO_FILE", "1") != "0":
        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        log_dir.mkdir(parents=True, exist_ok=True)
        archivo = RotatingFileHandler(
            log_dir / "etl.log", maxBytes=5_000_000,
            backupCount=3, encoding="utf-8",
        )
        archivo.setFormatter(formatter)
        root.addHandler(archivo)

    # Bajar el ruido de librerías
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    _configurado = True


def get_logger(nombre: str = "etl") -> logging.Logger:
    _configurar_root()
    return logging.getLogger(nombre)