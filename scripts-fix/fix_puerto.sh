#!/usr/bin/env bash
# Modo 2 -- corrige un incidente port_occupied: detiene la unidad que ocupa
# indebidamente el puerto y reinicia la que se esperaba (tareas #199, #202).
#
# Solo actúa si la unidad que ocupa el puerto es una que el cliente ya
# vigila explícitamente (servicios_vigilados) -- ante un PID cuya unidad no
# se puede identificar, o que no está en esa lista, escala sin ejecutar
# nada (plan-finalizacion-mvp.md §4.2: "identidad incierta, escalar").
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=comun.sh
source "$DIR/comun.sh"

port="${1:-}"
[[ -n "$port" ]] || fail "uso: $0 <puerto>"

expected_unit=""
IFS=',' read -ra owners <<< "${DOCTORJK_PORT_OWNERS:-}"
for entry in "${owners[@]}"; do
  key="${entry%%=*}"
  value="${entry#*=}"
  if [[ "$key" == "$port" ]]; then
    expected_unit="$value"
    break
  fi
done
[[ -n "$expected_unit" ]] || fail "puerto $port no está en puertos_vigilados"

pid="$(ss -tlnp "sport = :$port" 2>/dev/null \
  | awk -F'pid=' 'NR>1 && /pid=/{split($2,a,","); print a[1]; exit}')"

if [[ -z "$pid" ]]; then
  log "nadie escucha en $port; nada que corregir (idempotente)"
  exit 0
fi

occupier_unit="$(systemctl status "$pid" --no-pager --lines=0 2>/dev/null | awk 'NR==1{print $2}')"
[[ -n "$occupier_unit" ]] \
  || fail "no pude identificar la unidad que ocupa el puerto $port (PID $pid); escalar sin actuar"

if [[ "$occupier_unit" == "$expected_unit" ]]; then
  log "$expected_unit ya tiene el puerto $port; nada que corregir (idempotente)"
  exit 0
fi

list_contains "$occupier_unit" "${DOCTORJK_MONITORED_SERVICES:-}" \
  || fail "unidad $occupier_unit no está vigilada; identidad no confiable, escalar sin actuar"

log "precondición: $occupier_unit ocupa el puerto $port en vez de $expected_unit"
run_or_announce systemctl stop "$occupier_unit"
run_or_announce systemctl restart "$expected_unit"

if is_dry_run; then
  log "[DRY-RUN] no se verifica postcondición"
  exit 0
fi

sleep 2
if systemctl is-active --quiet "$expected_unit"; then
  log "verificado: $expected_unit quedó activa en el puerto $port"
  exit 0
fi

fail "$expected_unit no quedó activa tras liberar el puerto $port"
