#!/usr/bin/env bash
# Utilidades compartidas por los scripts de infraestructura.
# Se hace `source`, no se ejecuta directamente.
#
# Existe por un fallo real: los tres scripts resolvian el tenancy con una
# sustitucion de comando que, bajo `set -e`, mataba al shell ANTES de llegar a
# su propio manejo de error. Resultado: --contar no imprimia absolutamente
# nada, y --listar mostraba un cartel de "RESTAURACION INTERRUMPIDA" siendo un
# comando de solo lectura. Ambos fallos venian de la misma linea repetida.

# Ruta de configuracion de OCI, respetando la variable estandar del CLI.
OCI_CONFIG="${OCI_CLI_CONFIG_FILE:-$HOME/.oci/config}"

comun_die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# Devuelve el tenancy OCID por stdout, o cadena vacia si no se puede resolver.
# NUNCA falla: el `|| true` evita que `set -e` mate al script antes de que el
# llamador pueda dar un mensaje util.
resolver_tenancy() {
  if [[ -n "${OCI_TENANCY_OCID:-}" ]]; then
    printf '%s' "$OCI_TENANCY_OCID"
    return 0
  fi
  [[ -r "$OCI_CONFIG" ]] || return 0
  awk -F= '/^tenancy/{gsub(/[ \r]/, "", $2); print $2; exit}' "$OCI_CONFIG" 2>/dev/null || true
}

# Comprueba que este equipo puede hablar con Oracle. Se llama al inicio de
# cualquier modo, incluidos los de solo lectura, para fallar con un mensaje que
# nombre la causa real en vez de con un error de OCI a medio camino.
exigir_oci() {
  if ! command -v oci >/dev/null 2>&1; then
    cat >&2 <<'FIN'

ERROR: el OCI CLI no esta instalado en este equipo.

  Estos scripts hablan con la API de Oracle Cloud, asi que solo corren desde
  una maquina con el CLI y credenciales -- normalmente tu portatil.

  NO funcionan dentro de beetle-vps: el VPS no tiene el CLI ni credenciales,
  y es a proposito. Si alguien compromete el servidor, no debe poder borrar
  los backups que sirven para recuperarlo.

  Desde el VPS, para listar snapshots usa el workflow de GitHub Actions:
    Actions -> "Restaurar beetle-vps desde snapshot" -> Run workflow
    (correrlo sin argumentos solo lista, no restaura nada)

  Para instalar el CLI en tu portatil:
    docs/runbook-snapshots.md

FIN
    exit 1
  fi

  if [[ -z "$(resolver_tenancy)" ]]; then
    cat >&2 <<FIN

ERROR: hay OCI CLI pero no encuentro las credenciales.

  Se busco el tenancy en:
    \$OCI_TENANCY_OCID   (variable de entorno)
    $OCI_CONFIG

  Si el CLI esta recien instalado, falta configurarlo:
    oci setup config

  Ver docs/runbook-snapshots.md

FIN
    exit 1
  fi
}
