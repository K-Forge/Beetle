#!/usr/bin/env bash
# Abre TCP/22 en el security list del VPS para una IP concreta.
#
# Existe porque la regla de SSH esta anclada a una IP y las IPs domesticas
# cambian al moverse de red. En vez de abrir el puerto al mundo, se reescribe la
# regla en 5 segundos cuando hace falta.
#
# Cada persona tiene su propia regla, identificada por etiqueta. Al reejecutarlo
# con la misma etiqueta se REEMPLAZA su regla anterior, no se acumulan.
#
# Uso:  abrir-ssh.sh brian              # usa tu IP publica actual
#       abrir-ssh.sh mauricio 1.2.3.4   # IP explicita
#       abrir-ssh.sh --listar
#       abrir-ssh.sh --quitar mauricio

set -euo pipefail

SUBNET=ocid1.subnet.oc1.sa-bogota-1.aaaaaaaagbh4dmxogd3jjzkoe7tfki2arn7owfg6qd7rkfqzogjs43sala5a
PREFIJO="SSH gestionado:"   # marca las reglas que este script administra

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

SL=$(oci network subnet get --subnet-id "$SUBNET" --query 'data."security-list-ids"[0]' --raw-output) \
  || die "no pude leer la subred. Revisa las credenciales de OCI."

reglas_actuales() {
  oci network security-list get --security-list-id "$SL" \
    --query 'data."ingress-security-rules"' --output json
}

if [[ "${1:-}" == "--listar" ]]; then
  reglas_actuales | python3 -c "
import json,sys
for r in json.load(sys.stdin):
    d = r.get('description') or '(sin descripcion)'
    proto = {'6':'TCP','17':'UDP','1':'ICMP'}.get(r.get('protocol'), r.get('protocol'))
    print(f\"  {proto:5} {r.get('source'):20} {d}\")
"
  exit 0
fi

QUITAR=""
if [[ "${1:-}" == "--quitar" ]]; then
  QUITAR="${2:-}"
  [[ -n "$QUITAR" ]] || die "falta la etiqueta a quitar."
  ETIQUETA="$QUITAR"
else
  ETIQUETA="${1:-}"
  [[ -n "$ETIQUETA" ]] || die "falta la etiqueta (ej: brian). Usa --listar para ver las reglas."
  IP="${2:-}"
  if [[ -z "$IP" ]]; then
    IP=$(curl -s --max-time 10 https://ifconfig.me) || die "no pude averiguar tu IP publica."
    [[ -n "$IP" ]] || die "no pude averiguar tu IP publica."
    echo "IP publica detectada: $IP"
  fi
  # Validacion minima: que parezca una IPv4 y no un mensaje de error del servicio.
  [[ "$IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || die "'$IP' no parece una IPv4."
fi

reglas_actuales > /tmp/ingress-previo.json
echo "Respaldo de las reglas actuales: /tmp/ingress-previo.json"

DESC="$PREFIJO $ETIQUETA"
python3 - "$DESC" "${IP:-}" "$QUITAR" <<'PY'
import json, sys
desc, ip, quitar = sys.argv[1], sys.argv[2], sys.argv[3]
reglas = json.load(open('/tmp/ingress-previo.json'))

# Fuera la regla previa de esta etiqueta: se reemplaza, no se acumula.
reglas = [r for r in reglas if (r.get('description') or '') != desc]

if not quitar:
    reglas.append({
        "description": desc, "icmp-options": None, "is-stateless": False,
        "protocol": "6", "source": f"{ip}/32", "source-type": "CIDR_BLOCK",
        "tcp-options": {"destination-port-range": {"max": 22, "min": 22},
                        "source-port-range": None},
        "udp-options": None,
    })

json.dump(reglas, open('/tmp/ingress-nuevo.json', 'w'), indent=2)
print(f"{len(reglas)} reglas resultantes")
PY

oci network security-list update --security-list-id "$SL" \
  --ingress-security-rules file:///tmp/ingress-nuevo.json --force \
  --query 'data."ingress-security-rules"[].{proto:protocol,origen:source,desc:description}' \
  --output table

echo
if [[ -n "$QUITAR" ]]; then
  echo "Regla de '$ETIQUETA' eliminada."
else
  echo "Listo. '$ETIQUETA' puede entrar por SSH desde $IP."
  echo "Si cambias de red, vuelve a correr: abrir-ssh.sh $ETIQUETA"
fi
