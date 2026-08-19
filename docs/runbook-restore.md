# Runbook — restaurar `beetle-vps` desde snapshot

Cómo devolver el VPS a un estado anterior, quién puede hacerlo y qué se rompe en
el camino. **Procedimiento verificado end-to-end el 2026-08-18.**

---

## 1. El método: terminar y relanzar

En OCI, un boot volume creado desde un backup **no se puede adjuntar a una
instancia existente**. La API lo rechaza así:

```
Boot volume ... cannot be attached to instance ...
It can only be attached to its parent instance.
```

Solo sirve para **lanzar una instancia nueva**. Un "swap de boot volume in-place"
—apagar la instancia y cambiarle el disco— **es imposible**. Si a alguien se le
ocurre, ya se probó: falla después de haber borrado el disco viejo.

Por eso restaurar significa **terminar la instancia y lanzar otra**:

```
1. verificar que el backup este AVAILABLE   ← nunca se salta
2. terminar la instancia (--preserve-boot-volume false)
3. crear boot volume desde el backup
4. lanzar instancia nueva desde ese boot volume
5. reasignar la IP reservada BEETLE-IP
```

El paso 2 borra el disco viejo **antes** de crear el nuevo, a propósito: ocupa
150 GB de los 200 GB gratuitos y sin liberarlos no cabe el reemplazo. Por eso el
paso 1 no es opcional — el backup es la única red de seguridad durante esa
ventana, y los backups no se tocan en ningún momento del procedimiento.

Duración medida en dos restauraciones reales: **entre 2 y 13 minutos**. La
variable es lo que tarde OCI en crear el boot volume desde el backup.

## 2. Qué cambia y qué no

| | |
|---|---|
| IP pública `157.137.210.21` | **No cambia.** `BEETLE-IP` es reservada y se reasigna en el paso 5 |
| IP privada | **Cambia.** No es fija (pasó de `10.0.0.126` a `10.0.0.85`) |
| OCID de la instancia | **Cambia.** Por eso el script busca la instancia por nombre, nunca por OCID |
| Host key de SSH | **Cambia.** Ver abajo |
| Identidad de Tailscale | **Se conserva** — vive en el disco restaurado |
| Contenido del disco | Vuelve exactamente al estado del snapshot |
| Reglas de `ufw`, `fail2ban`, mirror de `apt` | **Se conservan** — viven en el disco |

### El host key va a cambiar

Al reconstruirse la máquina, SSH aborta con `REMOTE HOST IDENTIFICATION HAS
CHANGED` y un aviso de man-in-the-middle. **Es esperado después de un restore**,
pero solo entonces. Cada miembro del equipo tiene que correr, en su máquina:

```bash
ssh-keygen -R 157.137.210.21
ssh-keygen -R 100.112.242.120
```

Si ves esa advertencia **sin** que nadie haya restaurado, no la ignores.

## 3. Cómo restaurar

### Opción A — el botón (no requiere credenciales de Oracle)

En GitHub: **Actions → "Restaurar beetle-vps desde snapshot" → Run workflow**.

- Sin argumentos, solo lista los snapshots. Es seguro.
- Para restaurar hacen falta **dos llaves**: el nombre exacto del backup y
  escribir `RESTAURAR` en el campo de confirmación.

Cada ejecución queda en el historial de Actions: quién, cuándo y desde qué
backup. Es la misma trazabilidad de las tareas #201 y #213, aplicada a la
infraestructura.

### Opción B — el script

```bash
.github/scripts/restaurar-snapshot.sh --verificar   # valida el OCI CLI
.github/scripts/restaurar-snapshot.sh --listar
.github/scripts/restaurar-snapshot.sh beetle-base-2026-08-18
```

