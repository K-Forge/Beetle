#!/usr/bin/env bash
# Instala Doctor J/K como servicio de systemd.
#
# Idempotente: correrlo dos veces no duplica nada ni pisa la configuracion
# existente. Actualizar el agente no debe reabrir decisiones que el cliente ya
# tomo (que umbrales usa, en que modo corre, con que credencial).
#
# Uso:  sudo ./instalador/install.sh

set -euo pipefail

PREFIX="/opt/doctorjk"
CONFIG_DIR="/etc/doctorjk"
DATA_DIR="/var/lib/doctorjk"
REPORTS_DIR="$DATA_DIR/informes"
SERVICE_USER="doctorjk"
UNITS=(doctorjk.service doctorjk-trigger.service)

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info() { printf '  %s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
fatal() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# ------------------------------------------------------- 1. verificar entorno
# Todo lo que pueda impedir la instalacion se comprueba ANTES de tocar el
# sistema: es preferible salir sin haber hecho nada que dejar el servidor a
# medio instalar.

step "Verificando el sistema"

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

for file in "$REPO/pyproject.toml" "$REPO/instalador/config.toml.example" "$REPO/.env.example"; do
  [[ -f "$file" ]] || fatal "falta $file; ¿se ejecuta desde el repositorio?"
done
info "todas las comprobaciones pasaron"

# --------------------------------------------------------- 2. usuario y rutas

step "Creando usuario y directorios"

if id "$SERVICE_USER" >/dev/null 2>&1; then
  info "el usuario $SERVICE_USER ya existe, no se toca"
else
  # Sin shell de login y sin home propio: solo existe para correr el servicio.
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  info "usuario $SERVICE_USER creado (sin login)"
fi

install -d -m 0755 "$PREFIX"
install -d -m 0750 -o root -g "$SERVICE_USER" "$CONFIG_DIR"
install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$DATA_DIR"
install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$REPORTS_DIR"
info "informes en $REPORTS_DIR"

# ----------------------------------------------------------- 3. codigo y venv

step "Instalando el agente"

# rsync respeta --delete para que un archivo borrado del repo no sobreviva en
# la instalacion; se excluye lo que no debe salir del repositorio.
if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude='__pycache__' --exclude='*.pyc' \
    "$REPO/doctorjk/" "$PREFIX/doctorjk/"
else
  rm -rf "${PREFIX:?}/doctorjk"
  cp -r "$REPO/doctorjk" "$PREFIX/doctorjk"
  find "$PREFIX/doctorjk" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
fi
install -m 0755 "$REPO/doctorjk/trigger.sh" "$PREFIX/doctorjk/trigger.sh"
install -d -m 0755 "$PREFIX/prompts"
install -m 0644 "$REPO/prompts/diagnosticador.md" "$PREFIX/prompts/diagnosticador.md"
install -m 0644 "$REPO/pyproject.toml" "$PREFIX/pyproject.toml"
# Las unidades systemd apuntan Documentation= acá (defecto 13); sin copiarlo,
# `systemctl status` ofrece un enlace roto.
install -m 0644 "$REPO/README.md" "$PREFIX/README.md"

# Modo 2 (tareas #199-202): los cuatro scripts corren como root vía sudoers
# exacto (paso 5), nunca con permisos del propio doctorjk.
install -d -m 0755 "$PREFIX/scripts-fix"
install -m 0755 "$REPO/scripts-fix/comun.sh" "$PREFIX/scripts-fix/comun.sh"
for fix_script in fix_disco.sh fix_servicio.sh fix_memoria.sh fix_puerto.sh; do
  install -m 0755 "$REPO/scripts-fix/$fix_script" "$PREFIX/scripts-fix/$fix_script"
done

if [[ -x "$PREFIX/venv/bin/python" ]]; then
  info "entorno virtual existente, se reutiliza"
else
  python3 -m venv "$PREFIX/venv"
  info "entorno virtual creado"
fi
"$PREFIX/venv/bin/pip" install --quiet --upgrade pip
"$PREFIX/venv/bin/pip" install --quiet "$PREFIX"
info "dependencias instaladas"

chown -R root:root "$PREFIX"
chmod -R go-w "$PREFIX"

# ------------------------------------------------------------ 4. configuracion
# Nunca se sobrescribe: una reinstalacion no debe reabrir decisiones tomadas.

step "Configuracion"

if [[ -f "$CONFIG_DIR/config.toml" ]]; then
  info "config.toml ya existe, se conserva sin cambios"
else
  install -m 0640 -o root -g "$SERVICE_USER" \
    "$REPO/instalador/config.toml.example" "$CONFIG_DIR/config.toml"
  info "config.toml creado desde la plantilla"
fi

if [[ -f "$CONFIG_DIR/.env" ]]; then
  info ".env ya existe, se conserva sin cambios"
else
  install -m 0600 -o root -g "$SERVICE_USER" "$REPO/.env.example" "$CONFIG_DIR/.env"
  info ".env creado (permisos 600) — falta poner la credencial"
fi
# Aunque ya existiera, se reafirma el modo: un .env legible por todos es una fuga.
chmod 0600 "$CONFIG_DIR/.env"

# ---------------------------------------------------- 5. privilegios del Modo 2
# doctorjk corre sin privilegios (CONTEXTO-IA.md §8.5); estos cuatro scripts
# ya vetted son la ÚNICA escalación permitida, cada uno por su ruta exacta.
# Nunca un systemctl/find suelto, nunca shell genérico (tareas #199-202,
# plan-finalizacion-mvp.md §4.1).

step "Instalando privilegios de Modo 2 (sudoers)"

SUDOERS_TMP="$(mktemp)"
trap 'rm -f "$SUDOERS_TMP"' EXIT
cat > "$SUDOERS_TMP" <<SUDOERS_EOF
# Generado por instalador/install.sh -- no editar a mano, se sobrescribe en
# cada instalación. Cuatro rutas exactas, nada más.
doctorjk ALL=(root) NOPASSWD: $PREFIX/scripts-fix/fix_disco.sh
doctorjk ALL=(root) NOPASSWD: $PREFIX/scripts-fix/fix_servicio.sh
doctorjk ALL=(root) NOPASSWD: $PREFIX/scripts-fix/fix_memoria.sh
doctorjk ALL=(root) NOPASSWD: $PREFIX/scripts-fix/fix_puerto.sh
SUDOERS_EOF

visudo -cf "$SUDOERS_TMP" || fatal "el sudoers generado para Modo 2 no es válido, no se instala"
install -m 0440 -o root -g root "$SUDOERS_TMP" /etc/sudoers.d/doctorjk
rm -f "$SUDOERS_TMP"
trap - EXIT
info "sudoers instalado: 4 scripts exactos, sin shell genérico"

# Verificación de autorización, NUNCA de ejecución (corregido 2026-09-01
# tras hallazgo de auditoría: la versión anterior corría fix_disco.sh de
# verdad, lo que podía disparar una limpieza real de journal/logs en cada
# reinstalación si el disco ya estaba sobre el umbral y dry_run=false --
# un instalador jamás debe provocar una remediación como efecto secundario
# de instalarse). "sudo -n -l <comando>" solo confirma que sudoers lo
# autorizaría, sin correrlo.
if runuser -u "$SERVICE_USER" -- sudo -n -l "$PREFIX/scripts-fix/fix_disco.sh" / >/dev/null 2>&1; then
  info "verificado: sudoers autoriza a $SERVICE_USER a escalar a los scripts de Modo 2"
else
  fatal "sudoers no autoriza a $SERVICE_USER para Modo 2; revisar /etc/sudoers.d/doctorjk"
fi

# --------------------------------------------------------------- 6. servicios

step "Instalando unidades de systemd"

for unit in "${UNITS[@]}"; do
  install -m 0644 "$REPO/instalador/$unit" "/etc/systemd/system/$unit"
  info "$unit instalada"
done

# Chequeo estático de la unidad instalada (bloqueante P0 de auditoría,
# 2026-09-01): NoNewPrivileges=true anularía sudo desde dentro del servicio
# aunque el sudoers esté perfecto -- se verifica el archivo ya copiado a
# /etc/systemd/system, no la fuente del repo, para detectar tambien un
# despliegue con una unidad vieja/distinta.
if grep -qE '^\s*NoNewPrivileges\s*=\s*true' "/etc/systemd/system/doctorjk.service"; then
  fatal "doctorjk.service tiene NoNewPrivileges=true; sudo -n nunca escalaría, Modo 2 fallaría siempre"
fi

systemctl daemon-reload
for unit in "${UNITS[@]}"; do
  systemctl enable --quiet "$unit"
done

# restart y no start: en una reinstalacion hay que recargar el codigo nuevo.
systemctl restart doctorjk.service
systemctl restart doctorjk-trigger.service

sleep 3
failed_units=()
for unit in "${UNITS[@]}"; do
  systemctl is-active --quiet "$unit" || failed_units+=("$unit")
done

if (( ${#failed_units[@]} > 0 )); then
  printf '\nERROR: no arrancaron: %s\n' "${failed_units[*]}" >&2
  printf 'Revisa:  journalctl -u %s -n 30 --no-pager\n' "${failed_units[0]}" >&2
  exit 1
fi

# ----------------------------------------------------------------- 7. resumen
# Refleja el estado REAL de config.toml/.env, no un texto fijo (hallazgo de
# auditoría #8): en una reinstalación con Modo 2 ya activo o la credencial
# ya puesta, el resumen anterior mentía en las dos líneas.

MODE=$(grep -E '^\s*modo_remediacion' "$CONFIG_DIR/config.toml" | head -1 | cut -d'"' -f2 || echo "desconocido")
case "$MODE" in
  diagnostico) MODE_DESC="solo diagnostica; no modifica el servidor" ;;
  scripts)     MODE_DESC="Modo 2 activo; corrige con scripts deterministas si auto_fix=true" ;;
  automatico)  MODE_DESC="Modo 3 activo; el modelo genera el plan si auto_fix=true" ;;
  *)           MODE_DESC="modo desconocido, revisar config.toml" ;;
esac

if grep -qE '^\s*DOCTORJK_LLM_API_KEY\s*=\s*\S' "$CONFIG_DIR/.env"; then
  CRED_ESTADO="configurada"
else
  CRED_ESTADO="falta completarla"
fi

cat <<END

== Instalacion completa

  Modo actual:   $MODE ($MODE_DESC)
  Configuracion: $CONFIG_DIR/config.toml
  Credencial:    $CONFIG_DIR/.env      <- $CRED_ESTADO
  Informes:      $REPORTS_DIR
  Servicios:     ${UNITS[*]}

END

if [[ "$CRED_ESTADO" == "falta completarla" ]]; then
  cat <<END
  Antes de que pueda diagnosticar, pon la credencial del proveedor:

      sudo nano $CONFIG_DIR/.env
      sudo systemctl restart doctorjk.service

END
fi

cat <<END
  Para ver que esta haciendo:

      journalctl -u doctorjk -f

END
