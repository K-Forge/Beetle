#!/usr/bin/env bash
# Modo 2 -- corrige un incidente port_occupied: detiene la unidad que ocupa
# indebidamente el puerto y reinicia la que se esperaba (tareas #199, #202).
#
# Solo actúa si la unidad que ocupa el puerto es una que el cliente ya
# vigila explícitamente (servicios_vigilados) -- ante un PID cuya unidad no
# se puede identificar, o que no está en esa lista, escala sin ejecutar
# nada (plan-finalizacion-mvp.md §4.2: "identidad incierta, escalar").
#
# Postcondición real (hallazgo de auditoría #3, 2026-09-01): que la unidad
# esperada esté "active" no prueba que haya vuelto a enlazar el puerto --
# puede seguir arrancando o haber fallado el bind por otra razón. Se
# verifica con `ss` que alguien escucha ahí Y que es la unidad esperada.
#
# $1 = puerto. config.toml se lee de la ruta fija que define comun.sh (no
# es un argumento; ver esa cabecera).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=comun.sh
source "$DIR/comun.sh"

port="${1:-}"
[[ -n "$port" ]] || fail "uso: $0 <puerto>"

listening_pid() {
  ss -tlnp "sport = :$port" 2>/dev/null \
    | awk -F'pid=' 'NR>1 && /pid=/{split($2,a,","); print a[1]; exit}'
}

unit_for_pid() {
  systemctl status "$1" --no-pager --lines=0 2>/dev/null | awk 'NR==1{print $2}'
}

port_owners="$(read_config_attr monitored_ports)"
expected_unit=""
IFS=',' read -ra owners <<< "$port_owners"
for entry in "${owners[@]}"; do
  key="${entry%%=*}"
  value="${entry#*=}"
  if [[ "$key" == "$port" ]]; then
    expected_unit="$value"
    break
  fi
done
[[ -n "$expected_unit" ]] || fail "puerto $port no está en puertos_vigilados"

pid="$(listening_pid)"
if [[ -z "$pid" ]]; then
  log "nadie escucha en $port; nada que corregir (idempotente)"
  exit 0
fi

occupier_unit="$(unit_for_pid "$pid")"
[[ -n "$occupier_unit" ]] \
  || fail "no pude identificar la unidad que ocupa el puerto $port (PID $pid); escalar sin actuar"

if [[ "$occupier_unit" == "$expected_unit" ]]; then
  log "$expected_unit ya tiene el puerto $port; nada que corregir (idempotente)"
  exit 0
fi

monitored="$(read_config_attr monitored_services)"
list_contains "$occupier_unit" "$monitored" \
  || fail "unidad $occupier_unit no está vigilada; identidad no confiable, escalar sin actuar"

log "precondición: $occupier_unit ocupa el puerto $port en vez de $expected_unit"
run_or_announce systemctl stop "$occupier_unit"
run_or_announce systemctl restart "$expected_unit"

if is_dry_run; then
  log "[DRY-RUN] no se verifica postcondición"
  exit 0
fi

sleep 2
if ! systemctl is-active --quiet "$expected_unit"; then
  fail "$expected_unit no quedó activa tras liberar el puerto $port"
fi

new_pid="$(listening_pid)"
if [[ -z "$new_pid" ]]; then
  fail "$expected_unit está activa pero nadie escucha en $port todavía"
fi

new_occupier="$(unit_for_pid "$new_pid")"
if [[ "$new_occupier" != "$expected_unit" ]]; then
  fail "el puerto $port lo tiene $new_occupier, no $expected_unit -- verificado con ss"
fi

log "verificado con ss: $expected_unit escucha en el puerto $port"
