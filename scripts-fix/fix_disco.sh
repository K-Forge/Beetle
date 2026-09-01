#!/usr/bin/env bash
# Modo 2 -- corrige un incidente disk_full: libera espacio bajo rutas fijas
# y verifica que el uso baje del umbral (tareas #199, #202).
#
# Alcance deliberadamente acotado (plan-finalizacion-mvp.md §4.2): nunca
# borra "el archivo más grande" sin política. Solo toca:
#   - el journal de systemd, con vacuum acotado a un tamaño fijo;
#   - logs rotados/comprimidos bajo /var/log (*.log.*.gz, *.log.[0-9]*) con
#     más de 3 días -- nunca un log activo sin rotar.
# Deliberadamente NO toca /tmp: en un servidor compartido no hay forma
# segura de distinguir un archivo temporal huérfano de uno en uso de otro
# proceso o de otro equipo sin una política de retención más fina, que
# queda pendiente para cuando el producto la defina (no se inventa acá).
#
# Solo actúa sobre "/": journal y /var/log viven en el filesystem raíz, así
# que limpiarlos no ayuda a un punto de montaje distinto -- para cualquier
# otro mount point este script escala en vez de fingir que hizo algo útil
# (hallazgo de auditoría #9, 2026-09-01).
#
# $1 = punto de montaje. config.toml se lee de la ruta fija que define
# comun.sh (no es un argumento; ver esa cabecera).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=comun.sh
source "$DIR/comun.sh"

mount_point="${1:-}"
[[ -n "$mount_point" ]] || fail "uso: $0 <punto-de-montaje>"
[[ "$mount_point" == "/" ]] || fail "sin política de limpieza para $mount_point (solo se cubre /); escalar sin actuar"

threshold="$(read_config_attr disk_pct_threshold)"

disk_usage_pct() {
  df --output=pcent "$mount_point" 2>/dev/null | tail -1 | tr -dc '0-9'
}

usage="$(disk_usage_pct)" || true
[[ -n "$usage" ]] || fail "no pude leer el uso de disco de $mount_point"

log "precondición: $mount_point al ${usage}% (umbral ${threshold}%)"
if (( usage <= threshold )); then
  log "$mount_point ya está bajo el umbral; nada que corregir (idempotente)"
  exit 0
fi

run_or_announce journalctl --vacuum-size=100M
run_or_announce find /var/log -type f \( -name '*.log.*.gz' -o -name '*.log.[0-9]*' \) -mtime +3 -delete

if is_dry_run; then
  log "[DRY-RUN] no se verifica postcondición"
  exit 0
fi

usage_after="$(disk_usage_pct)" || true
[[ -n "$usage_after" ]] || fail "no pude releer el uso de disco tras limpiar"
log "postcondición: $mount_point ahora al ${usage_after}%"
if (( usage_after <= threshold )); then
  log "verificado: $mount_point bajó del umbral"
  exit 0
fi

fail "$mount_point sigue sobre el umbral tras la limpieza (${usage_after}% > ${threshold}%)"
