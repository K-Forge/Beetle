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
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
FIX_PUERTO = REPO_ROOT / "scripts-fix" / "fix_puerto.sh"
FIX_DISCO = REPO_ROOT / "scripts-fix" / "fix_disco.sh"
FIX_SERVICIO = REPO_ROOT / "scripts-fix" / "fix_servicio.sh"
FIX_MEMORIA = REPO_ROOT / "scripts-fix" / "fix_memoria.sh"

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


# --------------------------------------------------------------- fix_disco.sh

_FAKE_DF = """#!/usr/bin/env bash
# Primera llamada: sobre el umbral (dispara la limpieza). Segunda en
# adelante: bajo el umbral (simula que la limpieza sí liberó espacio).
count_file="$FAKE_STATE_DIR/df_calls"
count=0
[[ -f "$count_file" ]] && count="$(cat "$count_file")"
count=$((count + 1))
echo "$count" > "$count_file"
echo "Use%"
if (( count == 1 )); then
  echo "95%"
else
  echo "60%"
fi
"""

_FAKE_JOURNALCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_STATE_DIR/journalctl_calls"
exit 0
"""

_FAKE_FIND = """#!/usr/bin/env bash
# Traduce /var/log al directorio de prueba FAKE_VAR_LOG y delega en el
# find real -- así fix_disco.sh corre su búsqueda de verdad (mismos
# argumentos, mismo -print0), solo que contra archivos de prueba, no el
# filesystem real de la máquina que corre las pruebas.
args=("$@")
if [[ "${args[0]}" == "/var/log" ]]; then
  args[0]="$FAKE_VAR_LOG"
fi
exec /usr/bin/find "${args[@]}"
"""


def test_fix_disco_lista_candidatos_antes_de_borrar(tmp_path: Path):
    # Gate 4.2 exige listar candidatos antes de aplicar la política de
    # retención; un `find -delete` silencioso no deja ese rastro (hallazgo
    # de auditoría, 2026-09-01).
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", _FAKE_COMUN_SH)
    _instalar(scripts_dir / "fix_disco.sh", FIX_DISCO.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "df", _FAKE_DF)
    _instalar(fake_bin / "journalctl", _FAKE_JOURNALCTL)
    _instalar(fake_bin / "find", _FAKE_FIND)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()

    fake_var_log = tmp_path / "var-log"
    fake_var_log.mkdir()
    viejo_rotado = fake_var_log / "app.log.1.gz"
    viejo_rotado.write_bytes(b"contenido viejo")
    # mtime de hace 10 dias: debe calzar con -mtime +3.
    diez_dias = 10 * 24 * 3600
    os.utime(viejo_rotado, (0, time.time() - diez_dias))
    log_activo = fake_var_log / "app.log"
    log_activo.write_text("log activo, no se toca", encoding="utf-8")

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_STATE_DIR": str(fake_state),
        "FAKE_VAR_LOG": str(fake_var_log),
        "TEST_DRY_RUN": "0",
        "TEST_DISK_THRESHOLD": "90",
    }

    resultado = subprocess.run(
        [str(scripts_dir / "fix_disco.sh"), "/"],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert f"candidato: {viejo_rotado}" in resultado.stdout
    assert not viejo_rotado.exists(), "el candidato rotado debía eliminarse"
    assert log_activo.exists(), "un log activo sin rotar nunca se toca"
    assert f"removed '{viejo_rotado}'" in resultado.stdout  # rm -v confirma el borrado real


def test_fix_disco_en_dry_run_no_borra_nada(tmp_path: Path):
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", _FAKE_COMUN_SH)
    _instalar(scripts_dir / "fix_disco.sh", FIX_DISCO.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "df", _FAKE_DF)
    _instalar(fake_bin / "journalctl", _FAKE_JOURNALCTL)
    _instalar(fake_bin / "find", _FAKE_FIND)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()

    fake_var_log = tmp_path / "var-log"
    fake_var_log.mkdir()
    viejo_rotado = fake_var_log / "app.log.1.gz"
    viejo_rotado.write_bytes(b"contenido viejo")
    os.utime(viejo_rotado, (0, time.time() - 10 * 24 * 3600))

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_STATE_DIR": str(fake_state),
        "FAKE_VAR_LOG": str(fake_var_log),
        "TEST_DRY_RUN": "1",
        "TEST_DISK_THRESHOLD": "90",
    }

    resultado = subprocess.run(
        [str(scripts_dir / "fix_disco.sh"), "/"],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert f"candidato: {viejo_rotado}" in resultado.stdout  # se lista igual
    assert viejo_rotado.exists(), "dry-run nunca borra de verdad"


# ------------------------------------------------------------ fix_servicio.sh

_FAKE_SYSTEMCTL_SERVICIO = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_STATE_DIR/systemctl_calls"
state_file="$FAKE_STATE_DIR/service_active"
case "$1" in
  is-active)
    if [[ -f "$state_file" ]]; then exit 0; else exit 3; fi
    ;;
  restart)
    touch "$state_file"
    exit 0
    ;;
  *) exit 0 ;;
esac
"""


