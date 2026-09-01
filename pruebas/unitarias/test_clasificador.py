# Pruebas del clasificador (tarea #200): mapeo explícito tipo -> script.
from __future__ import annotations

import pytest

from doctorjk.clasificador import classify
from doctorjk.modelos import SignalType


@pytest.mark.parametrize(
    "signal_type,script",
    [
        (SignalType.DISK_FULL, "fix_disco.sh"),
        (SignalType.SERVICE_FAILED, "fix_servicio.sh"),
        (SignalType.MEMORY_LOW, "fix_memoria.sh"),
        (SignalType.PORT_OCCUPIED, "fix_puerto.sh"),
    ],
)
def test_tipos_mapeados_devuelven_su_script(signal_type, script):
    assert classify(signal_type) == script


def test_port_down_no_tiene_script():
    # No se mapea a puerto_ocupado: son condiciones distintas (defecto 6).
    assert classify(SignalType.PORT_DOWN) is None


def test_high_load_no_tiene_script():
    assert classify(SignalType.HIGH_LOAD) is None
