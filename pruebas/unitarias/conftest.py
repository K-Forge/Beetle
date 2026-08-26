# Fixtures compartidas por las pruebas unitarias. No hay __init__.py en esta
# carpeta a proposito: pytest la agrega directo a sys.path (modo "rootless"),
# asi que los tests importan doctorjk porque el paquete quedo instalado en
# modo editable (`pip install -e ".[dev]"`, ver pyproject.toml y bloque A2).
from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
