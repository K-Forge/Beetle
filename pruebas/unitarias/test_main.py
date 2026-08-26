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


# ------------------------------------------------- cableado del Modo 1 (D4)


def test_build_pipeline_deps_arma_los_cinco_contratos(tmp_path):
    from doctorjk.config import AppConfig, RemediationMode
    from doctorjk.main import build_pipeline_deps

    config = AppConfig(
        monitor_interval_s=30.0,
        persistence_cycles=2,
        cooldown_cycles=2,
        disk_pct_threshold=90,
        memory_available_mb_threshold=512,
        port_timeout_s=60.0,
        service_cycles=2,
        reports_dir=tmp_path,
        remediation_mode=RemediationMode.DIAGNOSTICO,
        auto_fix=False,
        dry_run=True,
        command_timeout_s=30.0,
        llm_url="https://proveedor/v1",
        llm_model="gpt-oss-120b",
        llm_timeout_s=30.0,
        llm_cache=False,
        llm_api_key="k",
    )

    deps = build_pipeline_deps(config, session=object())

    assert deps.collect_evidence is not None
    assert deps.sanitize_evidence is not None
    assert deps.diagnose is not None
    assert deps.save_report is not None
    assert deps.write_raw_evidence is not None


def test_on_incident_no_deja_escapar_excepciones(tmp_path, caplog):
    # Un incidente que falla no debe tumbar la vigilancia de los demás.
    from datetime import datetime, timezone

    from doctorjk.main import on_incident
    from doctorjk.modelos import Incident, IncidentState, SignalType
    from doctorjk.pipeline import PipelineDeps

    def revienta(*args, **kwargs):
        raise RuntimeError("fallo inesperado")

    deps = PipelineDeps(revienta, revienta, revienta, revienta, revienta)
    ahora = datetime(2026, 8, 26, tzinfo=timezone.utc)
    incidente = Incident("inc-9", SignalType.SERVICE_FAILED, "x", ahora, ahora, IncidentState.INCIDENT)

    with caplog.at_level("ERROR"):
        on_incident(incidente, "prompt", tmp_path, deps, ahora)

    assert "inc-9" in caplog.text
