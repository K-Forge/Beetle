#!/usr/bin/env bash
# Funciones compartidas por los scripts de scripts-fix/ (Modo 2, tareas
# #199-202). Se importa con `source`, nunca se ejecuta solo.
#
# Contrato que exige cada fix_*.sh (scripts-fix/README.md): cabecera
# set -euo pipefail, respeta DOCTORJK_DRY_RUN=1, código 0 solo si quedó
# resuelto y verificado, idempotente, mensajes en español a stdout/stderr.

log() {
  # Mensajes que el remediador guarda tal cual en la bitácora de auditoría
  # (tarea #201): sin datos sensibles, journald ya recibe la salida completa.
  printf '[%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

fail() {
  printf '[%s] ERROR: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2
  exit 1
}

# Verdadero si DOCTORJK_DRY_RUN=1. Cada fix_*.sh debe consultarlo antes de
# cualquier acción que cambie el estado del sistema (no antes de leer para
# verificar precondición/postcondición, eso es seguro siempre).
is_dry_run() {
  [[ "${DOCTORJK_DRY_RUN:-0}" == "1" ]]
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
# comas en $2 (p. ej. DOCTORJK_MONITORED_SERVICES). Comparación exacta, no
# substring: "nginx.service" no debe calzar con "nginx.service.bak".
list_contains() {
  local needle="$1" list="$2" item
  IFS=',' read -ra items <<< "$list"
  for item in "${items[@]}"; do
    [[ "$item" == "$needle" ]] && return 0
  done
  return 1
}
