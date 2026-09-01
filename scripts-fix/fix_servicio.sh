#!/usr/bin/env bash
# Modo 2 -- corrige un incidente service_failed: reinicia la unidad y
# verifica que quede activa (tareas #199, #202).
#
# Corre como root: el sudoers exacto que install.sh genera permite a
# doctorjk ejecutar este script vía "sudo -n" (ver remediador.py), nunca un
# comando systemctl suelto. Solo actúa sobre una unidad que el cliente ya
# vigila en config.toml (servicios_vigilados) -- nunca sobre un nombre de
# unidad arbitrario recibido por argumento.
#
# $1 = unidad a corregir. config.toml se lee de la ruta fija que define
# comun.sh (ver esa cabecera: no es un argumento, sudoers no restringe
# argumentos y sería tan manipulable como una variable de entorno).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=comun.sh
source "$DIR/comun.sh"

unit="${1:-}"
[[ -n "$unit" ]] || fail "uso: $0 <unidad-systemd> [config.toml]"

monitored="$(read_config_attr monitored_services)"
list_contains "$unit" "$monitored" || fail "unidad no vigilada, no se toca: $unit"

log "precondición: $unit debe estar fallida"
if systemctl is-active --quiet "$unit"; then
  log "$unit ya está activa; nada que corregir (idempotente)"
  exit 0
fi

run_or_announce systemctl restart "$unit"

if is_dry_run; then
  log "[DRY-RUN] no se verifica postcondición"
  exit 0
fi

sleep 2
if systemctl is-active --quiet "$unit"; then
  log "verificado: $unit quedó activa"
  exit 0
fi

fail "$unit sigue sin estar activa tras el reinicio"