def _preparar_fix_servicio(tmp_path: Path, ya_activa: bool) -> tuple[Path, dict, Path]:
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", _FAKE_COMUN_SH)
    _instalar(scripts_dir / "fix_servicio.sh", FIX_SERVICIO.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "systemctl", _FAKE_SYSTEMCTL_SERVICIO)
    _instalar(fake_bin / "sleep", _FAKE_SLEEP)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()
    if ya_activa:
        (fake_state / "service_active").write_text("", encoding="utf-8")

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_STATE_DIR": str(fake_state),
        "TEST_MONITORED_SERVICES": "postgresql@16-main.service",
    }
    return scripts_dir, entorno, fake_state


def test_fix_servicio_reinicia_y_verifica_postcondicion(tmp_path: Path):
    scripts_dir, entorno, fake_state = _preparar_fix_servicio(tmp_path, ya_activa=False)
    entorno["TEST_DRY_RUN"] = "0"

    resultado = subprocess.run(
        [str(scripts_dir / "fix_servicio.sh"), "postgresql@16-main.service"],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    llamadas = (fake_state / "systemctl_calls").read_text(encoding="utf-8")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "restart postgresql@16-main.service" in llamadas
    assert "verificado: postgresql@16-main.service quedó activa" in resultado.stdout
    assert (fake_state / "service_active").exists(), "la postcondición debe reflejar el reinicio real"


def test_fix_servicio_dry_run_no_muta(tmp_path: Path):
    scripts_dir, entorno, fake_state = _preparar_fix_servicio(tmp_path, ya_activa=False)
    entorno["TEST_DRY_RUN"] = "1"

    resultado = subprocess.run(
        [str(scripts_dir / "fix_servicio.sh"), "postgresql@16-main.service"],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "[DRY-RUN] no ejecutado: systemctl restart postgresql@16-main.service" in resultado.stdout
    assert "no se verifica postcondición" in resultado.stdout
    assert not (fake_state / "service_active").exists(), "dry-run nunca debe reiniciar de verdad"


def test_fix_servicio_idempotente_si_ya_esta_activa(tmp_path: Path):
    scripts_dir, entorno, fake_state = _preparar_fix_servicio(tmp_path, ya_activa=True)
    entorno["TEST_DRY_RUN"] = "0"

    resultado = subprocess.run(
        [str(scripts_dir / "fix_servicio.sh"), "postgresql@16-main.service"],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "ya está activa; nada que corregir (idempotente)" in resultado.stdout
    llamadas = (fake_state / "systemctl_calls").read_text(encoding="utf-8")
    assert "restart" not in llamadas, "no debe reiniciar algo que ya estaba sano"


# ------------------------------------------------------------- fix_memoria.sh

_FAKE_FREE = """#!/usr/bin/env bash
if [[ -f "$FAKE_STATE_DIR/memoria_liberada" ]]; then
  available="${TEST_AVAILABLE_AFTER:-1000}"
else
  available="${TEST_AVAILABLE_BEFORE:-100}"
fi
echo "              total        used        free      shared  buff/cache   available"
echo "Mem:           3900        2000         500          10         1400       $available"
echo "Swap:             0           0           0"
"""

_FAKE_SYSTEMCTL_MEMORIA = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_STATE_DIR/systemctl_calls"
case "$1" in
  show) echo "${TEST_UNIT_MEMORY_BYTES:-0}" ;;
  restart) touch "$FAKE_STATE_DIR/memoria_liberada"; exit 0 ;;
  *) exit 0 ;;
