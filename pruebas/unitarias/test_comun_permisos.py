# Cobertura directa de _verify_config_ownership en scripts-fix/comun.sh real
# (no un doble). Corrige el hueco de test_scripts_fix.py: hasta el hallazgo
# de auditoría en vivo del 2026-09-01, esta función nunca se ejecutaba en
# ningún test -- un bug de aritmética (8#$mode ya convierte octal->decimal;
# aplicarle /10%10 y %10 después extrae dígitos DECIMALES del resultado, no
# los dígitos OCTALES de $mode) hacía que el modo real que pone install.sh
# (0640) fallara SIEMPRE, sin que "bash -n, shellcheck -x, revisión de
# código" lo detectara -- ninguno de esos tres ejecuta la aritmética.
#
# No se puede chown/chmod un archivo real a root sin sudo, así que se fuerza
# lo que _verify_config_ownership ve con un `stat` falso en PATH (mismo
# patrón que test_scripts_fix.py usa para systemctl/ss/df/find), controlado
# por TEST_STAT_OWNER/TEST_STAT_MODE. El intérprete Python no se llega a
# invocar en estas pruebas -- comun.sh falla o sigue de largo antes de que
# read_config_attr lo use -- pero igual necesita existir y ser ejecutable
# para pasar el chequeo `[[ -x "$VENV_PYTHON" ]]` previo.
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from ayudantes import COMUN_SH, FAKE_STAT
from ayudantes import instalar_script as _instalar

_RUNNER_SH = """#!/usr/bin/env bash
# Sourcear comun.sh dispara _verify_config_ownership al final del propio
# archivo (no es una función que se llame aparte) -- reproduce exactamente
# cómo lo invoca cada fix_*.sh real.
source "$1"
echo SOURCED_OK
"""


def _fuente_comun_real(tmp_path: Path, owner: str, mode: str) -> subprocess.CompletedProcess[str]:
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", COMUN_SH.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "stat", FAKE_STAT)

    runner = tmp_path / "runner.sh"
    _instalar(runner, _RUNNER_SH)

    config_path = tmp_path / "config.toml"
    config_path.write_text("", encoding="utf-8")

    venv_python = tmp_path / "venv-python-stub"
    _instalar(venv_python, "#!/usr/bin/env bash\nexit 0\n")

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "TEST_STAT_OWNER": owner,
        "TEST_STAT_MODE": mode,
        "DOCTORJK_CONFIG_PATH": str(config_path),
        "DOCTORJK_VENV_PYTHON": str(venv_python),
    }
    return subprocess.run(
        [str(runner), str(scripts_dir / "comun.sh")],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )


# 0640 es el modo real que install.sh pone sobre config.toml (chmod 0640) --
# el caso que el bug rompía siempre. 4640/1644 agregan setuid/sticky para
# confirmar que la máscara octal ignora bits fuera de grupo/otros-escritura
# en vez de tropezar con un cuarto dígito en %a.
@pytest.mark.parametrize("mode", ["640", "600", "444", "4640", "1644"])
def test_verify_config_ownership_acepta_modos_sin_escritura_de_grupo_u_otros(
    tmp_path: Path, mode: str
) -> None:
    resultado = _fuente_comun_real(tmp_path, owner="root", mode=mode)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert "SOURCED_OK" in resultado.stdout


@pytest.mark.parametrize("mode", ["660", "642", "666"])
def test_verify_config_ownership_rechaza_modos_escribibles_por_grupo_u_otros(
    tmp_path: Path, mode: str
) -> None:
    resultado = _fuente_comun_real(tmp_path, owner="root", mode=mode)
    assert resultado.returncode != 0
    assert "permisos de escritura demasiado amplios" in resultado.stderr
    assert f"modo {mode}" in resultado.stderr


def test_verify_config_ownership_rechaza_dueno_no_root(tmp_path: Path) -> None:
    resultado = _fuente_comun_real(tmp_path, owner="beetle", mode="640")
    assert resultado.returncode != 0
    assert "no es propiedad de root" in resultado.stderr


