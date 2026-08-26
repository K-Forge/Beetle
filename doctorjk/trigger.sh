#!/usr/bin/env bash
# Deteccion en tiempo real: escucha el journal y avisa al agente ante un error
# puntual, sin esperar al siguiente ciclo del monitor.
#
# Complementa a monitor.py, no lo reemplaza. El polling de 30 s cubre condiciones
# que se sostienen (disco llenandose, memoria bajando); este trigger cubre lo que
# pasa de golpe -- un servicio que muere, un OOM kill -- donde 30 s de retraso
# bastan para que la evidencia ya no este.
#
# Corre como proceso de fondo junto al monitor, en su propia unidad systemd
# (doctorjk-trigger.service, Gate E). Los mensajes van a journald.
#
# CONTRATO FIFO (plan-mvp.md §3.1): este script NO lanza el agente ni declara
# incidentes. doctorjk/main.py es el unico dueno del estado -- mantiene abierto
# un FIFO local y corre su propio detector residente. Este script solo escribe
# una senal fija en ese FIFO cuando ve una linea relevante; main.py toma la
# muestra real. Tampoco repite la linea cruda del journal en su propio log: esa
# linea puede traer datos sensibles y el agente ya la puede recuperar del
# journal si hace falta.
#
# POR QUE -p warning Y NO -p err (la tarea #172 pedia -p err):
# systemd NO registra la caida de un servicio como error. Medido en beetle-vps
# matando PostgreSQL con SIGKILL:
#
#   "Control process exited, code=exited"   -> prioridad 5 (notice)
#   "Failed with result 'exit-code'"        -> prioridad 4 (warning)
#
# Con -p err (prioridades 0-3) el trigger queda CIEGO ante exactamente el
# incidente que el agente existe para atrapar. Se usa -p warning, que cubre 0-4.
# El ruido extra que eso trae se corta con IGNORE_PATTERNS y con el cooldown.

set -euo pipefail

# --------------------------------------------------------------- configuracion

# Mismo FIFO que abre doctorjk/main.py. Una sola variable de entorno para que
# la unidad systemd de ambos procesos la fije igual (Gate E).
FIFO_PATH="${DOCTORJK_FIFO_PATH:-/run/doctorjk/trigger.fifo}"

# Ventana de silencio tras disparar. Un incidente real no produce una linea de
# error, produce una rafaga: PostgreSQL cayendose escribe decenas en segundos.
# Sin esto se escribiria en el FIFO por cada linea y se saturaria el ciclo del
# agente con la misma rafaga una y otra vez.
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
  "ssh-session("                    # tailscaled anota cada sesion SSH del equipo
  "Deactivated successfully"        # systemd al cerrar unidades de rutina
  "Stopped target"
  "session-c"                       # sesiones de login abriendo y cerrando
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

notify_agent() {
  # No se registra la linea cruda ($1): solo que hubo una senal. El agente ya
  # puede ir al journal si necesita el detalle, y asi este log nunca duplica
  # algo potencialmente sensible.
  log "linea relevante detectada, senal enviada al orquestador"

  # abrir un FIFO en escritura (">") bloquea hasta que alguien lo tenga
  # abierto en lectura. Si main.py no esta corriendo, eso colgaria este loop
  # entero y el trigger dejaria de escuchar el journal. Se acota con timeout
  # en vez de confiar en que main.py siempre este arriba.
  if ! timeout 2 bash -c "printf '1\n' > '$FIFO_PATH'" 2>/dev/null; then
    log "no se pudo escribir en $FIFO_PATH; el orquestador no esta escuchando?"
  fi
}

# ------------------------------------------------------------------- ejecucion

command -v journalctl >/dev/null 2>&1 || {
  echo "journalctl no esta disponible; este agente requiere systemd" >&2
  exit 1
}

log "trigger iniciado (cooldown ${COOLDOWN_S}s, fifo: ${FIFO_PATH})"

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
  notify_agent "$line"
done < <(journalctl -f -p warning -o short-iso -n 0)

# Solo se llega aqui si journalctl murio. systemd reinicia la unidad.
log "journalctl termino inesperadamente; saliendo para que systemd reinicie"
exit 1
