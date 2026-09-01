#!/usr/bin/env bash
# Modo 2 -- corrige un incidente memory_low: reinicia la ÚNICA unidad
# aprobada explícitamente en config.toml (unidad_memoria_aprobada) para
# liberar la memoria que retiene (tareas #199, #202).
#
# Sin unidad aprobada, este script escala en vez de actuar: no mata
# procesos arbitrarios ni escribe a /proc/sys/vm/drop_caches
# (plan-finalizacion-mvp.md §4.2 -- ambos quedan explícitamente prohibidos).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=comun.sh
source "$DIR/comun.sh"

unit="${DOCTORJK_APPROVED_MEMORY_UNIT:-}"
[[ -n "$unit" ]] || fail "sin unidad_memoria_aprobada configurada; escalar sin actuar"

threshold_mb="${DOCTORJK_MEMORY_THRESHOLD_MB:-512}"

available_mb() {
  free -m | awk '/^Mem:/{print $7}'
}

available="$(available_mb)" || true
[[ -n "$available" ]] || fail "no pude leer memoria disponible"

log "precondición: ${available} MB disponibles (umbral ${threshold_mb} MB)"
if (( available >= threshold_mb )); then
  log "ya hay memoria suficiente; nada que corregir (idempotente)"
  exit 0
fi

run_or_announce systemctl restart "$unit"

if is_dry_run; then
  log "[DRY-RUN] no se verifica postcondición"
  exit 0
fi

sleep 3
available_after="$(available_mb)" || true
[[ -n "$available_after" ]] || fail "no pude releer memoria disponible"
log "postcondición: ${available_after} MB disponibles"
if (( available_after >= threshold_mb )); then
  log "verificado: memoria disponible sobre el umbral"
  exit 0
fi

fail "memoria sigue baja tras reiniciar $unit (${available_after} MB < ${threshold_mb} MB)"
