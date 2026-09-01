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
# se prueba acá es la lógica de decisión de cada fix_*.sh, no la
# verificación de dueño/permisos de comun.sh.
#
# **Esa verificación (_verify_config_ownership) SÍ tiene su propia cobertura
# directa, contra el comun.sh real, en test_comun_permisos.py.** Hasta el
# hallazgo de auditoría en vivo del 2026-09-01 se asumía que "bash -n,
# shellcheck -x, revisión de código" alcanzaba para esa función -- resultó
# falso: un bug de aritmética (mezclar la conversión octal->decimal de
# `8#$mode` con extracción de dígitos decimales) hacía que el modo real que
# pone install.sh (0640) fallara SIEMPRE, y ningún test lo detectó porque
# ninguno ejecutaba la función real. `bash -n` solo valida sintaxis, nunca
# semántica aritmética.
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from ayudantes import (
    FAKE_DF,
    FAKE_FIND,
    FAKE_FREE,
    FAKE_JOURNALCTL,
    FAKE_SLEEP,
    FAKE_SS,
    FAKE_SS_OCUPADO,
    FAKE_SYSTEMCTL,
    FAKE_SYSTEMCTL_MEMORIA,
    FAKE_SYSTEMCTL_PUERTO_OCUPADO,
    FAKE_SYSTEMCTL_SERVICIO,
    FIX_DISCO,
    FIX_MEMORIA,
    FIX_PUERTO,
    FIX_SERVICIO,
)
from ayudantes import instalar_script as _instalar

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
    approved_port_occupants) echo "${TEST_APPROVED_PORT_OCCUPANTS:-}" ;;
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
    _instalar(fake_bin / "ss", FAKE_SS)
    _instalar(fake_bin / "systemctl", FAKE_SYSTEMCTL)
    _instalar(fake_bin / "sleep", FAKE_SLEEP)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_STATE_DIR": str(fake_state),
        "TEST_PORT": "5432",
        "TEST_EXPECTED_UNIT": "postgresql@16-main.service",
        "TEST_MONITORED_PORTS": "5432=postgresql@16-main.service",
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
    _instalar(fake_bin / "ss", FAKE_SS)
    _instalar(fake_bin / "systemctl", FAKE_SYSTEMCTL)
    _instalar(fake_bin / "sleep", FAKE_SLEEP)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_STATE_DIR": str(fake_state),
        "TEST_PORT": "5432",
        "TEST_EXPECTED_UNIT": "postgresql@16-main.service",
        "TEST_MONITORED_PORTS": "5432=postgresql@16-main.service",
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


def test_fix_puerto_falla_cerrado_si_ocupante_vigilado_pero_no_aprobado(tmp_path: Path):
    # Hallazgo de auditoría P0 (2026-09-01): fix_puerto.sh NO debe autorizar
    # a detener un ocupante solo porque está en servicios_vigilados -- esa
    # lista dice qué vigilar, no qué está aprobado para detener. Estar
    # vigilado pero NO en ocupantes_puerto_aprobados debe fallar cerrado.
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", _FAKE_COMUN_SH)
    _instalar(scripts_dir / "fix_puerto.sh", FIX_PUERTO.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "ss", FAKE_SS_OCUPADO)
    _instalar(fake_bin / "systemctl", FAKE_SYSTEMCTL_PUERTO_OCUPADO)
    _instalar(fake_bin / "sleep", FAKE_SLEEP)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_STATE_DIR": str(fake_state),
        "TEST_PORT": "18080",
        "TEST_EXPECTED_UNIT": "doctorjk-test-owner.service",
        "TEST_OCCUPIER_UNIT": "doctorjk-test-occupier.service",
        "TEST_MONITORED_PORTS": "18080=doctorjk-test-owner.service",
        "TEST_MONITORED_SERVICES": "doctorjk-test-occupier.service",  # vigilado...
        "TEST_APPROVED_PORT_OCCUPANTS": "",  # ...pero NO aprobado para detener
        "TEST_DRY_RUN": "0",
    }

    resultado = subprocess.run(
        [str(scripts_dir / "fix_puerto.sh"), "18080"],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    assert resultado.returncode != 0
    assert "no está en ocupantes_puerto_aprobados" in resultado.stderr
    assert not (fake_state / "systemctl_calls").exists() or (
        "stop" not in (fake_state / "systemctl_calls").read_text(encoding="utf-8")
        and "restart" not in (fake_state / "systemctl_calls").read_text(encoding="utf-8")
    )


def test_fix_puerto_detiene_ocupante_aprobado_aunque_no_este_vigilado(tmp_path: Path):
    # La otra mitad del mismo hallazgo: estar en ocupantes_puerto_aprobados
    # alcanza para autorizar, sin necesidad de estar también en
    # servicios_vigilados -- las dos listas son independientes.
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", _FAKE_COMUN_SH)
    _instalar(scripts_dir / "fix_puerto.sh", FIX_PUERTO.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "ss", FAKE_SS_OCUPADO)
    _instalar(fake_bin / "systemctl", FAKE_SYSTEMCTL_PUERTO_OCUPADO)
    _instalar(fake_bin / "sleep", FAKE_SLEEP)

    fake_state = tmp_path / "estado"
    fake_state.mkdir()

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "FAKE_STATE_DIR": str(fake_state),
        "TEST_PORT": "18080",
        "TEST_EXPECTED_UNIT": "doctorjk-test-owner.service",
        "TEST_OCCUPIER_UNIT": "doctorjk-test-occupier.service",
        "TEST_MONITORED_PORTS": "18080=doctorjk-test-owner.service",
        "TEST_MONITORED_SERVICES": "",  # NO vigilado...
        "TEST_APPROVED_PORT_OCCUPANTS": "doctorjk-test-occupier.service",  # ...pero sí aprobado
        "TEST_DRY_RUN": "0",
    }

    resultado = subprocess.run(
        [str(scripts_dir / "fix_puerto.sh"), "18080"],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )

    llamadas = (fake_state / "systemctl_calls").read_text(encoding="utf-8")
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "stop doctorjk-test-occupier.service" in llamadas
    assert "restart doctorjk-test-owner.service" in llamadas
    assert "verificado con ss" in resultado.stdout


# --------------------------------------------------------------- fix_disco.sh


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
    _instalar(fake_bin / "df", FAKE_DF)
    _instalar(fake_bin / "journalctl", FAKE_JOURNALCTL)
    _instalar(fake_bin / "find", FAKE_FIND)

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
    _instalar(fake_bin / "df", FAKE_DF)
    _instalar(fake_bin / "journalctl", FAKE_JOURNALCTL)
    _instalar(fake_bin / "find", FAKE_FIND)

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


def _preparar_fix_servicio(tmp_path: Path, ya_activa: bool) -> tuple[Path, dict, Path]:
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", _FAKE_COMUN_SH)
    _instalar(scripts_dir / "fix_servicio.sh", FIX_SERVICIO.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "systemctl", FAKE_SYSTEMCTL_SERVICIO)
    _instalar(fake_bin / "sleep", FAKE_SLEEP)

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


def _preparar_fix_memoria(tmp_path: Path, **overrides) -> tuple[Path, dict, Path]:
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", _FAKE_COMUN_SH)
    _instalar(scripts_dir / "fix_memoria.sh", FIX_MEMORIA.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "free", FAKE_FREE)
    _instalar(fake_bin / "systemctl", FAKE_SYSTEMCTL_MEMORIA)
    _instalar(fake_bin / "sleep", FAKE_SLEEP)

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
