#!/usr/bin/env bash
# Revierte lo que dejo install.sh.
#
# CONSERVA los informes y la evidencia de /var/lib/doctorjk: son el historial
# de incidentes del servidor y pueden hacer falta despues de desinstalar. Para
# borrarlos hay que pedirlo explicitamente con --borrar-datos.
#
# Uso:  sudo ./instalador/desinstalar.sh [--borrar-datos]

set -euo pipefail

PREFIJO="/opt/doctorjk"
CONFIG_DIR="/etc/doctorjk"
DATOS_DIR="/var/lib/doctorjk"
USUARIO="doctorjk"
UNIDADES=(doctorjk-trigger.service doctorjk.service)

BORRAR_DATOS=false
[[ "${1:-}" == "--borrar-datos" ]] && BORRAR_DATOS=true

info() { printf '  %s\n' "$*"; }
paso() { printf '\n== %s\n' "$*"; }

[[ $EUID -eq 0 ]] || { echo "ERROR: ejecutar como root (sudo)" >&2; exit 1; }

paso "Deteniendo servicios"
# El trigger primero: depende del agente y no debe quedar escribiendo a un FIFO
# cuyo dueno ya murio.
for unidad in "${UNIDADES[@]}"; do
  if systemctl list-unit-files "$unidad" >/dev/null 2>&1; then
    systemctl disable --now --quiet "$unidad" 2>/dev/null || true
    info "$unidad detenida"
  fi
  rm -f "/etc/systemd/system/$unidad"
done
systemctl daemon-reload
systemctl reset-failed 2>/dev/null || true

paso "Quitando el codigo"
rm -rf "$PREFIJO"
info "$PREFIJO eliminado"

paso "Configuracion y datos"
if $BORRAR_DATOS; then
  rm -rf "$CONFIG_DIR" "$DATOS_DIR"
  info "configuracion, informes y evidencia ELIMINADOS"
else
  info "se conservan $CONFIG_DIR y $DATOS_DIR"
  info "para borrarlos: sudo $0 --borrar-datos"
fi

# El usuario se conserva si quedaron datos suyos: borrarlo dejaria los informes
# con un UID huerfano, ilegibles por nombre.
if $BORRAR_DATOS && id "$USUARIO" >/dev/null 2>&1; then
  userdel "$USUARIO" 2>/dev/null || true
  info "usuario $USUARIO eliminado"
fi

printf '\n== Desinstalacion completa\n\n'
