# Funciones de apoyo compartidas por las pruebas unitarias. No es un test en
# si mismo (por eso no se llama test_*.py) para que pytest no intente
# recolectarlo como caso de prueba.
from __future__ import annotations

import stat
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"

REPO_ROOT = Path(__file__).parent.parent.parent
SCRIPTS_FIX_DIR = REPO_ROOT / "scripts-fix"
COMUN_SH = SCRIPTS_FIX_DIR / "comun.sh"
FIX_SERVICIO = SCRIPTS_FIX_DIR / "fix_servicio.sh"
FIX_DISCO = SCRIPTS_FIX_DIR / "fix_disco.sh"
FIX_PUERTO = SCRIPTS_FIX_DIR / "fix_puerto.sh"
FIX_MEMORIA = SCRIPTS_FIX_DIR / "fix_memoria.sh"


def load_fixture(name: str) -> str:
    """Lee una salida de comando real y sanitizada guardada en fixtures/."""
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


def instalar_script(ruta: Path, contenido: str) -> None:
    """Escribe contenido en ruta y lo marca ejecutable -- usado para instalar
    scripts-fix/*.sh reales y dobles/comandos falsos en un PATH de prueba."""
    ruta.write_text(contenido, encoding="utf-8")
    ruta.chmod(ruta.stat().st_mode | stat.S_IEXEC)


# --------------------------------------------------------------------------
# Dobles de comandos del sistema, compartidos entre test_scripts_fix.py,
# test_comun_permisos.py y test_scripts_fix_integracion_real.py. Cada uno
# imita solo el subcomando/formato exacto que el script real bajo prueba
# consume -- no un mock genérico de systemctl/ss/etc.

# stat -c '%U'|'%a' "$ruta" -- ignora la ruta real, reporta lo que el test
# quiera vía TEST_STAT_OWNER/TEST_STAT_MODE. Así se controla lo que
# _verify_config_ownership (comun.sh real) ve, sin necesitar root para
# chown/chmod de verdad.
FAKE_STAT = """#!/usr/bin/env bash
case "$2" in
  '%U') echo "${TEST_STAT_OWNER}" ;;
  '%a') echo "${TEST_STAT_MODE}" ;;
esac
"""

FAKE_SLEEP = """#!/usr/bin/env bash
exit 0
"""

# Nadie escucha en la primera llamada (precondición); alguien escucha desde
# la segunda en adelante (postcondición, simulando que systemctl restart de
# verdad hizo bind del puerto).
FAKE_SS = """#!/usr/bin/env bash
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

FAKE_SYSTEMCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_STATE_DIR/systemctl_calls"
case "$1" in
  is-active) exit 0 ;;
  status) echo "\xe2\x97\x8f ${TEST_EXPECTED_UNIT} - fake unit"; exit 0 ;;
  restart|stop) exit 0 ;;
  *) exit 0 ;;
esac
"""

# ss ya muestra un ocupante indebido en la primera llamada (precondición);
# desde la segunda, muestra a la unidad esperada con OTRO pid (postcondición,
# simulando que systemctl restart de verdad hizo bind del puerto).
FAKE_SS_OCUPADO = """#!/usr/bin/env bash
count_file="$FAKE_STATE_DIR/ss_calls"
count=0
[[ -f "$count_file" ]] && count="$(cat "$count_file")"
count=$((count + 1))
echo "$count" > "$count_file"
echo "State  Recv-Q Send-Q  Local Address:Port  Peer Address:Port Process"
if (( count == 1 )); then
  echo "LISTEN 0 128 0.0.0.0:${TEST_PORT} 0.0.0.0:* users:((\\"proc\\",pid=4242,fd=3))"
else
  echo "LISTEN 0 128 0.0.0.0:${TEST_PORT} 0.0.0.0:* users:((\\"proc\\",pid=5555,fd=3))"
fi
"""

# unit_for_pid() distingue por el pid que le pasan: 4242 -> ocupante, otro
# pid -> unidad esperada -- así el test puede distinguir a quién identificó
# el script en cada llamada, no solo asumir un único nombre fijo.
FAKE_SYSTEMCTL_PUERTO_OCUPADO = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_STATE_DIR/systemctl_calls"
case "$1" in
  status)
    if [[ "$2" == "4242" ]]; then
      echo "\xe2\x97\x8f ${TEST_OCCUPIER_UNIT} - fake unit"
    else
      echo "\xe2\x97\x8f ${TEST_EXPECTED_UNIT} - fake unit"
    fi
    exit 0
    ;;
  is-active) exit 0 ;;
  restart|stop) exit 0 ;;
  *) exit 0 ;;
esac
"""

FAKE_SYSTEMCTL_SERVICIO = """#!/usr/bin/env bash
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

# Primera llamada: sobre el umbral (dispara la limpieza). Segunda en
# adelante: bajo el umbral (simula que la limpieza sí liberó espacio).
FAKE_DF = """#!/usr/bin/env bash
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

FAKE_JOURNALCTL = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_STATE_DIR/journalctl_calls"
exit 0
"""

# Traduce /var/log al directorio de prueba FAKE_VAR_LOG y delega en el find
# real -- así fix_disco.sh corre su búsqueda de verdad (mismos argumentos,
# mismo -print0), solo que contra archivos de prueba, no el filesystem real
# de la máquina que corre las pruebas.
FAKE_FIND = """#!/usr/bin/env bash
args=("$@")
if [[ "${args[0]}" == "/var/log" ]]; then
  args[0]="$FAKE_VAR_LOG"
fi
exec /usr/bin/find "${args[@]}"
"""

FAKE_FREE = """#!/usr/bin/env bash
if [[ -f "$FAKE_STATE_DIR/memoria_liberada" ]]; then
  available="${TEST_AVAILABLE_AFTER:-1000}"
else
  available="${TEST_AVAILABLE_BEFORE:-100}"
fi
echo "              total        used        free      shared  buff/cache   available"
echo "Mem:           3900        2000         500          10         1400       $available"
echo "Swap:             0           0           0"
"""

FAKE_SYSTEMCTL_MEMORIA = """#!/usr/bin/env bash
echo "$*" >> "$FAKE_STATE_DIR/systemctl_calls"
case "$1" in
  show) echo "${TEST_UNIT_MEMORY_BYTES:-0}" ;;
  restart) touch "$FAKE_STATE_DIR/memoria_liberada"; exit 0 ;;
  *) exit 0 ;;
esac
"""