**Corre `--verificar` primero.** Comprueba que cada subcomando y flag exista en
el OCI CLI instalado. No es paranoia: tres bugs reales llegaron a producción por
nombres asumidos —`delete` en vez de `detach`,
`--source-boot-volume-backup-id` en vez de `--boot-volume-backup-id`, y
`--wait-for-state TERMINATED` en `terminate`, que espera estados de work
request. Los dos primeros se descubrieron con el disco ya borrado.

## 4. Quién puede restaurar

| Quién | Cómo | Puede borrar backups |
|---|---|---|
| Brian | OCI CLI como admin | Sí |
| Mauricio | El botón de GitHub Actions | **No** |

El workflow usa el usuario de servicio `beetle-restore-bot`, del grupo
`beetle-restore`, cuya política concede `read` sobre `boot-volume-backups` —
no `manage`. **Quien restaura no puede destruir un punto de restauración.**

Nota de OCI para quien edite políticas: `boot-volume-attachments` **no es un
resource-type válido** y falla con un `No permissions found` que no dice cuál
statement está mal.

## 5. Acceso al VPS: no hay una sola puerta

El security list de la subred tiene:

- UDP/41641 desde `0.0.0.0/0` — Tailscale, la vía diaria
- ICMP — path MTU discovery
- **TCP/22 desde `0.0.0.0/0`** — break-glass, solo-llave + fail2ban
- **TCP/80 desde `0.0.0.0/0`** — Nginx para demos y pruebas externas

Antes del 2026-08-18 no existía **ninguna** regla TCP: Tailscale era la única
entrada, y si el nodo no volvía tras un restore, la única salida era la consola
serial de Oracle.

**El orden es Tailscale primero, siempre.** El SSH público es solo para cuando
el tailnet no responde. Se abrió a `0.0.0.0/0` porque anclarlo a IPs fijas era
inviable con el equipo cambiando de red; la seguridad real son la llave y
fail2ban, no el filtro de IP.

El key expiry del nodo `beetle-vps` está desactivado (verificado: `KeyExpiry`
ausente en `tailscale status --json`). Gracias a eso, en la prueba real Tailscale
reconectó solo tras la reconstrucción, sin `--force-reauth`.

## 6. Política de snapshots

Solo caben **5 backups** (`free-backup-count = 5`). No es tan restrictivo:

- Las 42 corridas de la Fase 8 (#205) **restauran todas desde el mismo snapshot
  base**. No hace falta uno por corrida.
- Reparto sugerido: 1 base limpio + 1 por hito (fin de Fase 4, fin de Fase 7) +
  2 libres.

Crear uno nuevo:

```bash
.github/scripts/crear-snapshot.sh <motivo>
```

Ese script **bloquea la creación del sexto**. No está verificado si Oracle lo
rechaza o lo cobra, así que ante la duda falla en vez de arriesgar un cargo.
Para ver cuántos hay: `crear-snapshot.sh --contar`.

**El OCI CLI no está en el VPS**, así que los snapshots no se listan desde dentro
de la máquina: o desde una máquina con credenciales, o con el workflow de Actions.

Un snapshot tomado con el VPS encendido es *crash-consistent*: equivale a un
corte de luz. Para un VPS de desarrollo alcanza.

**Antes de cualquier prueba destructiva, toma un snapshot fresco y restaura desde
ese**, no desde el base. Así nadie pierde el trabajo del día.

## 7. Cuotas reales

Verificadas con `oci limits`, no estimadas:

| Recurso | Cuota | En uso | Libre |
|---|---|---|---|
| OCPUs ARM (A1) | 2 | 2 (`beetle-vps`) | 0 |
| Almacenamiento gratis | 200 GB | 150 GB | 50 GB |
| Backups gratis | 5 | 2 | 3 |

Una instancia **apagada sigue consumiendo su cuota de OCPUs**. Por eso el
procedimiento termina la instancia en vez de dejarla detenida: sin liberar esas
2 OCPUs no se puede lanzar la nueva.

`VM.Standard.E2.1.Micro` no existe en `sa-bogota-1`, así que no hay forma de
levantar una VM auxiliar, ni siquiera temporal.
