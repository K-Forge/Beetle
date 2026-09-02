#!/usr/bin/env bash
# Restaura beetle-vps desde un boot volume backup.
#
# METODO: terminar y relanzar. En OCI un boot volume creado desde un backup NO se
# puede adjuntar a una instancia existente -- la API responde "It can only be
# attached to its parent instance". Solo sirve para LANZAR una instancia nueva.
# Un "swap de boot volume in-place" es imposible; no lo reintentes.
#
# Verificado end-to-end el 2026-08-18.
#
# Consecuencias que el operador debe conocer ANTES de correr esto:
#   - el OCID de la instancia cambia
#   - la IP privada cambia (no es fija)
#   - la IP publica NO cambia: BEETLE-IP es reservada y se reasigna al final
#   - el host key de SSH cambia -> hay que correr ssh-keygen -R en cada maquina
#   - Tailscale vuelve solo: su identidad vive en el disco restaurado
#
# Uso:  restaurar-snapshot.sh <nombre-del-backup>
#       restaurar-snapshot.sh --listar
#       restaurar-snapshot.sh --verificar

set -euo pipefail

AD="ODnr:SA-BOGOTA-1-AD-1"
NOMBRE_INSTANCIA="beetle-vps"
NOMBRE_IP_RESERVADA="BEETLE-IP"
SHAPE="VM.Standard.A1.Flex"
SHAPE_CONFIG='{"ocpus":2,"memoryInGBs":12}'

