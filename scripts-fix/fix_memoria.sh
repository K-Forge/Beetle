#!/usr/bin/env bash
# Modo 2 -- corrige un incidente memory_low: reinicia la ÚNICA unidad
# aprobada explícitamente en config.toml (unidad_memoria_aprobada) para
# liberar la memoria que retiene (tareas #199, #202).
#
# Sin unidad aprobada, este script escala en vez de actuar: no mata
# procesos arbitrarios ni escribe a /proc/sys/vm/drop_caches
# (plan-finalizacion-mvp.md §4.2 -- ambos quedan explícitamente prohibidos).
#
# Precondición de cgroup (hallazgo de auditoría #4, ajustado 2026-09-01):
# memoria global baja no prueba que la unidad aprobada sea la responsable.
# No hay en este repo un criterio de producto para "consumidor anómalo" más
# allá de los datos que ya se leen acá, así que NO se inventa un porcentaje
# fijo. El piso que sí se puede justificar con datos existentes: si el
# cgroup de la unidad aprobada no alcanza siquiera el déficit entre memoria
# disponible y el umbral (lo mínimo que haría falta liberar para cruzar de
# vuelta el umbral en el mejor caso, liberando el 100% de lo que usa), es
# matemáticamente imposible que reiniciarla resuelva el incidente -- se
# escala sin actuar. Que SÍ alcance el déficit NO prueba que sea la causa
# real (no hay aquí forma de correlacionar con el inicio del incidente ni
# de descartar otros procesos): es un piso necesario, no una identificación
# causal. La responsabilidad de que sea razonable reiniciar esa unidad ante
# memoria baja ya la tomó un humano al aprobarla en config.toml; este
# script solo evita reiniciarla cuando los propios números dicen que ni
# siquiera podría ayudar.
#
# No recibe recurso por $1: la unidad ya viene fijada por config, no por el
# incidente (memory_low es una señal global, sin un `resource_key`
# específico que apuntar). config.toml se lee siempre de la ruta fija que
# define comun.sh (ver esa cabecera para el porqué).
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=comun.sh
source "$DIR/comun.sh"

unit="$(read_config_attr approved_memory_unit)"
[[ -n "$unit" ]] || fail "sin unidad_memoria_aprobada configurada; escalar sin actuar"

threshold_mb="$(read_config_attr memory_available_mb_threshold)"

available_mb() {
  free -m | awk '/^Mem:/{print $7}'
}

unit_memory_mb() {
  local bytes
  bytes="$(systemctl show "$1" --property=MemoryCurrent --value 2>/dev/null)"
  [[ "$bytes" =~ ^[0-9]+$ ]] || { echo ""; return; }
  echo $(( bytes / 1024 / 1024 ))
}

available="$(available_mb)" || true
[[ -n "$available" ]] || fail "no pude leer memoria disponible"

log "precondición: ${available} MB disponibles (umbral ${threshold_mb} MB)"
if (( available >= threshold_mb )); then
  log "ya hay memoria suficiente; nada que corregir (idempotente)"
  exit 0
fi

deficit=$(( threshold_mb - available ))

unit_mem="$(unit_memory_mb "$unit")"
[[ -n "$unit_mem" ]] \
  || fail "no pude leer MemoryCurrent de $unit (MemoryAccounting deshabilitado?); escalar sin actuar"

log "precondición de cgroup: $unit usa ${unit_mem} MB; déficit a cubrir ${deficit} MB"
if (( unit_mem < deficit )); then
  fail "$unit usa menos memoria (${unit_mem} MB) que el déficit (${deficit} MB); " \
    "liberarla no alcanzaría a cruzar el umbral, escalar sin actuar"
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
