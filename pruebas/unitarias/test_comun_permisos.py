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
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
COMUN_SH = REPO_ROOT / "scripts-fix" / "comun.sh"

_FAKE_STAT = """#!/usr/bin/env bash
# stat -c '%U'|'%a' "$ruta" -- ignora la ruta real, reporta lo que el test
# quiera vía TEST_STAT_OWNER/TEST_STAT_MODE.
case "$2" in
  '%U') echo "${TEST_STAT_OWNER}" ;;
  '%a') echo "${TEST_STAT_MODE}" ;;
esac
"""

_RUNNER_SH = """#!/usr/bin/env bash
# Sourcear comun.sh dispara _verify_config_ownership al final del propio
# archivo (no es una función que se llame aparte) -- reproduce exactamente
# cómo lo invoca cada fix_*.sh real.
source "$1"
echo SOURCED_OK
"""


def _instalar(ruta: Path, contenido: str) -> None:
    ruta.write_text(contenido, encoding="utf-8")
    ruta.chmod(ruta.stat().st_mode | stat.S_IEXEC)


def _fuente_comun_real(tmp_path: Path, owner: str, mode: str) -> subprocess.CompletedProcess[str]:
    scripts_dir = tmp_path / "scripts-fix"
    scripts_dir.mkdir()
    _instalar(scripts_dir / "comun.sh", COMUN_SH.read_text(encoding="utf-8"))

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    _instalar(fake_bin / "stat", _FAKE_STAT)

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