log()  { printf '[%s] %s\n' "$(date -u +%H:%M:%S)" "$*"; }
die()  { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

PASO_ACTUAL="inicio"
on_error() {
  printf '\n=========================================================\n' >&2
  printf '  RESTAURACION INTERRUMPIDA en: %s\n' "$PASO_ACTUAL" >&2
  printf '  Los backups NO se tocan nunca: sigues teniendo de donde\n'  >&2
  printf '  restaurar. Revisa que quedo vivo antes de reintentar:\n'    >&2
  printf '    oci compute instance list --compartment-id <tenancy>\n'   >&2
  printf '    oci bv boot-volume list --compartment-id <tenancy> \\\n'  >&2
  printf '        --availability-domain %s\n' "$AD"                     >&2
  printf '=========================================================\n' >&2
}
# OJO: el trap NO se arma aqui. Armarlo antes de los modos de solo lectura
# hacia que `--listar` y `--verificar` mostraran un cartel de "RESTAURACION
# INTERRUMPIDA" sin que hubiera ninguna restauracion en curso, lo cual alarma
# sin motivo. Se arma abajo, justo antes del primer paso que toca algo.

# shellcheck source=.github/scripts/comun.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/comun.sh"

exigir_oci
TENANCY="$(resolver_tenancy)"

# ---------------------------------------------------------------- verificacion
# Los nombres de subcomando y de flag del OCI CLI no son adivinables, y un typo
# aqui no se descubre hasta que el script ya destruyo algo. Tres bugs reales que
# esto habria atrapado: "delete" en vez de "detach";
# --source-boot-volume-backup-id en vez de --boot-volume-backup-id; y
# --wait-for-state TERMINATED en terminate, que espera estados de work request.
verificar_comandos() {
  local fallos=0
  _chk() {
    if oci $1 --help 2>/dev/null | grep -q -- "$2"; then
      printf '  ok   : oci %s %s\n' "$1" "$2"
    else
      printf '  FALTA: oci %s %s\n' "$1" "$2" >&2
      fallos=$((fallos + 1))
    fi
  }
  echo "Validando comandos del OCI CLI..."
  _chk "bv boot-volume-backup list"    "--compartment-id"
  _chk "bv boot-volume create"         "--boot-volume-backup-id"
  _chk "compute instance terminate"    "--preserve-boot-volume"
  _chk "compute instance launch"       "--source-details"
  _chk "compute instance list-vnics"   "--instance-id"
  _chk "network public-ip update"      "--private-ip-id"
  (( fallos == 0 )) || die "$fallos comando(s) no coinciden con este OCI CLI. No se ejecuta nada."
  echo "Comandos validados."
}

if [[ "${1:-}" == "--verificar" ]]; then verificar_comandos; exit 0; fi

if [[ "${1:-}" == "--listar" ]]; then
  oci bv boot-volume-backup list --compartment-id "$TENANCY" --all \
    --query 'sort_by(data[?"lifecycle-state"==`AVAILABLE`],&"time-created")[].{nombre:"display-name",creado:"time-created",gb:"unique-size-in-gbs"}' \
    --output table
  exit 0
fi

BACKUP_NAME="${1:-}"
[[ -n "$BACKUP_NAME" ]] || die "falta el nombre del backup. Usa --listar para verlos."

verificar_comandos

# ------------------------------------------------------------------ inventario
log "Buscando backup '$BACKUP_NAME'..."
BACKUP_OCID=$(oci bv boot-volume-backup list --compartment-id "$TENANCY" --all \
  --query "data[?\"display-name\"=='$BACKUP_NAME' && \"lifecycle-state\"=='AVAILABLE'].id | [0]" \
  --raw-output 2>/dev/null)
[[ -n "$BACKUP_OCID" && "$BACKUP_OCID" != "null" ]] \
  || die "no existe un backup AVAILABLE llamado '$BACKUP_NAME'."
log "Backup AVAILABLE."

# La instancia se busca por nombre, no por OCID: cada restauracion crea una nueva
# y un OCID hardcodeado queda obsoleto en cuanto restauras una vez.
INST=$(oci compute instance list --compartment-id "$TENANCY" --all \
  --query "data[?\"display-name\"=='$NOMBRE_INSTANCIA' && \"lifecycle-state\"!='TERMINATED'].id | [0]" \
  --raw-output 2>/dev/null)
[[ -n "$INST" && "$INST" != "null" ]] || die "no encontre una instancia viva llamada '$NOMBRE_INSTANCIA'."

SUBNET=$(oci compute instance list-vnics --instance-id "$INST" --query 'data[0]."subnet-id"' --raw-output)
RESIP=$(oci network public-ip list --compartment-id "$TENANCY" --scope REGION --all \
  --query "data[?\"display-name\"=='$NOMBRE_IP_RESERVADA'].id | [0]" --raw-output 2>/dev/null)
[[ -n "$RESIP" && "$RESIP" != "null" ]] || die "no encontre la IP reservada '$NOMBRE_IP_RESERVADA'."

cat <<BANNER

  A punto de restaurar $NOMBRE_INSTANCIA
  ---------------------------------------------------------------
  Backup origen : $BACKUP_NAME
  Metodo        : se TERMINA la instancia y se lanza una nueva
  IP publica    : se conserva ($NOMBRE_IP_RESERVADA es reservada)
  IP privada    : CAMBIA
  Host key SSH  : CAMBIA -> ssh-keygen -R en cada maquina del equipo
  Downtime      : ~10-20 min

  Todo lo que este en el disco y no este en el backup SE PIERDE.
  ---------------------------------------------------------------

BANNER

if [[ "${RESTORE_CONFIRMADO:-}" != "si" ]]; then
  read -r -p "Escribe 'restaurar' para continuar: " answer
  [[ "$answer" == "restaurar" ]] || die "cancelado por el operador."
fi

# ------------------------------------------------------------------- ejecucion
# Se termina con --preserve-boot-volume false a proposito: el disco viejo ocupa
# 150 GB de los 200 GB gratuitos, y sin liberarlos no cabe el nuevo. El backup ya
# esta verificado como AVAILABLE, asi que el punto de restauracion esta a salvo.
# A partir de aqui si se toca el servidor: ahora el trap tiene sentido.
trap on_error ERR

PASO_ACTUAL="terminar la instancia vieja"
log "1/4 Terminando la instancia vieja y su boot volume..."
oci compute instance terminate --instance-id "$INST" --force --preserve-boot-volume false \
  --wait-for-state SUCCEEDED --max-wait-seconds 900 >/dev/null
log "     Terminada; OCPUs y disco liberados."

PASO_ACTUAL="crear boot volume desde el backup"
log "2/4 Creando boot volume desde el backup..."
NEW_BV=$(oci bv boot-volume create --availability-domain "$AD" --compartment-id "$TENANCY" \
  --boot-volume-backup-id "$BACKUP_OCID" \
  --display-name "${NOMBRE_INSTANCIA}-restaurado-$(date -u +%Y%m%d-%H%M)" \
  --wait-for-state AVAILABLE --max-wait-seconds 1800 --query 'data.id' --raw-output)
log "     Creado."

PASO_ACTUAL="lanzar la instancia nueva"
log "3/4 Lanzando la instancia nueva..."
NEW_INST=$(oci compute instance launch --availability-domain "$AD" --compartment-id "$TENANCY" \
  --shape "$SHAPE" --shape-config "$SHAPE_CONFIG" \
  --source-details "{\"sourceType\":\"bootVolume\",\"bootVolumeId\":\"$NEW_BV\"}" \
  --subnet-id "$SUBNET" --display-name "$NOMBRE_INSTANCIA" --assign-public-ip false \
  --wait-for-state RUNNING --max-wait-seconds 1800 --query 'data.id' --raw-output)
log "     Corriendo: $NEW_INST"

PASO_ACTUAL="reasignar la IP reservada"
log "4/4 Reasignando $NOMBRE_IP_RESERVADA..."
VNIC=$(oci compute instance list-vnics --instance-id "$NEW_INST" --query 'data[0].id' --raw-output)
PRIV=$(oci network private-ip list --vnic-id "$VNIC" --query 'data[0].id' --raw-output)
oci network public-ip update --public-ip-id "$RESIP" --private-ip-id "$PRIV" >/dev/null
log "     Reasignada."

IP=$(oci compute instance list-vnics --instance-id "$NEW_INST" --query 'data[0]."public-ip"' --raw-output)

cat <<FIN

  Restauracion completa.
  IP publica: $IP  (sin cambios)

  ANTES de conectarte, en cada maquina del equipo:
      ssh-keygen -R $IP
  El host key cambio porque la maquina se reconstruyo. Si no lo haces, SSH
  aborta con una advertencia de man-in-the-middle.

  Tailscale deberia volver solo (su identidad viene en el disco). Si no
  aparece en ~2 min, entra por la IP publica y corre:
      sudo tailscale up --force-reauth

FIN