esac
"""


def _preparar_fix_memoria(tmp_path: Path, **overrides) -> tuple[Path, dict, Path]:
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", _FAKE_COMUN_SH)
    _instalar(scripts_dir / "fix_memoria.sh", FIX_MEMORIA.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "free", _FAKE_FREE)
    _instalar(fake_bin / "systemctl", _FAKE_SYSTEMCTL_MEMORIA)
    _instalar(fake_bin / "sleep", _FAKE_SLEEP)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_STATE_DIR": str(fake_state),
        "TEST_APPROVED_MEMORY_UNIT": "appcarga.service",
        "TEST_MEMORY_THRESHOLD": "512",
        "TEST_AVAILABLE_BEFORE": "100",
        "TEST_AVAILABLE_AFTER": "1000",
        "TEST_DRY_RUN": "0",
    }
    entorno.update(overrides)
    return scripts_dir, entorno, fake_state


def test_fix_memoria_reinicia_y_verifica_postcondicion(tmp_path: Path):
    # déficit = 512 - 100 = 412 MB; la unidad usa 500 MB, cubre el déficit.
    scripts_dir, entorno, fake_state = _preparar_fix_memoria(
        tmp_path, TEST_UNIT_MEMORY_BYTES=str(500 * 1024 * 1024)
    )

    resultado = subprocess.run(
        [str(scripts_dir / "fix_memoria.sh")],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    llamadas = (fake_state / "systemctl_calls").read_text(encoding="utf-8")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "restart appcarga.service" in llamadas
    assert "verificado: memoria disponible sobre el umbral" in resultado.stdout
    assert (fake_state / "memoria_liberada").exists()


def test_fix_memoria_dry_run_no_muta(tmp_path: Path):
    scripts_dir, entorno, fake_state = _preparar_fix_memoria(
        tmp_path, TEST_UNIT_MEMORY_BYTES=str(500 * 1024 * 1024), TEST_DRY_RUN="1"
    )

    resultado = subprocess.run(
        [str(scripts_dir / "fix_memoria.sh")],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "[DRY-RUN] no ejecutado: systemctl restart appcarga.service" in resultado.stdout
    assert "no se verifica postcondición" in resultado.stdout
    assert not (fake_state / "memoria_liberada").exists(), "dry-run nunca debe reiniciar de verdad"


def test_fix_memoria_idempotente_si_ya_hay_memoria_suficiente(tmp_path: Path):
    scripts_dir, entorno, fake_state = _preparar_fix_memoria(
        tmp_path, TEST_AVAILABLE_BEFORE="600"  # ya por sobre el umbral de 512
    )

    resultado = subprocess.run(
        [str(scripts_dir / "fix_memoria.sh")],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "ya hay memoria suficiente; nada que corregir (idempotente)" in resultado.stdout
    # Ni siquiera debe haber consultado el cgroup de la unidad aprobada.
    assert not (fake_state / "systemctl_calls").exists()


def test_fix_memoria_falla_cerrado_si_cgroup_no_cubre_el_deficit(tmp_path: Path):
    # Lo que pide la revisión: el fallo cerrado cuando la unidad aprobada no
    # concentra memoria suficiente para siquiera poder cubrir el déficit.
    # déficit = 512 - 100 = 412 MB; la unidad solo usa 50 MB.
    scripts_dir, entorno, fake_state = _preparar_fix_memoria(
        tmp_path, TEST_UNIT_MEMORY_BYTES=str(50 * 1024 * 1024)
    )

    resultado = subprocess.run(
        [str(scripts_dir / "fix_memoria.sh")],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    assert resultado.returncode != 0
    assert "no alcanzaría a cruzar el umbral" in resultado.stderr
    assert not (fake_state / "memoria_liberada").exists(), "no debe reiniciar si no puede ayudar"
    llamadas = (fake_state / "systemctl_calls").read_text(encoding="utf-8")
    assert "restart" not in llamadas


def test_fix_memoria_sin_unidad_aprobada_escala_sin_actuar(tmp_path: Path):
    scripts_dir, entorno, fake_state = _preparar_fix_memoria(
        tmp_path, TEST_APPROVED_MEMORY_UNIT=""
    )

    resultado = subprocess.run(
        [str(scripts_dir / "fix_memoria.sh")],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    assert resultado.returncode != 0
    assert "sin unidad_memoria_aprobada configurada" in resultado.stderr
    assert not fake_state.joinpath("systemctl_calls").exists()
