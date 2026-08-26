# Funciones de apoyo compartidas por las pruebas unitarias. No es un test en
# si mismo (por eso no se llama test_*.py) para que pytest no intente
# recolectarlo como caso de prueba.
from __future__ import annotations

from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    """Lee una salida de comando real y sanitizada guardada en fixtures/."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")
