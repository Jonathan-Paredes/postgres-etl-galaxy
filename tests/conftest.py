import os
import sys
from pathlib import Path
import pytest

os.environ['LOG_TO_FILE'] = '0'
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scr'))
import etl_original as etl

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'tests/fixtures/galaxy_tickets_abiertos_pruebas.xlsx'

@pytest.fixture
def fuente():
    return etl.extraer(str(FIXTURE))
