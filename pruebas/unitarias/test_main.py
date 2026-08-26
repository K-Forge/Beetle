# Pruebas del punto de entrada (issue #222): parseo de argumentos, el FIFO
# como canal unico entre trigger.sh y el orquestador, y el apagado limpio
# ante SIGTERM. No prueban el loop infinito de run() directamente -- eso se
# cubre indirectamente: wait_for_next_cycle() es el unico lugar que decide
# "tick" o "trigger", y run() llama al mismo callback sin importar cual de
# los dos devolvio.
from __future__ import annotations

import os
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from doctorjk.main import (
    AppContext,
    ensure_fifo,
    parse_args,
    run,
    wait_for_next_cycle,
)

REPO_ROOT = Path(__file__).parent.parent.parent


# ------------------------------------------------------------------- parse_args


def test_defaults_son_seguros():
    args = parse_args([])
    assert args.dry_run is False
    assert args.auto_fix is False
    assert args.once is False
    assert args.interval > 0


def test_auto_fix_y_dry_run_son_incompatibles():
    with pytest.raises(SystemExit):
        parse_args(["--auto-fix", "--dry-run"])


def test_intervalo_cero_se_rechaza():
    with pytest.raises(SystemExit):
        parse_args(["--interval", "0"])


def test_intervalo_negativo_se_rechaza():
    with pytest.raises(SystemExit):
        parse_args(["--interval", "-5"])


# --------------------------------------------------------------------- ensure_fifo


def test_ensure_fifo_crea_pipe_con_permisos_restrictivos(tmp_path):
    fifo_path = tmp_path / "run" / "doctorjk" / "trigger.fifo"
    assert ensure_fifo(fifo_path) is True
    assert stat.S_ISFIFO(fifo_path.stat().st_mode)
    assert stat.S_IMODE(fifo_path.stat().st_mode) == 0o600


def test_ensure_fifo_es_idempotente(tmp_path):
    fifo_path = tmp_path / "trigger.fifo"
    assert ensure_fifo(fifo_path) is True
    assert ensure_fifo(fifo_path) is True


def test_ensure_fifo_sin_permisos_degrada_a_solo_polling(tmp_path, monkeypatch):
    fifo_path = tmp_path / "sin-permiso" / "trigger.fifo"

    def falla_permiso(self, *args, **kwargs):
        raise PermissionError("denegado")

    monkeypatch.setattr(Path, "mkdir", falla_permiso)
    assert ensure_fifo(fifo_path) is False


# ---------------------------------------------------------- wait_for_next_cycle


def test_wait_for_next_cycle_sin_fifo_espera_el_intervalo(monkeypatch):
    dormidos = []
    monkeypatch.setattr(time, "sleep", dormidos.append)
    assert wait_for_next_cycle(None, 30.0) == "tick"
    assert dormidos == [30.0]


def test_wait_for_next_cycle_detecta_escritura_del_trigger(tmp_path):
    fifo_path = tmp_path / "trigger.fifo"
    os.mkfifo(fifo_path)
    fd_lectura = os.open(str(fifo_path), os.O_RDWR | os.O_NONBLOCK)
    fd_escritura = os.open(str(fifo_path), os.O_WRONLY | os.O_NONBLOCK)
    try:
        os.write(fd_escritura, b"1\n")
        assert wait_for_next_cycle(fd_lectura, 5.0) == "trigger"
    finally:
        os.close(fd_escritura)
        os.close(fd_lectura)


def test_wait_for_next_cycle_sin_senal_cae_a_tick_por_timeout(tmp_path):
    fifo_path = tmp_path / "trigger.fifo"
    os.mkfifo(fifo_path)
    fd_lectura = os.open(str(fifo_path), os.O_RDWR | os.O_NONBLOCK)
    try:
        assert wait_for_next_cycle(fd_lectura, 0.1) == "tick"
    finally:
        os.close(fd_lectura)


# --------------------------------------------------------------------------- run


def test_once_llama_al_callback_una_sola_vez_sin_tocar_el_fifo():
    llamadas = []
    contexto = AppContext(
        interval_s=30.0,
        fifo_path=Path("/ruta/que/no/deberia/tocarse/trigger.fifo"),
        once=True,
        take_snapshot=lambda: "muestra-falsa",
        on_snapshot=llamadas.append,
    )
    run(contexto)
    assert llamadas == ["muestra-falsa"]


def test_run_termina_limpio_con_sigterm(tmp_path):
    fifo_path = tmp_path / "trigger.fifo"
    entorno = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    proceso = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "doctorjk.main",
            "--fifo-path",
            str(fifo_path),
            "--interval",
            "0.2",
        ],
        cwd=str(REPO_ROOT),
        env=entorno,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        time.sleep(0.5)
        proceso.send_signal(signal.SIGTERM)
        codigo = proceso.wait(timeout=5)
    finally:
        if proceso.poll() is None:
            proceso.kill()
            proceso.wait()
    assert codigo == 0