# ------------------------------------------------------- read_config_attr()
#
# Segunda P0 de auditoría (2026-09-01, detectada en local antes de volver al
# VPS): read_config_attr llamaba a `load_config(sys.argv[1])` con
# sys.argv[1] crudo (un str) -- el mismo bug ya corregido en install.sh
# (load_config exige Path y llama path.read_bytes()). Cualquier fix_*.sh
# que llegara a pasar _verify_config_ownership habría reventado en la
# primera lectura de config real (dry_run incluido, que TODOS consultan) --
# lo habría atrapado el intento en vivo apenas se corrigiera el hallazgo
# anterior. Se corrige acá y se reproduce/confirma offline, sin VPS.
#
# Esto sí necesita el intérprete REAL del venv del repo (no el stub que
# usan las pruebas de arriba): read_config_attr importa doctorjk.config de
# verdad. Se usa sys.executable -- el intérprete que corre pytest -- en vez
# de hardcodear ".venv/bin/python3": es el mismo intérprete en este repo, y
# no rompe si el venv algún día se llama distinto.
_TOML_COMPLETO = """
intervalo_monitor_s = 30
ciclos_persistencia = 2
enfriamiento_ciclos = 2
disco_pct = 90
puntos_montaje_vigilados = ["/", "/var"]
memoria_disponible_mb = 512
puerto_timeout_s = 60
servicio_ciclos = 2
servicios_vigilados = ["nginx.service", "postgresql.service"]
puertos_vigilados = [
  { puerto = 80, servicio = "nginx.service" },
  { puerto = 5432, servicio = "postgresql.service" },
]
unidad_memoria_aprobada = "appcarga.service"
ocupantes_puerto_aprobados = ["intruso.service"]
directorio_informes = "/var/lib/doctorjk/informes"
modo_remediacion = "diagnostico"
auto_fix = false
dry_run = true
timeout_comando_s = 30
llm_url = "https://proveedor.example/v1/chat/completions"
llm_modelo = "gpt-oss-120b"
llm_timeout_s = 30
llm_cache = false
"""

_RUNNER_READ_ATTR_SH = """#!/usr/bin/env bash
# Sourcea el comun.sh real (dispara _verify_config_ownership de paso, igual
# que en producción) y despues llama a read_config_attr($2) sobre él.
source "$1"
read_config_attr "$2"
"""


def _leer_atributo_real(tmp_path: Path, atributo: str, toml_text: str) -> subprocess.CompletedProcess[str]:
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", COMUN_SH.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "stat", FAKE_STAT)

    runner = tmp_path / "runner.sh"
    _instalar(runner, _RUNNER_READ_ATTR_SH)

    config_path = tmp_path / "config.toml"
    config_path.write_text(toml_text, encoding="utf-8")

    entorno = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "TEST_STAT_OWNER": "root",
        "TEST_STAT_MODE": "640",
        "DOCTORJK_CONFIG_PATH": str(config_path),
        "DOCTORJK_VENV_PYTHON": sys.executable,
    }
    return subprocess.run(
        [str(runner), str(scripts_dir / "comun.sh"), atributo],
        capture_output=True,
        text=True,
        env=entorno,
        timeout=10,
    )


@pytest.mark.parametrize(
    ("atributo", "esperado"),
    [
        ("dry_run", "1"),
        ("disk_pct_threshold", "90"),
        ("monitored_ports", "80=nginx.service,5432=postgresql.service"),
        # Las tres listas nuevas de Gate 4/4.4 -- justo las que la migración
        # de install.sh agrega y que dispararon el hallazgo P0 anterior.
        ("monitored_mount_points", "/,/var"),
        ("approved_memory_unit", "appcarga.service"),
        ("approved_port_occupants", "intruso.service"),
    ],
)
def test_read_config_attr_real_lee_config_valida(tmp_path: Path, atributo: str, esperado: str) -> None:
    resultado = _leer_atributo_real(tmp_path, atributo, _TOML_COMPLETO)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert resultado.stdout.strip() == esperado
