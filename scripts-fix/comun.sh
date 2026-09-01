#!/usr/bin/env bash
# Funciones compartidas por los scripts de scripts-fix/ (Modo 2, tareas
# #199-202). Se importa con `source`, nunca se ejecuta solo.
#
# Contrato de invocación (remediador.py): $1 = recurso objetivo (unidad,
# punto de montaje o puerto). Nada más -- ni la ruta de config.toml ni el
# intérprete de Python se aceptan por argumento ni por variable de entorno
# controlable en el camino privilegiado (ver abajo).
#
# La política -- listas vigiladas, umbrales, dry-run -- se lee SIEMPRE de
# config.toml directamente, nunca de variables de entorno (hallazgo de
# auditoría #1, 2026-09-01). En producción estos scripts corren vía
# "sudo -n" y sudo con env_reset (default de seguridad de sudo) elimina
# cualquier DOCTORJK_* que remediador.py intentara pasar -- las listas
# llegarían vacías y cada script fallaría cerrado o, peor, usaría un
# default silencioso. La corrección NO es SETENV/env_keep en sudoers: eso
# le daría al proceso sin privilegios doctorjk la posibilidad de fabricar
# la allowlist que ve el script que corre como root.
#
# Segunda corrección (hallazgo #1-bis, misma fecha): la ruta de config.toml
# tampoco puede venir de $2. sudoers, tal como lo genera install.sh, permite
# el script con CUALQUIER argumento -- no hay forma de fijar $2 con
# NOPASSWD sin listar cada valor posible -- así que un argumento sería tan
# manipulable como una variable de entorno. La ruta queda fija en
# /etc/doctorjk/config.toml, sin excepción, en el camino privilegiado.
#
# DOCTORJK_CONFIG_PATH y DOCTORJK_VENV_PYTHON solo existen para pruebas
# locales SIN sudo de por medio: en producción, sudo -n con env_reset las
# elimina antes de que este script las vea, así que nunca pueden pisar la
# ruta ni el intérprete reales. No es "confiar menos" en esas variables --
# es que estructuralmente no llegan al camino que importa.
CONFIG_PATH="${DOCTORJK_CONFIG_PATH:-/etc/doctorjk/config.toml}"
VENV_PYTHON="${DOCTORJK_VENV_PYTHON:-/opt/doctorjk/venv/bin/python3}"

log() {
  # Mensajes que el remediador guarda tal cual en la bitácora de auditoría
  # (tarea #201): sin datos sensibles, journald ya recibe la salida completa.
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

fail() {
  printf '[%s] ERROR: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
  exit 1
}

# Ningún fallback a un "python3" genérico del PATH (hallazgo #2, misma
# fecha): si el intérprete exacto no está, se falla cerrado. Buscar en PATH
# desde un proceso que ya es root podría importar un paquete `doctorjk`
# falso puesto ahí por cualquiera con permiso de escritura en ese PATH.
[[ -x "$VENV_PYTHON" ]] || fail "intérprete no encontrado o no ejecutable: $VENV_PYTHON"

# Nunca se confía en config.toml sin verificar que sigue siendo root-owned y
# no escribible por nadie más: si esta verificación no existiera, cualquier
# forma futura de desviar CONFIG_PATH (o un ataque que reemplace el archivo
# real) le daría a un proceso sin privilegios control total sobre la
# política que ve el script que corre como root.
_verify_config_ownership() {
  local owner mode
  owner="$(stat -c '%U' "$CONFIG_PATH" 2>/dev/null)" \
    || fail "no pude leer los permisos de $CONFIG_PATH"
  [[ "$owner" == "root" ]] \
    || fail "$CONFIG_PATH no es propiedad de root (dueño: $owner); no se confía"
  mode="$(stat -c '%a' "$CONFIG_PATH" 2>/dev/null)" \
    || fail "no pude leer el modo de $CONFIG_PATH"
  # Bit de escritura de grupo (0o020) y de otros (0o002), aislados con una
  # máscara octal sobre el valor ya convertido por `8#$mode`. La versión
  # anterior recalculaba `8#$mode` (una conversión octal -> decimal) y
  # después le aplicaba /10 % 10 y % 10 como si fueran los dígitos octales
  # originales -- son los dígitos DECIMALES del número ya convertido, no los
  # octales de "$mode". Para el modo real que pone install.sh (0640) esto
  # fallaba cerrado siempre (hallazgo en vivo, VPS, 2026-09-01): 8#640 = 416,
  # y 416 % 10 = 6 trae el bit 2 encendido por pura coincidencia decimal, sin
  # relación con el bit "otros escribible" real de 640 (que es 0). La máscara
  # octal no tiene ese problema y además ignora correctamente cualquier bit
  # extra de setuid/setgid/sticky que agregue un cuarto dígito a %a.
  if (( (8#$mode & 8#020) || (8#$mode & 8#002) )); then
    fail "$CONFIG_PATH tiene permisos de escritura demasiado amplios (modo $mode); no se confía"
  fi
}
_verify_config_ownership

# Lee un atributo ya validado de AppConfig usando doctorjk.config.load_config
# -- el mismo parser que usa main.py, nunca una relectura ad-hoc del TOML en
# bash. Listas se devuelven separadas por comas; monitored_ports como
# "puerto=servicio,puerto=servicio"; booleanos como "1"/"0".
#
# "-I" (modo aislado): ignora PYTHONPATH/PYTHONHOME y no agrega el
# directorio del script ni el site-packages del usuario a sys.path -- el
# proceso ya es root, no debe resolver imports desde nada que un proceso sin
# privilegios pueda haber puesto en esas rutas.
read_config_attr() {
  local attr="$1"
  "$VENV_PYTHON" -I - "$CONFIG_PATH" "$attr" <<'PYEOF'
import sys
from pathlib import Path

from doctorjk.config import load_config

# Mismo bug ya corregido en install.sh (2026-09-01): load_config() exige
# Path y llama path.read_bytes() -- pasarle el str crudo de sys.argv[1]
# revienta con AttributeError en cuanto cualquier fix_*.sh llama a
# read_config_attr, sin importar el resto del script.
config = load_config(Path(sys.argv[1]))
attribute = sys.argv[2]
value = getattr(config, attribute)

if attribute == "monitored_ports":
    print(",".join(f"{p.port}={p.service}" for p in value))
elif isinstance(value, (list, tuple)):
    print(",".join(str(v) for v in value))
elif isinstance(value, bool):
    print("1" if value else "0")
else:
    print(value)
PYEOF
}

# Verdadero si config.toml tiene dry_run=true. Cada fix_*.sh debe
# consultarlo antes de cualquier acción que cambie el estado del sistema (no
# antes de leer para verificar precondición/postcondición, eso es seguro
# siempre).
is_dry_run() {
  [[ "$(read_config_attr dry_run)" == "1" ]]
}

# Ejecuta una acción salvo en dry-run, donde solo la anuncia. Uso:
#   run_or_announce systemctl restart "$unit"
run_or_announce() {
  if is_dry_run; then
    log "[DRY-RUN] no ejecutado: $*"
    return 0
  fi
  log "ejecutando: $*"
  "$@"
}

# Verdadero si $1 aparece como elemento exacto de la lista separada por
# comas en $2 (p. ej. la salida de read_config_attr monitored_services).
# Comparación exacta, no substring: "nginx.service" no debe calzar con
# "nginx.service.bak".
list_contains() {
  local needle="$1" list="$2" item
  IFS=',' read -ra items <<< "$list"
  for item in "${items[@]}"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}
