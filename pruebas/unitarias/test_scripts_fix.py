# Pruebas de integración de scripts-fix/*.sh reales (no dobles sintéticos).
#
# comun.sh real exige que config.toml sea root-owned (defensa contra
# fabricar la política vista por un script que corre como root, hallazgo de
# auditoría #1-bis) -- eso hace imposible probar el script REAL de punta a
# punta sin privilegios de root, que este entorno de pruebas no tiene y no
# debe intentar obtener (sin sudo real en pruebas locales). Por eso estas
# pruebas usan un DOBLE de comun.sh que expone la misma interfaz
# (read_config_attr, is_dry_run, run_or_announce, list_contains, log, fail)
# respaldada por variables de entorno en vez de leer un TOML real -- lo que
# se prueba es la lógica de decisión de cada fix_*.sh, no la verificación de
# dueño/permisos de comun.sh, que ya tiene su propia cobertura (bash -n,
# shellcheck -x, revisión de código).
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
FIX_PUERTO = REPO_ROOT / "scripts-fix" / "fix_puerto.sh"

_FAKE_COMUN_SH = """#!/usr/bin/env bash
# Doble de prueba de comun.sh -- NO verifica dueño/permisos de nada; la
# política sale de variables TEST_* que arma el test Python. Vive solo en
# pruebas/, nunca se instala ni se commitea a scripts-fix/.
log() { printf '[%s] %s\\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { printf '[%s] ERROR: %s\\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; exit 1; }
read_config_attr() {
  case "$1" in
    dry_run) echo "${TEST_DRY_RUN:-0}" ;;
    monitored_services) echo "${TEST_MONITORED_SERVICES:-}" ;;
    monitored_ports) echo "${TEST_MONITORED_PORTS:-}" ;;
    disk_pct_threshold) echo "${TEST_DISK_THRESHOLD:-90}" ;;
    memory_available_mb_threshold) echo "${TEST_MEMORY_THRESHOLD:-512}" ;;
    approved_memory_unit) echo "${TEST_APPROVED_MEMORY_UNIT:-}" ;;
    *) echo "" ;;
  esac
}
is_dry_run() { [[ "$(read_config_attr dry_run)" == "1" ]]; }
run_or_announce() {
  if is_dry_run; then log "[DRY-RUN] no ejecutado: $*"; return 0; fi
  log "ejecutando: $*"
  "$@"
}
list_contains() {
  local needle="$1" list="$2" item
  IFS=',' read -ra items <<< "$list"
  for item in "${items[@]}"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}
"""

_FAKE_SS = """#!/usr/bin/env bash
# Nadie escucha en la primera llamada (precondición); alguien escucha desde
# la segunda en adelante (postcondición, simulando que systemctl restart
# de verdad hizo bind del puerto).
count_file="$FAKE_STATE_DIR/ss_calls"
count=0
[[ -f "$count_file" ]] && count="$(cat "$count_file")"
count=$((count + 1))
echo "$count" > "$count_file"
echo "State  Recv-Q Send-Q  Local Address:Port  Peer Address:Port Process"
if (( count >= 2 )); then
  echo "LISTEN 0 128 0.0.0.0:${TEST_PORT} 0.0.0.0:* users:((\\"proc\\",pid=4242,fd=3))"
fi
"""

_FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_STATE_DIR/systemctl_calls"
case "$1" in
  is-active) exit 0 ;;
  status) echo "\xe2\x97\x8f ${TEST_EXPECTED_UNIT} - fake unit"; exit 0 ;;
  restart|stop) exit 0 ;;
  *) exit 0 ;;
esac
"""

_FAKE_SLEEP = """#!/usr/bin/env bash
exit 0
"""


def _instalar(ruta: Path, contenido: str) -> None:
    ruta.write_text(contenido, encoding="utf-8")
    ruta.chmod(ruta.stat().st_mode | stat.S_IEXEC)


def test_fix_puerto_reinicia_y_verifica_aunque_nadie_escuche_al_empezar(tmp_path: Path):
    # Revisión post-commit (2026-09-01): si el ocupante indebido ya
    # desapareció solo entre la detección y esta corrida, el script NO debe
    # declarar "nada que corregir" con solo un exit 0 -- eso dejaría a la
    # unidad esperada sin el puerto. Debe reiniciarla igual y verificar con
    # ss que quedó escuchando.
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", _FAKE_COMUN_SH)
    _instalar(scripts_dir / "fix_puerto.sh", FIX_PUERTO.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "ss", _FAKE_SS)
    _instalar(fake_bin / "systemctl", _FAKE_SYSTEMCTL)
    _instalar(fake_bin / "sleep", _FAKE_SLEEP)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_STATE_DIR": str(fake_state),
        "TEST_PORT": "5432",
        "TEST_EXPECTED_UNIT": "postgresql@16-main.service",
        "TEST_MONITORED_PORTS": "5432=postgresql@16-main.service",
        "TEST_MONITORED_SERVICES": "postgresql@16-main.service",
        "TEST_DRY_RUN": "0",
    }

    resultado = subprocess.run(
        [str(scripts_dir / "fix_puerto.sh"), "5432"],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    llamadas_systemctl = (fake_state / "systemctl_calls").read_text(encoding="utf-8")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "restart postgresql@16-main.service" in llamadas_systemctl
    assert "verificado con ss" in resultado.stdout


def test_fix_puerto_en_dry_run_solo_anuncia_aunque_nadie_escuche(tmp_path: Path):
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", _FAKE_COMUN_SH)
    _instalar(scripts_dir / "fix_puerto.sh", FIX_PUERTO.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "ss", _FAKE_SS)
    _instalar(fake_bin / "systemctl", _FAKE_SYSTEMCTL)
    _instalar(fake_bin / "sleep", _FAKE_SLEEP)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_STATE_DIR": str(fake_state),
        "TEST_PORT": "5432",
        "TEST_EXPECTED_UNIT": "postgresql@16-main.service",
        "TEST_MONITORED_PORTS": "5432=postgresql@16-main.service",
        "TEST_MONITORED_SERVICES": "postgresql@16-main.service",
        "TEST_DRY_RUN": "1",
    }

    resultado = subprocess.run(
        [str(scripts_dir / "fix_puerto.sh"), "5432"],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "[DRY-RUN] no ejecutado: systemctl restart postgresql@16-main.service" in resultado.stdout
    assert not (fake_state / "systemctl_calls").exists() or "restart" not in (
        fake_state / "systemctl_calls"
    ).read_text(encoding="utf-8")
