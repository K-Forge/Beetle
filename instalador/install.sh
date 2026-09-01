#!/usr/bin/env bash
# Instala Doctor J/K como servicio de systemd.
#
# Idempotente: correrlo dos veces no duplica nada ni pisa la configuracion
# existente. Actualizar el agente no debe reabrir decisiones que el cliente ya
# tomo (que umbrales usa, en que modo corre, con que credencial).
#
# Uso:  sudo ./instalador/install.sh

set -euo pipefail

PREFIJO="/opt/doctorjk"
CONFIG_DIR="/etc/doctorjk"
DATOS_DIR="/var/lib/doctorjk"
INFORMES_DIR="$DATOS_DIR/informes"
USUARIO="doctorjk"
UNIDADES=(doctorjk.service doctorjk-trigger.service)

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info() { printf '  %s\n' "$*"; }
paso() { printf '\n== %s\n' "$*"; }
fatal() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# ------------------------------------------------------- 1. verificar entorno
# Todo lo que pueda impedir la instalacion se comprueba ANTES de tocar el
# sistema: es preferible salir sin haber hecho nada que dejar el servidor a
# medio instalar.

paso "Verificando el sistema"

[[ $EUID -eq 0 ]] || fatal "hay que ejecutarlo como root (sudo)"

command -v systemctl >/dev/null 2>&1 || fatal "systemd no esta disponible; Doctor J/K lo requiere"

if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  case "${ID:-}${ID_LIKE:-}" in
    *debian*|*ubuntu*) info "distribucion: ${PRETTY_NAME:-desconocida}" ;;
    *) fatal "solo se soporta Ubuntu/Debian; se detecto '${PRETTY_NAME:-desconocida}'" ;;
  esac
else
  fatal "no pude leer /etc/os-release"
fi

command -v python3 >/dev/null 2>&1 || fatal "python3 no esta instalado"
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || fatal "se requiere Python 3.11 o superior; hay $PY_VER"
info "python: $PY_VER"

python3 -c 'import venv' 2>/dev/null || fatal "falta el modulo venv (apt install python3-venv)"

for archivo in "$REPO/pyproject.toml" "$REPO/instalador/config.toml.example" "$REPO/.env.example"; do
  [[ -f "$archivo" ]] || fatal "falta $archivo; ¿se ejecuta desde el repositorio?"
done
info "todas las comprobaciones pasaron"

# --------------------------------------------------------- 2. usuario y rutas

paso "Creando usuario y directorios"

if id "$USUARIO" >/dev/null 2>&1; then
  info "el usuario $USUARIO ya existe, no se toca"
else
  # Sin shell de login y sin home propio: solo existe para correr el servicio.
  useradd --system --no-create-home --shell /usr/sbin/nologin "$USUARIO"
  info "usuario $USUARIO creado (sin login)"
fi

install -d -m 0755 "$PREFIJO"
install -d -m 0750 -o root -g "$USUARIO" "$CONFIG_DIR"
install -d -m 0750 -o "$USUARIO" -g "$USUARIO" "$DATOS_DIR"
install -d -m 0750 -o "$USUARIO" -g "$USUARIO" "$INFORMES_DIR"
info "informes en $INFORMES_DIR"

# ----------------------------------------------------------- 3. codigo y venv

paso "Instalando el agente"

# rsync respeta --delete para que un archivo borrado del repo no sobreviva en
# la instalacion; se excluye lo que no debe salir del repositorio.
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude='__pycache__' --exclude='*.pyc' \
    "$REPO/doctorjk/" "$PREFIJO/doctorjk/"
else
  rm -rf "${PREFIJO:?}/doctorjk"
  cp -r "$REPO/doctorjk" "$PREFIJO/doctorjk"
  find "$PREFIJO/doctorjk" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
fi
install -m 0755 "$REPO/doctorjk/trigger.sh" "$PREFIJO/doctorjk/trigger.sh"
install -d -m 0755 "$PREFIJO/prompts"
install -m 0644 "$REPO/prompts/diagnosticador.md" "$PREFIJO/prompts/diagnosticador.md"
install -m 0644 "$REPO/pyproject.toml" "$PREFIJO/pyproject.toml"

if [[ -x "$PREFIJO/venv/bin/python" ]]; then
  info "entorno virtual existente, se reutiliza"
else
  python3 -m venv "$PREFIJO/venv"
  info "entorno virtual creado"
fi
"$PREFIJO/venv/bin/pip" install --quiet --upgrade pip
"$PREFIJO/venv/bin/pip" install --quiet "$PREFIJO"
info "dependencias instaladas"

chown -R root:root "$PREFIJO"
chmod -R go-w "$PREFIJO"

# ------------------------------------------------------------ 4. configuracion
# Nunca se sobrescribe: una reinstalacion no debe reabrir decisiones tomadas.

paso "Configuracion"

if [[ -f "$CONFIG_DIR/config.toml" ]]; then
  info "config.toml ya existe, se conserva sin cambios"
else
  install -m 0640 -o root -g "$USUARIO" \
    "$REPO/instalador/config.toml.example" "$CONFIG_DIR/config.toml"
  info "config.toml creado desde la plantilla"
fi

if [[ -f "$CONFIG_DIR/.env" ]]; then
  info ".env ya existe, se conserva sin cambios"
else
  install -m 0600 -o root -g "$USUARIO" "$REPO/.env.example" "$CONFIG_DIR/.env"
  info ".env creado (permisos 600) — falta poner la credencial"
fi
# Aunque ya existiera, se reafirma el modo: un .env legible por todos es una fuga.
chmod 0600 "$CONFIG_DIR/.env"

# --------------------------------------------------------------- 5. servicios

paso "Instalando unidades de systemd"

for unidad in "${UNIDADES[@]}"; do
  install -m 0644 "$REPO/instalador/$unidad" "/etc/systemd/system/$unidad"
  info "$unidad instalada"
done

systemctl daemon-reload
for unidad in "${UNIDADES[@]}"; do
  systemctl enable --quiet "$unidad"
done

# restart y no start: en una reinstalacion hay que recargar el codigo nuevo.
systemctl restart doctorjk.service
systemctl restart doctorjk-trigger.service

sleep 3
fallidas=()
for unidad in "${UNIDADES[@]}"; do
  systemctl is-active --quiet "$unidad" || fallidas+=("$unidad")
done

if (( ${#fallidas[@]} > 0 )); then
  printf '\nERROR: no arrancaron: %s\n' "${fallidas[*]}" >&2
  printf 'Revisa:  journalctl -u %s -n 30 --no-pager\n' "${fallidas[0]}" >&2
  exit 1
fi

# ----------------------------------------------------------------- 6. resumen

MODO=$(grep -E '^\s*modo_remediacion' "$CONFIG_DIR/config.toml" | head -1 | cut -d'"' -f2 || echo "desconocido")

cat <<FIN

== Instalacion completa

  Modo actual:   $MODO (solo diagnostica; no modifica el servidor)
  Configuracion: $CONFIG_DIR/config.toml
  Credencial:    $CONFIG_DIR/.env      <- falta completarla
  Informes:      $INFORMES_DIR
  Servicios:     ${UNIDADES[*]}

  Antes de que pueda diagnosticar, pon la credencial del proveedor:

      sudo nano $CONFIG_DIR/.env
      sudo systemctl restart doctorjk.service

  Para ver que esta haciendo:

      journalctl -u doctorjk -f

FIN
