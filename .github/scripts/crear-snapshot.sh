#!/usr/bin/env bash
# Crea un snapshot (boot volume backup) de beetle-vps.
#
# El tier gratuito de Oracle permite 5 backups (free-backup-count = 5). NO esta
# verificado que Oracle rechace el sexto en vez de cobrarlo, asi que este script
# lo BLOQUEA por su cuenta: prefiere fallar a arriesgar un cargo inesperado.
#
# Uso:  crear-snapshot.sh <motivo>     # ej: crear-snapshot.sh limpio
#       crear-snapshot.sh --contar

set -euo pipefail

AD="ODnr:SA-BOGOTA-1-AD-1"
NOMBRE_INSTANCIA="beetle-vps"
LIMITE_GRATIS=5

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

TENANCY="${OCI_TENANCY_OCID:-$(awk -F= '/^tenancy/{print $2; exit}' "${OCI_CLI_CONFIG_FILE:-$HOME/.oci/config}" 2>/dev/null | tr -d ' \r')}"
[[ -n "$TENANCY" ]] || die "no pude determinar el tenancy OCID."

# Solo cuentan los que ocupan espacio; los TERMINATED ya no.
contar() {
  oci bv boot-volume-backup list --compartment-id "$TENANCY" --all \
    --query 'length(data[?"lifecycle-state"!=`TERMINATED`])' --raw-output 2>/dev/null || echo 0
}

ACTUALES=$(contar)

if [[ "${1:-}" == "--contar" ]]; then
  echo "Snapshots vivos: $ACTUALES de $LIMITE_GRATIS gratuitos."
  oci bv boot-volume-backup list --compartment-id "$TENANCY" --all \
    --query 'sort_by(data[?"lifecycle-state"!=`TERMINATED`],&"time-created")[].{nombre:"display-name",creado:"time-created",estado:"lifecycle-state"}' \
    --output table
  exit 0
fi

MOTIVO="${1:-}"
[[ -n "$MOTIVO" ]] || die "falta el motivo. Ej: crear-snapshot.sh limpio"

# La salvaguarda: no se intenta crear el sexto.
if (( ACTUALES >= LIMITE_GRATIS )); then
  cat >&2 <<FIN

  BLOQUEADO: ya hay $ACTUALES snapshots y el limite gratuito es $LIMITE_GRATIS.

  No se intenta crear otro porque no esta confirmado si Oracle lo rechaza o lo
  cobra. Borra uno primero:

      oci bv boot-volume-backup delete --boot-volume-backup-id <ocid> --force

  Para verlos:  crear-snapshot.sh --contar

FIN
  exit 1
fi

INST=$(oci compute instance list --compartment-id "$TENANCY" --all \
  --query "data[?\"display-name\"=='$NOMBRE_INSTANCIA' && \"lifecycle-state\"!='TERMINATED'].id | [0]" \
  --raw-output 2>/dev/null)
[[ -n "$INST" && "$INST" != "null" ]] || die "no encontre la instancia '$NOMBRE_INSTANCIA'."

BV=$(oci compute boot-volume-attachment list --compartment-id "$TENANCY" \
  --availability-domain "$AD" --instance-id "$INST" \
  --query 'data[?"lifecycle-state"==`ATTACHED`]."boot-volume-id" | [0]' --raw-output)
[[ -n "$BV" && "$BV" != "null" ]] || die "no encontre el boot volume adjunto."

NOMBRE="beetle-${MOTIVO}-$(date -u +%Y-%m-%d-%H%M)"
echo "Creando '$NOMBRE' (quedaran $((ACTUALES + 1)) de $LIMITE_GRATIS)..."

oci bv boot-volume-backup create --boot-volume-id "$BV" --display-name "$NOMBRE" \
  --type FULL --wait-for-state AVAILABLE --max-wait-seconds 1800 \
  --query 'data.{nombre:"display-name",estado:"lifecycle-state"}' --output table

echo
echo "Listo. Snapshots vivos: $(contar) de $LIMITE_GRATIS."
