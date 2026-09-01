#!/usr/bin/env bash
# Revierte lo que dejo install.sh.
#
# CONSERVA los informes y la evidencia de /var/lib/doctorjk: son el historial
# de incidentes del servidor y pueden hacer falta despues de desinstalar. Para
# borrarlos hay que pedirlo explicitamente con --delete-data.
#
# Uso:  sudo ./instalador/desinstalar.sh [--delete-data]

set -euo pipefail

PREFIX="/opt/doctorjk"
CONFIG_DIR="/etc/doctorjk"
DATA_DIR="/var/lib/doctorjk"
SERVICE_USER="doctorjk"
UNITS=(doctorjk-trigger.service doctorjk.service)

DELETE_DATA=false
[[ "${1:-}" == "--delete-data" ]] && DELETE_DATA=true

info() { printf '  %s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "ERROR: ejecutar como root (sudo)" >&2; exit 1; }

step "Deteniendo servicios"
# El trigger primero: depende del agente y no debe quedar escribiendo a un FIFO
# cuyo dueno ya murio.
for unit in "${UNITS[@]}"; do
  if systemctl list-unit-files "$unit" >/dev/null 2>&1; then
    systemctl disable --now --quiet "$unit" 2>/dev/null || true
    info "$unit detenida"
  fi
  rm -f "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

step "Quitando el codigo"
rm -rf "$PREFIX"
info "$PREFIX eliminado"

step "Configuracion y datos"
if $DELETE_DATA; then
  rm -rf "$CONFIG_DIR" "$DATA_DIR"
  info "configuracion, informes y evidencia ELIMINADOS"
else
  info "se conservan $CONFIG_DIR y $DATA_DIR"
  info "para borrarlos: sudo $0 --delete-data"
fi

# El usuario se conserva si quedaron datos suyos: borrarlo dejaria los informes
# con un UID huerfano, ilegibles por nombre.
if $DELETE_DATA && id "$SERVICE_USER" >/dev/null 2>&1; then
  userdel "$SERVICE_USER" 2>/dev/null || true
  info "usuario $SERVICE_USER eliminado"
fi

printf '\n== Desinstalacion completa\n\n'
