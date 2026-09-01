# Integración cruzada LOCAL: los 4 fix_*.sh REALES + comun.sh REAL + un
# config.toml completo real, corridos con el intérprete real del venv del
# repo (sys.executable -- comun.sh le aplica -I internamente en cada
# read_config_attr, igual que en producción). Único doble: `stat` (root/640,
# mismo patrón que test_comun_permisos.py) y los comandos del sistema que
# cada script invoca (systemctl/ss/df/free/journalctl/sleep) -- nunca
# comun.sh ni read_config_attr.
#
# Objetivo explícito (pedido de auditoría, 2026-09-01, tras los dos P0 de
# comun.sh encontrados en esta misma ronda -- aritmética octal de
# _verify_config_ownership, commit cc05ef9, y el str crudo de
# read_config_attr, commit ddeb6f2): que esta combinación exacta -- script
# real + comun.sh real + venv real -- hubiera atrapado ambos bugs de punta
# a punta, no solo con dobles que los saltean por diseño (test_scripts_fix.py
# usa un doble de comun.sh que no verifica nada) ni solo con sourcing
# aislado (test_comun_permisos.py no corre ningún fix_*.sh). Confirmado por
# mutación al final del archivo: cada bug, reintroducido por separado,
# rompe estos tests.
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

from ayudantes import (
    COMUN_SH,
    FAKE_DF,
    FAKE_FIND,
    FAKE_FREE,
    FAKE_JOURNALCTL,
    FAKE_SLEEP,
    FAKE_SS_OCUPADO,
    FAKE_STAT,
    FAKE_SYSTEMCTL,
    FAKE_SYSTEMCTL_MEMORIA,
    FAKE_SYSTEMCTL_PUERTO_OCUPADO,
    FAKE_SYSTEMCTL_SERVICIO,
    FIX_DISCO,
    FIX_MEMORIA,
    FIX_PUERTO,
    FIX_SERVICIO,
)
from ayudantes import instalar_script

# Un solo TOML completo y real para las 4 corridas: las entidades (unidad,
# puerto, ocupante, unidad de memoria) coinciden con lo que cada FAKE_*
# espera vía TEST_* -- no hay nada sintético del lado de comun.sh, solo del
# lado de los comandos de sistema que cada fix_*.sh invoca.
_TOML_TEMPLATE = """
intervalo_monitor_s = 30
ciclos_persistencia = 2
enfriamiento_ciclos = 2
disco_pct = 90
puntos_montaje_vigilados = ["/"]
memoria_disponible_mb = 512
puerto_timeout_s = 60
servicio_ciclos = 2
servicios_vigilados = ["test-svc.service"]
puertos_vigilados = [
  {{ puerto = 9999, servicio = "test-owner.service" }},
]
unidad_memoria_aprobada = "test-memhog.service"
ocupantes_puerto_aprobados = ["test-occupier.service"]
directorio_informes = "/var/lib/doctorjk/informes"
modo_remediacion = "diagnostico"
auto_fix = false
dry_run = {dry_run}
timeout_comando_s = 30
llm_url = "https://proveedor.example/v1/chat/completions"
llm_modelo = "gpt-oss-120b"
llm_timeout_s = 30
llm_cache = false
"""


