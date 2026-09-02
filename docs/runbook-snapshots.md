# Runbook — snapshots del VPS

Cómo crear, listar y encontrar los snapshots de `beetle-vps`, y qué hacer
cuando un script no responde como esperabas.

Para **restaurar** desde un snapshot, ver [runbook-restore.md](runbook-restore.md).

---

## 1. Dónde se guardan los snapshots

No están en ningún bucket ni en ningún archivo tuyo: los gestiona el servicio
**Block Volume** de Oracle, dentro de la región. No ocupan tu cuota de 200 GB de
almacenamiento en bloque — se cuentan aparte, por cantidad (máximo 5 gratuitos).

### En la consola web

```
Menú ☰  →  Storage  →  Block Storage  →  Boot Volume Backups
```

Enlace directo, ya con la región puesta:

<https://cloud.oracle.com/block-storage/boot-volume-backups?region=sa-bogota-1>

### Las tres razones por las que no los encuentras

| Síntoma | Causa |
|---|---|
| La lista sale vacía | Estás mirando **otra región**. Los nuestros están en `sa-bogota-1` (Bogotá). El selector de región está arriba a la derecha |
| Estás en *Block Volume Backups* y no aparecen | Son dos listas distintas. Los nuestros son de **Boot** Volume, el disco de arranque |
| Buscaste en Compute | Los backups no cuelgan de la instancia; viven en Storage aunque sean de un disco de arranque |

Todos están en el **compartimento raíz** (no hay sub-compartimentos en esta
tenancy), así que el selector de compartimento de la izquierda debe estar en la
raíz, no en uno hijo.

### Qué significan las columnas

- **Size** son los 150 GB del volumen original, no lo que ocupa el backup.
- El espacio real es el *unique size*: hoy ~9 GB, porque el disco está casi vacío.

---

## 2. Desde dónde se ejecutan los scripts

**Desde tu portátil, nunca desde el VPS.**

El VPS no tiene el OCI CLI ni credenciales de Oracle, y es deliberado: si
alguien compromete el servidor, no debe poder borrar los backups que sirven
justamente para recuperarlo.

Si los corres allá, ahora te lo dicen con un mensaje claro. Antes uno fallaba en
silencio y otro mostraba un cartel de "RESTAURACIÓN INTERRUMPIDA" sin que
hubiera ninguna restauración en curso — un fallo real, ya corregido.

**Sin credenciales de Oracle** (Mauricio, por ejemplo) se listan desde GitHub:
**Actions → "Restaurar beetle-vps desde snapshot" → Run workflow**. Correrlo sin
llenar los campos **solo lista**, no restaura nada.

---

## 3. Preparar tu portátil

Solo hace falta una vez.

```bash
# 1. Instalar el CLI
brew install oci-cli

# 2. Configurarlo (pide tenancy OCID, user OCID, fingerprint y región)
oci setup config
```

La región es `sa-bogota-1`. Al terminar queda `~/.oci/config`.

**Comprobar que quedó bien:**

```bash
oci iam region list --output table
```

Si eso responde, todo lo demás funciona.

---

## 4. Uso diario

Siempre desde la raíz del repositorio.

### Ver cuántos snapshots hay

```bash
.github/scripts/crear-snapshot.sh --contar
```

### Crear uno

```bash
.github/scripts/crear-snapshot.sh <motivo>
```

El motivo es una palabra corta que explique para qué es. Queda nombrado
`beetle-<motivo>-AAAA-MM-DD-HHMM`, por ejemplo:

```bash
.github/scripts/crear-snapshot.sh antes-de-fase-8
# -> beetle-antes-de-fase-8-2026-09-02-0051
```

Tarda 1–3 minutos. El script espera hasta que el snapshot queda `AVAILABLE`;
si sale antes, no está listo todavía.

### Listar los que se pueden restaurar

```bash
.github/scripts/restaurar-snapshot.sh --listar
```

### Comprobar que el script sigue sirviendo

```bash
.github/scripts/restaurar-snapshot.sh --verificar
```

Valida que cada subcomando y flag que usa exista en tu versión del OCI CLI, sin
ejecutar nada. Vale la pena correrlo después de actualizar el CLI: **tres bugs
reales llegaron a producción por nombres de comando asumidos**, y dos se
descubrieron con el disco ya borrado.

---

## 5. El límite de 5

El tier gratuito permite 5 snapshots. `crear-snapshot.sh` **bloquea la creación
del sexto** en vez de intentarlo: no está verificado si Oracle lo rechaza o
simplemente lo cobra, y ante la duda es preferible fallar.

Para hacer sitio, borra el más viejo que ya no sirva:

```bash
# 1. Ver cuáles hay
.github/scripts/crear-snapshot.sh --contar

# 2. Obtener el OCID del que vas a borrar
TEN=$(awk -F= '/^tenancy/{print $2; exit}' ~/.oci/config | tr -d ' ')
oci bv boot-volume-backup list --compartment-id "$TEN" --all \
  --query "data[?\"display-name\"=='NOMBRE-EXACTO'].id" --raw-output

# 3. Borrarlo
oci bv boot-volume-backup delete --boot-volume-backup-id <ocid> --force
```

Borrar un backup **no afecta** al VPS ni a los volúmenes creados a partir de él.

---

## 6. Si el script falla

### Crear un snapshot a mano

Si los scripts no funcionan y necesitas el snapshot igual:

```bash
TEN=$(awk -F= '/^tenancy/{print $2; exit}' ~/.oci/config | tr -d ' ')

# Boot volume actualmente adjunto a beetle-vps
BV=$(oci compute boot-volume-attachment list \
  --compartment-id "$TEN" \
  --availability-domain "ODnr:SA-BOGOTA-1-AD-1" \
  --query 'data[?"lifecycle-state"==`ATTACHED`]."boot-volume-id" | [0]' \
  --raw-output)

# Crear el backup y esperar a que esté listo
oci bv boot-volume-backup create \
  --boot-volume-id "$BV" \
  --display-name "beetle-manual-$(date -u +%Y-%m-%d-%H%M)" \
  --type FULL \
  --wait-for-state AVAILABLE --max-wait-seconds 1800
```

### Diagnóstico rápido

| Mensaje | Qué pasa |
|---|---|
| `el OCI CLI no esta instalado` | Estás en el VPS, o falta `brew install oci-cli` |
| `hay OCI CLI pero no encuentro las credenciales` | Falta `oci setup config` |
| `NotAuthenticated` | La API key caducó o se revocó; regenerar en la consola |
| `BLOQUEADO: ya hay 5 snapshots` | Borrar uno antes (sección 5) |
| El comando se queda colgado | Normal: crear un snapshot tarda 1–3 min |

---

## 7. Estado actual

| Snapshot | Creado | Para qué |
|---|---|---|
| `beetle-vps-2026-08-19-1641` | 2026-08-19 | Base con 2FA de SSH y puerto 80 configurados |
| `beetle-mauricio-2026-09-02-0051` | 2026-09-02 | Pedido por Mauricio |

2 de 5 usados.
