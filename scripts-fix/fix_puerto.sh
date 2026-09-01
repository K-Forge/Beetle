#!/usr/bin/env bash
# Modo 2 -- corrige un incidente port_occupied: detiene la unidad que ocupa
# indebidamente el puerto y reinicia la que se esperaba (tareas #199, #202).
#
# Solo actúa si la unidad que ocupa el puerto está en ocupantes_puerto_aprobados
# -- ante un PID cuya unidad no se puede identificar, o que no está en esa
# lista, escala sin ejecutar nada (plan-finalizacion-mvp.md §4.2: "identidad
# incierta, escalar").
#
# Deliberadamente NO se usa servicios_vigilados para esto (hallazgo de
# auditoría P0, 2026-09-01): esa lista dice qué vigilar, no qué está
# aprobado para detener. Si una unidad ocupante figurara en
# servicios_vigilados, detenerla dispararía service_failed sobre ella
# misma y fix_servicio.sh la reiniciaría -- pudiendo recrear
# port_occupied en bucle. ocupantes_puerto_aprobados es una allowlist
# separada, explícita, y vacía por defecto.
#
# Postcondición real (hallazgo de auditoría #3, 2026-09-01): que la unidad
# esperada esté "active" no prueba que haya vuelto a enlazar el puerto --
# puede seguir arrancando o haber fallado el bind por otra razón. Se
# verifica con `ss` que alguien escucha ahí Y que es la unidad esperada.
#
# Si nadie escucha al momento de remediar (revisión post-commit,
# 2026-09-01: el ocupante indebido pudo haber desaparecido solo entre la
# detección y esta corrida), NO se declara resuelto por default: el
# incidente original era que la unidad esperada no tenía el puerto, y
# sigue sin tenerlo. Se reinicia igual y se verifica con `ss`, sin el paso
# de detener a nadie (no hay a quién detener).
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

if [[ -n "$pid" ]]; then
  occupier_unit="$(unit_for_pid "$pid")"
  [[ -n "$occupier_unit" ]] \
    || fail "no pude identificar la unidad que ocupa el puerto $port (PID $pid); escalar sin actuar"

  if [[ "$occupier_unit" == "$expected_unit" ]]; then
    log "$expected_unit ya tiene el puerto $port; nada que corregir (idempotente)"
    exit 0
  fi

  approved="$(read_config_attr approved_port_occupants)"
  list_contains "$occupier_unit" "$approved" \
    || fail "unidad $occupier_unit no está en ocupantes_puerto_aprobados; no autorizada para detener, escalar sin actuar"

  log "precondición: $occupier_unit ocupa el puerto $port en vez de $expected_unit"
  run_or_announce systemctl stop "$occupier_unit"
else
  # Nadie escucha: no hay a quién detener, pero $expected_unit tampoco
  # tiene el puerto -- el incidente original (port_occupied) sigue sin
  # resolverse hasta que $expected_unit vuelva a enlazarlo de verdad.
  log "precondición: nadie escucha en $port; $expected_unit tampoco lo tiene todavía"
fi

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