def _ejecutar_fix_real(
    tmp_path: Path,
    fix_script: Path,
    args: list[str],
    fakes: dict[str, str],
    dry_run: bool,
    entorno_extra: dict[str, str] | None = None,
    estado_previo: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    """Instala comun.sh + fix_script REALES (no dobles) más un config.toml
    completo, y corre el script con los dobles de sistema de `fakes`
    (nombre de comando -> contenido) y `stat` fijo en root/640. Devuelve el
    resultado y FAKE_STATE_DIR para que el test inspeccione qué se llamó.
    `estado_previo` pre-siembra archivos en ese directorio antes de correr
    (p. ej. para simular una unidad ya activa al entrar)."""
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    instalar_script(scripts_dir / "comun.sh", COMUN_SH.read_text(encoding="utf-8"))
    instalar_script(scripts_dir / fix_script.name, fix_script.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    instalar_script(fake_bin / "stat", FAKE_STAT)
    for nombre, contenido in fakes.items():
        instalar_script(fake_bin / nombre, contenido)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()
    for nombre, contenido in (estado_previo or {}).items():
        (fake_state / nombre).write_text(contenido, encoding="utf-8")

    config_path = tmp_path / "config.toml"
    config_path.write_text(_TOML_TEMPLATE.format(dry_run="true" if dry_run else "false"), encoding="utf-8")

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "TEST_STAT_OWNER": "root",
        "TEST_STAT_MODE": "640",
        "FAKE_STATE_DIR": str(fake_state),
        "DOCTORJK_CONFIG_PATH": str(config_path),
        "DOCTORJK_VENV_PYTHON": sys.executable,
        **(entorno_extra or {}),
    }
    resultado = subprocess.run(
        [str(scripts_dir / fix_script.name), *args],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )
    return resultado, fake_state


# --------------------------------------------------------------- servicio


def test_integracion_fix_servicio_camino_real(tmp_path: Path) -> None:
    resultado, fake_state = _ejecutar_fix_real(
        tmp_path,
        FIX_SERVICIO,
        ["test-svc.service"],
        fakes={"systemctl": FAKE_SYSTEMCTL_SERVICIO, "sleep": FAKE_SLEEP},
        dry_run=False,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "verificado: test-svc.service quedó activa" in resultado.stdout
    assert (fake_state / "service_active").exists()


def test_integracion_fix_servicio_dry_run_no_muta(tmp_path: Path) -> None:
    resultado, fake_state = _ejecutar_fix_real(
        tmp_path,
        FIX_SERVICIO,
        ["test-svc.service"],
        fakes={"systemctl": FAKE_SYSTEMCTL_SERVICIO, "sleep": FAKE_SLEEP},
        dry_run=True,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "[DRY-RUN] no ejecutado: systemctl restart test-svc.service" in resultado.stdout
    assert not (fake_state / "service_active").exists()


def test_integracion_fix_servicio_idempotente(tmp_path: Path) -> None:
    resultado, fake_state = _ejecutar_fix_real(
        tmp_path,
        FIX_SERVICIO,
        ["test-svc.service"],
        fakes={"systemctl": FAKE_SYSTEMCTL_SERVICIO, "sleep": FAKE_SLEEP},
        dry_run=False,
        estado_previo={"service_active": ""},
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "ya está activa; nada que corregir (idempotente)" in resultado.stdout
    assert not (fake_state / "systemctl_calls").exists() or "restart" not in (
        fake_state / "systemctl_calls"
    ).read_text(encoding="utf-8")


# ------------------------------------------------------------------ disco

# Variante mínima de FAKE_DF para el caso idempotente: bajo el umbral ya en
# la primera llamada, sin necesitar contador de estado.
_FAKE_DF_BAJO_UMBRAL = """#!/usr/bin/env bash
echo "Use%"
echo "60%"
"""


def _preparar_var_log(tmp_path: Path) -> Path:
    fake_var_log = tmp_path / "var-log"
    fake_var_log.mkdir()
    viejo_rotado = fake_var_log / "app.log.1.gz"
    viejo_rotado.write_bytes(b"contenido viejo")
    os.utime(viejo_rotado, (0, time.time() - 10 * 24 * 3600))  # 10 dias: calza -mtime +3
    return fake_var_log


def test_integracion_fix_disco_camino_real(tmp_path: Path) -> None:
    fake_var_log = _preparar_var_log(tmp_path)
    viejo_rotado = fake_var_log / "app.log.1.gz"

    resultado, _ = _ejecutar_fix_real(
        tmp_path,
        FIX_DISCO,
        ["/"],
        fakes={"df": FAKE_DF, "journalctl": FAKE_JOURNALCTL, "find": FAKE_FIND},
        dry_run=False,
        entorno_extra={"FAKE_VAR_LOG": str(fake_var_log)},
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "verificado: / bajó del umbral" in resultado.stdout
    assert not viejo_rotado.exists()


def test_integracion_fix_disco_dry_run_no_muta(tmp_path: Path) -> None:
    fake_var_log = _preparar_var_log(tmp_path)
    viejo_rotado = fake_var_log / "app.log.1.gz"

    resultado, _ = _ejecutar_fix_real(
        tmp_path,
        FIX_DISCO,
        ["/"],
        fakes={"df": FAKE_DF, "journalctl": FAKE_JOURNALCTL, "find": FAKE_FIND},
        dry_run=True,
        entorno_extra={"FAKE_VAR_LOG": str(fake_var_log)},
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "[DRY-RUN] no se verifica postcondición" in resultado.stdout
    assert viejo_rotado.exists()


def test_integracion_fix_disco_idempotente(tmp_path: Path) -> None:
    fake_var_log = _preparar_var_log(tmp_path)

    resultado, _ = _ejecutar_fix_real(
        tmp_path,
        FIX_DISCO,
        ["/"],
        fakes={"df": _FAKE_DF_BAJO_UMBRAL, "journalctl": FAKE_JOURNALCTL, "find": FAKE_FIND},
        dry_run=False,
        entorno_extra={"FAKE_VAR_LOG": str(fake_var_log)},
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "ya está bajo el umbral; nada que corregir (idempotente)" in resultado.stdout


# ------------------------------------------------------------------ puerto

# Alguien ya escucha desde la primera llamada (a diferencia de FAKE_SS/
# FAKE_SS_OCUPADO, que arrancan con el puerto libre o con un ocupante
# indebido) -- combinado con FAKE_SYSTEMCTL (status siempre devuelve
# TEST_EXPECTED_UNIT), simula que test-owner.service ya tiene el puerto.
_FAKE_SS_YA_TIENE = """#!/usr/bin/env bash
echo "State  Recv-Q Send-Q  Local Address:Port  Peer Address:Port Process"
echo "LISTEN 0 128 0.0.0.0:${TEST_PORT} 0.0.0.0:* users:((\\"proc\\",pid=9000,fd=3))"
"""

_ENTORNO_PUERTO_OCUPADO = {
    "TEST_PORT": "9999",
    "TEST_EXPECTED_UNIT": "test-owner.service",
    "TEST_OCCUPIER_UNIT": "test-occupier.service",
}


def test_integracion_fix_puerto_camino_real(tmp_path: Path) -> None:
    resultado, fake_state = _ejecutar_fix_real(
        tmp_path,
        FIX_PUERTO,
        ["9999"],
        fakes={"ss": FAKE_SS_OCUPADO, "systemctl": FAKE_SYSTEMCTL_PUERTO_OCUPADO, "sleep": FAKE_SLEEP},
        dry_run=False,
        entorno_extra=_ENTORNO_PUERTO_OCUPADO,
    )
    llamadas = (fake_state / "systemctl_calls").read_text(encoding="utf-8")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "stop test-occupier.service" in llamadas
    assert "restart test-owner.service" in llamadas
    assert "verificado con ss" in resultado.stdout


def test_integracion_fix_puerto_dry_run_no_muta(tmp_path: Path) -> None:
    resultado, fake_state = _ejecutar_fix_real(
        tmp_path,
        FIX_PUERTO,
        ["9999"],
        fakes={"ss": FAKE_SS_OCUPADO, "systemctl": FAKE_SYSTEMCTL_PUERTO_OCUPADO, "sleep": FAKE_SLEEP},
        dry_run=True,
        entorno_extra=_ENTORNO_PUERTO_OCUPADO,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "[DRY-RUN] no se verifica postcondición" in resultado.stdout
    assert "stop test-occupier.service" not in (fake_state / "systemctl_calls").read_text(encoding="utf-8")


def test_integracion_fix_puerto_idempotente(tmp_path: Path) -> None:
    resultado, fake_state = _ejecutar_fix_real(
        tmp_path,
        FIX_PUERTO,
        ["9999"],
        fakes={"ss": _FAKE_SS_YA_TIENE, "systemctl": FAKE_SYSTEMCTL, "sleep": FAKE_SLEEP},
        dry_run=False,
        entorno_extra=_ENTORNO_PUERTO_OCUPADO,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "ya tiene el puerto 9999; nada que corregir (idempotente)" in resultado.stdout
    assert not (fake_state / "systemctl_calls").exists() or "stop" not in (
        fake_state / "systemctl_calls"
    ).read_text(encoding="utf-8")


# ----------------------------------------------------------------- memoria

_ENTORNO_MEMORIA_REAL = {"TEST_UNIT_MEMORY_BYTES": str(500 * 1024 * 1024)}


def test_integracion_fix_memoria_camino_real(tmp_path: Path) -> None:
    resultado, fake_state = _ejecutar_fix_real(
        tmp_path,
        FIX_MEMORIA,
        [],
        fakes={"free": FAKE_FREE, "systemctl": FAKE_SYSTEMCTL_MEMORIA, "sleep": FAKE_SLEEP},
        dry_run=False,
        entorno_extra=_ENTORNO_MEMORIA_REAL,
    )
    llamadas = (fake_state / "systemctl_calls").read_text(encoding="utf-8")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "restart test-memhog.service" in llamadas
    assert "verificado: memoria disponible sobre el umbral" in resultado.stdout
    assert (fake_state / "memoria_liberada").exists()


def test_integracion_fix_memoria_dry_run_no_muta(tmp_path: Path) -> None:
    resultado, fake_state = _ejecutar_fix_real(
        tmp_path,
        FIX_MEMORIA,
        [],
        fakes={"free": FAKE_FREE, "systemctl": FAKE_SYSTEMCTL_MEMORIA, "sleep": FAKE_SLEEP},
        dry_run=True,
        entorno_extra=_ENTORNO_MEMORIA_REAL,
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "[DRY-RUN] no ejecutado: systemctl restart test-memhog.service" in resultado.stdout
    assert not (fake_state / "memoria_liberada").exists()


def test_integracion_fix_memoria_idempotente(tmp_path: Path) -> None:
    resultado, fake_state = _ejecutar_fix_real(
        tmp_path,
        FIX_MEMORIA,
        [],
        fakes={"free": FAKE_FREE, "systemctl": FAKE_SYSTEMCTL_MEMORIA, "sleep": FAKE_SLEEP},
        dry_run=False,
        entorno_extra={"TEST_AVAILABLE_BEFORE": "600"},  # ya por sobre el umbral de 512
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "ya hay memoria suficiente; nada que corregir (idempotente)" in resultado.stdout
    assert not (fake_state / "systemctl_calls").exists()
