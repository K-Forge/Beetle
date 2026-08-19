#!/usr/bin/env bash
# Deteccion en tiempo real: escucha el journal y dispara el agente ante un error
# puntual, sin esperar al siguiente ciclo del monitor.
#
# Complementa a monitor.py, no lo reemplaza. El polling de 30 s cubre condiciones
# que se sostienen (disco llenandose, memoria bajando); este trigger cubre lo que
# pasa de golpe -- un servicio que muere, un OOM kill -- donde 30 s de retraso
# bastan para que la evidencia ya no este.
#
# Corre como proceso de fondo junto al monitor. Los mensajes van a journald.

set -euo pipefail

# --------------------------------------------------------------- configuracion

# Como se invoca el agente. Se deja en una sola variable porque doctorjk/main.py
# todavia no existe: cuando exista, esto es lo unico que cambia.
AGENT_CMD="${DOCTORJK_AGENT_CMD:-/usr/bin/python3 -m doctorjk.main}"

# Ventana de silencio tras disparar. Un incidente real no produce una linea de
# error, produce una rafaga: PostgreSQL cayendose escribe decenas en segundos.
# Sin esto se lanzaria un agente por linea y se saturaria la maquina que se
# supone estamos diagnosticando.
COOLDOWN_S="${DOCTORJK_TRIGGER_COOLDOWN:-120}"

LOG_TAG="doctorjk-trigger"

# Errores conocidos e inofensivos. Ruido recurrente que no es un incidente y que,
# de no filtrarse, gastaria una llamada al LLM cada vez.
IGNORE_PATTERNS=(
  "Failed to get AppArmor"          # avisos de systemd en contenedores/VMs
  "Could not resolve host"          # DNS intermitente, no es caida del servidor
  "Broken pipe"                     # cliente que corta la conexion
  "Connection reset by peer"
  "audit:"                          # auditd es verboso y no diagnostica nada
)

log() { logger -t "$LOG_TAG" -- "$*"; }

# ------------------------------------------------------------------- funciones

# Verdadero si la linea es ruido conocido y no debe disparar nada.
is_ignorable() {
  local line="$1" pattern
  for pattern in "${IGNORE_PATTERNS[@]}"; do
    [[ "$line" == *"$pattern"* ]] && return 0
  done
  return 1
}

# El agente escribe sus propios errores al journal. Si esos errores volvieran a
# dispararlo, se realimentaria en bucle hasta tumbar el servidor.
is_self() {
  [[ "$1" == *"doctorjk"* ]]
}

fire_agent() {
  log "error detectado, lanzando el agente: $1"
  # En segundo plano a proposito: si el agente tarda, el trigger tiene que seguir
  # escuchando en vez de quedarse ciego mientras diagnostica.
  # shellcheck disable=SC2086
  setsid $AGENT_CMD >/dev/null 2>&1 < /dev/null &
}

# ------------------------------------------------------------------- ejecucion

command -v journalctl >/dev/null 2>&1 || {
  echo "journalctl no esta disponible; este agente requiere systemd" >&2
  exit 1
}

log "trigger iniciado (cooldown ${COOLDOWN_S}s, agente: ${AGENT_CMD})"

last_fire=0

# -n 0 es deliberado: sin el, journalctl reproduce el historial al arrancar y el
# trigger dispararia por errores viejos en cada reinicio del servicio.
while IFS= read -r line; do
  [[ -n "$line" ]] || continue
  is_ignorable "$line" && continue
  is_self "$line" && continue

  now=$(date +%s)
  if (( now - last_fire < COOLDOWN_S )); then
    # Se ignora en silencio: es la rafaga del incidente que ya se esta atendiendo.
    continue
  fi

  last_fire="$now"
  fire_agent "$line"
done < <(journalctl -f -p err -o short-iso -n 0)

# Solo se llega aqui si journalctl murio. systemd reinicia la unidad.
log "journalctl termino inesperadamente; saliendo para que systemd reinicie"
exit 1
