# Progreso del MVP — traspaso

**Rama:** `mvp/integracion-modo-1` · **Base:** `gate-d/modo-1` (@MauItu + corrección de Gate C)
**Corte:** 2026-09-01 · **Suite:** 227 tests en verde

> **Actualización 2026-09-01:** Gates 1-3 del plan de finalización completos
> (config, detector, monitor, wiring real de main.py, ventana +1 minuto,
> contrato LLM corregido, identificadores en inglés) y validados en el VPS
> real (instalación cronometrada, 4 incidentes reales, llamada real a
> Cloudflare). Gate 4 (Modo 2) tiene el código completo y probado en local;
> la validación en VPS de su criterio de avance ("<2 min sin intervención
> humana") queda pendiente por instrucción explícita de no provocar más
> incidentes ni tocar el VPS hasta que haga falta de verdad. Ver §8.

Este documento existe para que alguien retome sin leer el historial completo.
Dice qué está hecho, qué está **verificado contra el VPS real** y qué sigue
pendiente a propósito. Donde no hay medición, lo dice; no hay resultados
inventados (plan-mvp.md §4, regla 10).

> **Corrección del 2026-08-31:** la versión anterior de este documento (corte
> 2026-08-26) afirmaba Gate B "corriendo" con fin previsto y Gate D "cerrado".
> Ambas afirmaciones no resisten la auditoría — ver
> [`plan-finalizacion-mvp.md`](plan-finalizacion-mvp.md), que es ahora la fuente
> normativa vigente sobre el estado real del proyecto. Este archivo se corrige
> para dejar de repetirlas.

---

## 1. Estado por gate

| Gate | Estado | Verificación |
|---|---|---|
| A — Base | Hecho por @MauItu | 105 tests |
| B — Detector | **Detenida y archivada** | Corrida inválida (2026-08-26 a 2026-09-01, `INVALIDA_SIN_DETECTOR`, §7.1) detenida por protocolo. El Detector real ahora sí está cableado (Gate 2) y corre en el VPS desde 2026-09-01 |
| C — Evidencia y privacidad | Cerrado | Corpus real del VPS, 0 fugas |
| D — Modo 1 (hito alfa) | **Cerrado y validado en VPS real** | `main.py` cablea el pipeline completo; instalación cronometrada, 4 incidentes reales detectados/diagnosticados/resueltos, llamada real a Cloudflare confirmada (§7.2) |
| E — Servicio e instalación | Cerrado | Unidades validadas, `systemd-analyze verify` limpio, instalación 14.3s, reinstalación idempotente confirmada |
| F — Modo 2 determinista | **Código completo, validación en VPS pendiente** | `clasificador.py`, `remediador.py`, 4 scripts + `comun.sh`, sudoers exacto, anexado al informe — todo con tests locales en verde. Falta provocar los 4 escenarios básicos en el VPS y medir el "<2 min" del criterio de avance (§8) |
| G–I | Sin empezar | — |

---

## 2. Gate C — una fuga real, encontrada y corregida

La primera corrida **pasó y no significaba nada**: con el VPS ocioso el corpus
traía 1.731 caracteres y casi ninguna sonda encontraba datos sensibles ni
siquiera antes de sanitizar. Sanitizar la nada siempre pasa.

Sembrando el journal con lo que loguean de verdad PostgreSQL, una app y Nginx,
apareció el fallo:

```
postgresql://app:cambia_esto@10.0.0.85:5432/cargatest
   -> la IP se redactaba, la contraseña salía en claro
```

**No era hipotético:** `cambia_esto` es la contraseña del `app.py` que corre en
ese VPS, así que llega al journal en cualquier error de conexión.

Corregido, más las cabeceras `Basic` (que llevan usuario:contraseña en base64 y
pasaban intactas mientras `Bearer` sí se cubría). Se conservan esquema y usuario
porque son diagnósticos; solo se enmascara la contraseña.

**Resultado tras el arreglo:** 6 sondas con datos sensibles en el texto crudo,
las 6 redactadas.

Dos cosas encontradas que **no** se corrigieron porque ya estaban documentadas
como limitaciones aceptadas en `sanitizador_limitaciones.md`: la colisión
MAC/IPv6 y las credenciales en formato `clave: valor`.

---

## 3. Gate D — qué hace y cómo se verificó

El corte vertical del Modo 1: de incidente confirmado a informe en disco.

```
incidente -> evidencia cruda -> se guarda local -> se sanitiza
          -> se diagnostica -> informe .md
```

### Decisiones que conviene no deshacer

**`SanitizedEvidence` es un tipo, no un `str`.** `llm.py` acepta únicamente ese
contrato, y solo `sanitizador.sanitize_evidence()` lo construye. La frontera de
privacidad deja de ser una convención y pasa a ser estructural: no hay forma de
pasar evidencia cruda por descuido.

**La evidencia cruda se guarda ANTES de llamar al modelo.** Si el proveedor
cuelga o el proceso muere, la evidencia de ese incidente ya está en disco.

**El fallback dice que no analizó nada.** Cuando se agotan los reintentos se
escribe un informe con los hechos disponibles y la frase explícita "no contiene
análisis de causa raíz". Preferible a no entregar nada, y sin fingir un
diagnóstico que nadie hizo.

**Informe y evidencia rotan como unidad.** Evidencia sin informe deja datos
crudos en disco sin nada que explique por qué están ahí; informe sin evidencia
es inauditable.

**Un `200` con cuerpo vacío o roto se trata como un 500.** Es igual de
inservible, así que entra al backoff en vez de devolverse como éxito.

### Verificación en el VPS real

Contra una unidad realmente caída, no en tests:

```
archivos: 20260826_064941_service_failed.md
          20260826_064941_service_failed_evidencia.txt
permisos: evidencia 600 · informe 644
evidencia cruda 2.710 chars -> enviado al proveedor 2.678

OK  informe escrito en disco
OK  la evidencia cruda menciona el servicio caído
OK  ninguna IP real viajó (5 en crudo, 0 fugadas)
```

### Lo que NO está probado

**Nunca se llamó al proveedor de verdad.** No hay credencial disponible, así que
todo D1 se probó con dobles. Antes de confiar en el Modo 1 hay que hacer una
llamada real a Cloudflare y comprobar que el formato de respuesta coincide con
lo que espera `_extraer_contenido`.

**El ejecutable real (`doctorjk/main.py`) nunca corrió este flujo.** La
verificación de arriba se hizo invocando el pipeline directamente, no a través
del proceso que instala systemd. Ver defecto 1 en `plan-finalizacion-mvp.md`
§3.1 y Gate 2 de ese mismo plan.

---

## 4. Gate E — parcial

**Hecho y validado:** `doctorjk.service` y `doctorjk-trigger.service` pasan
`systemd-analyze verify`. Unidades separadas a propósito: si el trigger muere,
el polling sigue vigilando; un solo proceso convertiría cualquier fallo en
ceguera total.

**Hecho, parcialmente probado:** `install.sh` y `desinstalar.sh`. Verificado que
el instalador rechaza ejecutarse sin root y fuera del repositorio, antes de tocar
nada.

**PENDIENTE — no se hizo y no se debe dar por hecho:** la instalación cronometrada
en un VPS restaurado (criterio de salida de Gate E: menos de 15 minutos). No se
ejecutó porque el instalador arranca los servicios y habría pisado el FIFO de la
corrida de Gate B, que llevaba 10 horas. **Hay que correrla cuando Gate B
termine**, sobre un VPS restaurado desde snapshot.

También queda sin probar la idempotencia real (instalar dos veces), por el mismo
motivo.

---

## 5. Inconsistencia corregida en `.env.example`

Declaraba `DOCTORJK_LLM_BASE_URL` y `DOCTORJK_LLM_MODEL` como variables de
entorno, pero según §3.3 del plan esas dos van en `config.toml` — no son
secretos y el cliente necesita editarlas. Quien las hubiera configurado en el
`.env` las habría visto ignoradas en silencio.

Ahora `.env` contiene únicamente `DOCTORJK_LLM_API_KEY`.

---

## 6. Qué sigue

El orden vigente es el de la sección 9 de `plan-finalizacion-mvp.md`, no el que
describía este documento antes de la corrección. Resumen:

1. Resolver la visibilidad pública del repositorio (requiere autorización humana).
2. Detener y archivar la corrida inválida de Gate B como `INVALIDA_SIN_DETECTOR`
   — no calcular falsos positivos con ella, no contar sus 17.040 muestras como
   evaluación del Detector.
3. Trabajar sobre `mvp/integracion-modo-1` (ya creada desde `gate-d/modo-1`).
4. Escribir el test que expone que `main()` no cablea el pipeline (Gate 1.1).
5. Corregir normalización de servicios/puertos sanos y persistencia por tipo
   de señal (Gate 1.2–1.3).
6. Cablear el Modo 1 real desde configuración (Gate 2.1).
7. Completar la ventana +1 minuto y el contrato real del proveedor (Gate 2.2–2.3).
8. Sanear identificadores al inglés y manejo de excepciones (Gate 1.4).
9. Validar instalación, llamada real a Cloudflare, los cuatro incidentes básicos
   y una corrida de 24 h con el Detector realmente cableado (Gate 3).
10. Recién entonces, el primer PR a `main` y el Modo 2 (#199).

Recordar que **#203 dice provocar la caída con `systemctl stop postgresql`, y
eso no genera ningún evento** — parar un servicio limpiamente no es un fallo.
Hay que matar el proceso. Está documentado en el comentario de #172 y en Gate
3.2 del plan de finalización.

---

## 7. Infraestructura del VPS

### 7.1 Gate B — detenida y archivada como `INVALIDA_SIN_DETECTOR` (2026-09-01)

Ejecutada siguiendo el protocolo de Gate 0.2 del plan de finalización, por
Tailscale, como usuario `beetle` (con sudo):

| Campo | Valor |
|---|---|
| Inicio | 2026-08-26T04:41:03Z (PID 80708, monitor) / 04:41:07Z (PID 80712, trigger) |
| Fin | 2026-09-01T05:12Z |
| Duración real | ~6 días (muy por encima de las 24 h previstas del gate) |
| Muestras | 17.325 líneas en `/opt/gate-b/gate-b.log` (2,2 MB) |
| Transiciones/incidentes | **0** — `grep -ci 'incident\|transition'` no encontró ninguna |
| Código usado | copia de `gate-d/modo-1` al 2026-08-26, sin Detector cableado en `main.py` |
| Terminación | SIGTERM al trigger primero, luego al monitor; ambos confirmados terminados |

Como ya decía la auditoría: cada una de esas 17.325 líneas es
`muestra tomada: ...` del callback `log_snapshot` de Gate A, nunca se
instanció el Detector. **No cuenta como validación de #174–#178** ni sirve
para calcular falsos positivos. `/opt/gate-b` se conserva sin borrar hasta
que el resumen de arriba quede versionado (ya lo está, en este commit); la
limpieza del directorio queda pendiente de aprobación explícita.

### 7.2 Gate 3.2 — Modo 1 instalado y validado en el VPS real (2026-09-01)

Código desplegado por Tailscale (tar, sin usar el remoto de GitHub) a
`~/mvp-integracion-modo-1` en `beetle-vps`, instalado con
`instalador/install.sh` como servicio real.

| Criterio | Resultado |
|---|---|
| Instalación limpia cronometrada | **14.3 s** (`/opt/doctorjk` recién borrado antes) |
| Reinstalación idempotente | Confirmada: mismo hash de `config.toml` y `.env` antes/después, ambos servicios siguieron activos |
| `systemd-analyze verify` | Limpio para las dos unidades propias (los únicos warnings son de `unified-monitoring-agent`, preexistente de Oracle) |
| Consumo en reposo | 0,6 % CPU (agente) / 0,0 % (trigger), muy por debajo del 1 % |
| Llamada real a Cloudflare | Confirmada varias veces, modelo `@cf/openai/gpt-oss-120b`, diagnósticos completos en español sin datos inventados |

**Cuatro incidentes provocados de forma controlada y con restauración:**

| Incidente | Cómo se provocó | Detectado | Informe | Recuperación |
|---|---|---:|---:|---:|
| `service_failed` (postgresql) | `kill -9` al proceso principal (no `systemctl stop`, que no genera evento) | Sí, 2 ciclos | Sí (cayó a fallback: ver abajo) | Sí, 2 ciclos sanos |
| `port_down` (:5432) | Consecuencia del mismo kill | Sí, 2 ciclos | Sí, diagnóstico real | Sí |
| `disk_full` (/) | `fallocate -l 128G`, 92% de uso; borrado ~90s después | Sí, 2 ciclos | Sí, diagnóstico real | Sí |
| `port_occupied` (:80) | nginx detenido, un `python3 -m http.server 80` tomó el puerto | Sí, 2 ciclos | Sí, diagnóstico real | Sí |

`memory_low` **no se provocó**: el VPS tiene 11 GiB sin swap y cruzar el
umbral (512 MB disponibles) exige ocupar ~10,5 GiB en una máquina
compartida sin margen de recuperación si algo sale mal. Se deja para Gate 5,
con una herramienta acotada por cgroup (`systemd-run -p MemoryMax=...`) y
ventana coordinada, no como prueba improvisada de Gate 3.

**Defecto real encontrado y corregido en el camino:** el payload a Cloudflare
no fijaba `max_tokens`. gpt-oss-120b es un modelo de razonamiento: sin ese
límite, el proveedor usa un default de 256, el modelo agota ese presupuesto
en razonamiento oculto y nunca llega a `content` (`finish_reason="length"`,
`content=null`). Todo incidente real habría caído al fallback en silencio.
Corregido con `MAX_COMPLETION_TOKENS=4096` (`doctorjk/llm.py`). Un segundo
ajuste real: `llm_timeout_s` subió de 30 a 60 s porque con evidencia de
tamaño real el modelo ocasionalmente tardó más de 30 s.

**Estado dejado en el VPS:** los 4 servicios reales (nginx, postgresql,
appcarga, cron) y `doctorjk`/`doctorjk-trigger` activos y sanos; disco al 3%;
sin artefactos de prueba. `doctorjk.service` sigue corriendo — es, a partir
de este momento, el inicio de la corrida de 24 h que pide el punto 12 de
Gate 3.2. Falta contarla cuando pasen las 24 h (contar transiciones reales
en el journal, no líneas de muestreo — el error de Gate B no se repite).

### 7.3 Snapshot y housekeeping

- Snapshot vigente: `beetle-vps-2026-08-19-1641`, 1 de 5 del cupo gratuito.

---

## 8. Gate 4 — Modo 2 determinista (2026-09-01)

**Código completo y probado en local (227 tests en verde), nada corrido en
VPS todavía** — por instrucción explícita de no provocar más incidentes ni
tocar el VPS salvo necesidad real.

| Pieza | Estado |
|---|---|
| `doctorjk/clasificador.py` | Mapeo `SignalType` → script (tarea #200), `PORT_DOWN` sin script a propósito |
| `doctorjk/remediador.py` | Ejecuta con opt-in (`modo_remediacion="scripts"` + `auto_fix`), sanitiza stdout/stderr, nunca lanza |
| `scripts-fix/comun.sh` + 4 `fix_*.sh` | `bash -n` y `shellcheck -x` limpios (verificado en el VPS por no tener shellcheck local) |
| `instalador/install.sh` | Copia `scripts-fix/`, genera `/etc/sudoers.d/doctorjk` con 4 rutas exactas (`visudo -cf` antes de instalar), nunca systemctl/shell suelto |
| `doctorjk/informe.py` | `append_remediation()` anexa el resultado al mismo informe, atómico |
| `doctorjk/main.py` | Tras cada diagnóstico, si `scripts_dir` está configurado, llama a `remediate()` con `sudo -n` como prefijo real |

**Decisiones tomadas sin fijación previa en el plan, documentadas para revisión:**

- `unidad_memoria_aprobada` (config.toml, nueva clave): sin ella, `fix_memoria.sh`
  escala en vez de actuar — el plan exigía "unidad aprobada" pero no decía
  cómo se configura.
- `fix_disco.sh` **no toca `/tmp`**: en un servidor compartido no hay forma
  seria de distinguir un archivo temporal huérfano de uno en uso ajeno sin
  una política más fina que el producto no ha definido. Solo vacía journal
  (100M) y logs rotados de más de 3 días bajo `/var/log`.
- Los scripts corren como root vía `sudo -n <ruta-exacta>`, no
  `systemctl`/`find` sueltos dentro de un script sin privilegios: es lo que
  permite que `doctorjk` (usuario sin privilegios) ejecute exactamente esos
  4 archivos ya vetted, nada más.

**Pendiente, no hecho a propósito:**

- Provocar los 4 escenarios básicos con `auto_fix=true` en el VPS y medir
  el criterio de avance real de la tarea #199 ("disco lleno se resuelve en
  <2 minutos sin intervención humana").
- `fix_memoria.sh` no tiene una unidad aprobada configurada todavía en el
  VPS (`unidad_memoria_aprobada = ""`): antes de probarlo hay que decidir
  qué unidad real del VPS es segura de reiniciar para ese fin.

---

## 9. Gate 4.4 — inventario del VPS y protocolo v2 (2026-09-01)

**Local aprobado de forma independiente:** 259 tests, `bash -n`, `compileall`
y `git diff --check` en verde. Todo lo de esta sección sigue sin ejecutarse
en el VPS salvo el inventario de solo lectura (§9.1) y la investigación de
los reinicios (§9.1bis). **El protocolo v2 (§9.2) corrige el borrador
rechazado** (mataba PostgreSQL/Nginx reales, cruzaba disco sin cálculo
previo, no resolvía la contradicción "sin Cloudflare" con incidentes que
pasan por el LLM, no tenía rollback ni medición de tiempo definidos, y no
tenía un orden de ejecución seguro). Nada de lo que sigue se ejecutó todavía
— es la propuesta a revisar antes de tocar el VPS.

### 9.1 Inventario

| Área | Estado |
|---|---|
| Conectividad | OK, `beetle@beetle-vps` por Tailscale |
| Servicios reales | `nginx`, `postgresql@16-main`, `appcarga`, `cron` — los 4 activos |
| Carga | `0.00 0.00 0.00`, 2 vCPU |
| Memoria | 11 GiB total, ~8.9 GiB libres, sin swap; ningún proceso individual pasa de 45 MB RSS |
| Disco | 145G, 4.2G usados (3%), 141G libres |
| `doctorjk.service` / `doctorjk-trigger.service` | Ambos activos. **`NoNewPrivileges=yes`** — es el código de Gate 3.2, previo a las correcciones de Gate 4; no se ha vuelto a instalar |
| `/opt/doctorjk` | Existe, sin `scripts-fix/`: Modo 2 nunca se desplegó |
| `/etc/sudoers.d/doctorjk` | No existe |
| `config.toml` | `modo_remediacion="diagnostico"`, `auto_fix=false`, `dry_run=true`, `unidad_memoria_aprobada=""` — Modo 2 apagado, tal como se dejó |
| `.env` | Existe, 600, con contenido (no se leyó el valor) |
| Informes | Los 4 de Gate 3.2 siguen ahí (`service_failed`×2, `port_down`, `disk_full`, `port_occupied`) |
| Corrida de 24h (Gate 3.2 §7.2) | **No fue continua.** `doctorjk.service` recibió SIGTERM y se reinició dos veces a las 06:32:50 y 06:33:06 UTC. Causa determinada, ver §9.1bis. |

### 9.1bis Investigación de los reinicios de 06:32:50 / 06:33:06 UTC (solo lectura, causa confirmada)

**Conclusión: parches automáticos de seguridad (`unattended-upgrades` +
`needrestart`), no un bug de Doctor J/K ni una acción manual.** Evidencia,
del journal completo de la ventana 06:30–06:35 UTC:

- `apt-daily-upgrade.service` arrancó a las 06:31:49 y corrió
  `unattended-upgrade` (PID 236087) de forma continua hasta las 06:33:32
  (`Consumed 1min 8.458s CPU time`) — es el único proceso activo en toda la
  ventana además del ruido habitual de escaneo SSH de internet y el propio
  `unified-monitoring-agent` de Oracle (`snap_daemon`, ajeno).
- Se ven **tres cascadas de reinicio**, todas dentro de esa ventana de
  `apt-daily-upgrade`, nunca fuera de ella:
  1. **06:32:23** — `systemd[1]: Reexecuting` (típico de una actualización
     del paquete `systemd` en sí) + cascada de demonios de bajo nivel
     (`iscsid`, `packagekit`, `ModemManager`, `polkit`, `rsyslog`,
     `systemd-journald`, `systemd-networkd`/`resolved`/`timesyncd`,
     `udisks2`) y `doctorjk-trigger.service` (no `doctorjk.service`).
  2. **06:32:50** — cascada mucho más amplia: `appcarga`, `ModemManager`,
     `doctorjk-trigger`, `fail2ban`, `nginx`, `packagekit`,
     `postgresql@16-main`, `rsyslog`, `ssh`, `udisks2` — y
     `doctorjk.service` (`doctorjk[234039]: SIGTERM recibido, cerrando de
     forma ordenada`, cierre limpio, no un crash).
  3. **06:33:06** — segunda pasada más chica: `appcarga`,
     `doctorjk-trigger`, `fail2ban`, `packagekit` y de nuevo
     `doctorjk.service` (`doctorjk[238379]: SIGTERM recibido...`, también
     limpio).
- Esta lista de servicios (justo los que corren binarios propios contra
  bibliotecas compartidas del sistema, no los servicios de systemd puros)
  es exactamente la firma de `needrestart`: reinicia todo lo que enlaza
  contra una biblioteca que acaba de actualizarse. **Ya se había observado
  este mismo mecanismo en esta sesión**: instalar `python3.12-venv` con
  `apt-get install` disparó `needrestart` y reinició `appcarga.service` y
  `fail2ban.service` como efecto secundario, sin relación con Doctor J/K.
- No hay ningún `sudo` de un humano ni ningún cambio de `main` (`6166bf9`
  seguía siendo el desplegado) en la ventana — el único `sudo` visible es
  el `unified-monitoring-agent` de Oracle consultando su propio estado.
- **Dato positivo, no solo diagnóstico:** las dos veces, `doctorjk` logueó
  su propio cierre ordenado (manejo de SIGTERM correcto) antes de que
  systemd lo reiniciara — no hubo pérdida de estado no controlada ni
  comportamiento errático, solo el reinicio en sí.

**Riesgo a controlar para el protocolo v2, no para hoy:** `apt-daily-upgrade`
corre en una ventana calendarizada por su propio timer y puede volver a
reiniciar `doctorjk.service` a mitad de un escenario real. El detector es un
state machine persistente (#174), así que un reinicio a mitad de un conteo
de persistencia no debería perder el progreso — pero por las dudas, el Paso
0 del protocolo v2 chequea `systemctl list-timers apt-daily-upgrade.timer`
antes de arrancar la fase de mutación real y no continúa si el próximo
disparo cae dentro de la ventana estimada del protocolo.

### 9.2 Protocolo v2 (nada ejecutado; secuencial, reversible, con cleanup y salud tras cada escenario)

**Reglas duras de todo el protocolo:**

- Si cualquier paso de cleanup falla, o el chequeo de salud posterior no
  calza con la línea base de §9.1, **se para ahí mismo** — no se continúa
  con el siguiente escenario.
- Cada edición de `config.toml` exige `sudo systemctl restart
  doctorjk.service` para tomar efecto (se carga una sola vez al arrancar).
  Para no multiplicar reinicios, todas las claves temporales de una fase se
  editan juntas y se reinicia una sola vez por fase.
- Nunca se toca `nginx`, `postgresql@16-main` ni `appcarga` reales — todos
  los incidentes se provocan con unidades `systemd-run` transitorias
  propias, nunca persistidas a disco (si algo queda mal, un reboot del VPS
  las borra igual, aunque no debería hacer falta llegar a eso).
- Ningún incidente real (Fase C/D) corre sin que antes `curl` confirme que
  el stub de LLM local responde (§9.2.2) — así "sin Cloudflare" y "probar
  el pipeline completo" dejan de ser incompatibles.
- **Por qué sigue sin hacer falta un snapshot nuevo:** cada mutación es
  reversible por diseño (unidades transitorias que nunca tocan disco,
  backup único de `config.toml`/`.env` antes de tocar nada, reinstalación
  idempotente ya probada en local). Se revisita esta decisión si algún paso
  revela lo contrario.

#### 9.2.0 Paso 0 — Redesplegar el código de Gate 4 (mutación necesaria, reversible)

**Corrección del hallazgo 6:** el borrador anterior copiaba el árbol entero
por `tar`. Eso habría llevado `docs/plan-finalizacion-mvp.md` y
`graphify-out/` (ambos sin trackear, ver `git status`) al VPS sin querer.
`git archive HEAD` transfiere **solo lo comiteado en el commit actual de
`AIprototipo`** — nunca `.git/`, `.env` ni archivos sin trackear.

```bash
# Chequeo previo: ¿va a disparar apt-daily-upgrade a mitad del protocolo?
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net \
  "systemctl list-timers apt-daily-upgrade.timer --no-pager"
# Si el próximo disparo cae dentro de la próxima hora, esperar a que termine
# esa corrida antes de seguir (no es bloqueante si no calza, solo se anota).

git archive HEAD | tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net \
  "rm -rf /tmp/doctorjk-deploy && mkdir -p /tmp/doctorjk-deploy && tar -x -C /tmp/doctorjk-deploy"

# Backup único de config/.env -- sirve tanto para el rollback de este paso
# como para la restauración final de la Fase E.
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  sudo cp /etc/doctorjk/config.toml /etc/doctorjk/config.toml.bak-gate44
  sudo cp /etc/doctorjk/.env /etc/doctorjk/.env.bak-gate44
"

tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "sudo /tmp/doctorjk-deploy/instalador/install.sh"
```

Verificar: `systemd-analyze verify`, `sudo -n -l` para los 4 scripts,
`grep NoNewPrivileges` sobre la unidad instalada (los mismos chequeos que ya
tiene `install.sh`), ambas unidades (`doctorjk`, `doctorjk-trigger`)
activas.

**Rollback si algo de esto falla (corrección del hallazgo 6):** nunca
`desinstalar.sh` — dejaría el agente completamente fuera. El VPS ya tiene
en `/home/beetle/Beetle` el checkout de `main` en `6166bf9` (Gate 3.2), que
este paso nunca toca porque despliega a `/tmp/doctorjk-deploy`, un
directorio aparte. Restaurar es re-correr el instalador viejo desde ese
checkout intacto:

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "sudo /home/beetle/Beetle/instalador/install.sh"
```

`install.sh` es idempotente y preserva `config.toml`/`.env` existentes, así
que esto vuelve al estado exacto de Gate 3.2 sin perder configuración.

#### 9.2.1 Fase A — preparar unidades sintéticas y config temporal (todavía sin provocar nada)

**Corrección del hallazgo 2:** ningún paso de este protocolo detiene Nginx
ni mata PostgreSQL reales. Los 4 tipos de incidente se provocan con
unidades `systemd-run` transitorias propias del protocolo, nunca cargadas
desde disco:

| Unidad | Rol | Notas |
|---|---|---|
| `doctorjk-test-svc.service` | `service_failed` | falla la primera vez que arranca, queda "active" (sleep) la segunda — así el reinicio de `fix_servicio.sh` sí prueba algo |
| `doctorjk-test-owner.service` | dueño esperado del puerto 18080 | se arranca una vez y se detiene, para que quede "cargada" y `systemctl restart` (el que corre `fix_puerto.sh`) la reconozca |
| `doctorjk-test-occupier.service` | ocupante indebido del puerto 18080 | listening en 18080 mientras `doctorjk-test-owner` está detenida = `port_occupied` |
| `doctorjk-test-memhog.service` | consumidor de memoria acotado | `MemoryMax=1200M`, `MemorySwapMax=0`; asigna ~1000 MB una sola vez (marcador en `/run`), así un `restart` real libera la memoria en vez de reasignarla |
| `doctorjk-test-llmstub.service` | stub OpenAI-compatible en `127.0.0.1` | ver §9.2.2 |

Preparación (sin provocar nada todavía):

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  # doctorjk-test-owner: se registra la definición transitoria y se deja detenida.
  sudo systemd-run --unit=doctorjk-test-owner python3 -m http.server 18080 --bind 127.0.0.1
  sudo systemctl stop doctorjk-test-owner
"
```

**Cálculo del filler de disco ANTES de crearlo (corrección del hallazgo 3
-- nunca cruzar el 90% real, y nunca crear un archivo sin calcular su
tamaño primero):**

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  total_kb=\$(df --output=size -k / | tail -1)
  used_kb=\$(df --output=used -k / | tail -1)
  target_pct=5
  target_used_kb=\$(( total_kb * target_pct / 100 ))
  filler_kb=\$(( target_used_kb - used_kb + 51200 ))   # +50 MiB de margen para cruzar con claridad
  max_kb=\$(( 4 * 1024 * 1024 ))                        # tope duro de 4 GiB
  echo \"filler calculado: \$((filler_kb / 1024)) MiB (tope 4096 MiB)\"
  if (( filler_kb > max_kb )); then echo 'ABORTAR: filler superaría 4 GiB' >&2; exit 1; fi
  if (( filler_kb <= 0 )); then echo 'ABORTAR: ya estamos sobre el 5% sin filler' >&2; exit 1; fi
  echo \$filler_kb > /tmp/doctorjk-filler-kb
"
```

Con el disco real al 3% (§9.1), este cálculo da un filler de ~3 GiB para
cruzar un umbral temporal de 5% — cómodamente bajo el tope de 4 GiB y muy
lejos del 90% real.

**Stub de LLM (corrección del hallazgo 5):** ver §9.2.2 antes de arrancarlo.

**Config temporal, un solo pase de edición + un solo restart:**

Respaldo ya hecho en el Paso 0. Editar `/etc/doctorjk/config.toml`:

- `servicios_vigilados` += `"doctorjk-test-svc.service"`,
  `"doctorjk-test-occupier.service"` (sin esto, `fix_servicio.sh` y
  `fix_puerto.sh` escalan en vez de actuar sobre unidades que no reconocen).
- `puertos_vigilados` += `{ puerto = 18080, servicio =
  "doctorjk-test-owner.service" }`.
- `disco_pct` → `5` (original respaldado en el Paso 0).
- `memoria_disponible_mb` → `$(free -m | awk '/^Mem:/{print $7}') - 700`
  calculado en el momento (con ~8.9 GiB libres da un umbral ~8.2 GiB —
  cruzarlo exige que el memhog de 1000 MB acotado por cgroup se sume al uso
  real, no bajar la memoria disponible real del sistema).
- `unidad_memoria_aprobada` → `"doctorjk-test-memhog.service"`.
- `llm_url` → endpoint del stub (§9.2.2).
- **Corrección del hallazgo 7 (intervalos seguros para que el E2E quepa en
  minutos):** `intervalo_monitor_s` → `5`, `ciclos_persistencia` → `2`,
  `servicio_ciclos` → `2`, `puerto_timeout_s` → `10` (da `port_cycles = 2`
  con el nuevo intervalo). Esto baja la confirmación de un incidente a
  ~10 s en vez de los `30 s × 2` (60 s) de producción.

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "sudo systemctl restart doctorjk.service"
```

Verificar en journal que no hay errores de `ConfigError` tras el reinicio y
que ambas unidades siguen activas.

#### 9.2.2 Stub de LLM efímero (corrección del hallazgo 5)

El pipeline llama al LLM **antes** de remediar (`llm.py` → `informe.py` →
`remediador.py`), así que cualquier escenario que pase por el pipeline
completo (Fase B2 y Fases C/D) necesita un backend que responda, sin usar
Cloudflare. Un stub HTTP mínimo, atado solo a `127.0.0.1`, con el formato
exacto que espera `llm.py::_extract_content()`:

```python
#!/usr/bin/env python3
# Stub OpenAI-compatible efimero, solo para validar Modo 2 sin llamar a
# Cloudflare (Gate 4.4). Ignora el cuerpo del pedido y el header de
# autorizacion: no hace falta credencial real para responder.
import json
from http.server import BaseHTTPRequestHandler, HTTPServer

RESPUESTA = {
    "choices": [{"message": {"content": "Diagnostico simulado por el stub de validacion (Gate 4.4)."}}]
}

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        body = json.dumps(RESPUESTA).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    HTTPServer(("127.0.0.1", 8998), Handler).serve_forever()
```

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  ss -tln | grep -q ':8998 ' && { echo '8998 ya está en uso, elegir otro puerto' >&2; exit 1; }
  cat > /tmp/doctorjk-llmstub.py <<'PYEOF'
  <contenido de arriba>
PYEOF
  sudo systemd-run --unit=doctorjk-test-llmstub --collect \
    python3 /tmp/doctorjk-llmstub.py
  sleep 1
  curl -sf -X POST http://127.0.0.1:8998/v1/chat/completions -d '{}' | grep -q 'Diagnostico simulado' \
    || { echo 'el stub no responde con el formato esperado' >&2; exit 1; }
"
```

`llm_url` en config.toml queda en `http://127.0.0.1:8998/v1/chat/completions`
mientras dure la Fase A→D. Nunca se usa la API real de Cloudflare en este
protocolo.

#### 9.2.3 Fase B — smoke test (todo en `dry_run=true`, `auto_fix=false`; nada muta)

**B1 — un tipo por el pipeline completo, en dry-run.** Se usa
`service_failed` (el más simple de los cuatro):

1. Provocar: `sudo systemd-run --unit=doctorjk-test-svc --property=Restart=no /bin/bash -c 'test -e /run/doctorjk-test-svc.marker && exec sleep infinity || { touch /run/doctorjk-test-svc.marker; exit 1; }'`
2. Esperar la confirmación del detector (`journalctl -u doctorjk | grep -- '-> incident:'`).
3. Confirmar en el informe anexado: sección de remediación con
   `[DRY-RUN] Ningún comando fue ejecutado`.
4. Confirmar que NO se ejecutó el restart real: la unidad sigue en estado
   `failed` (no pasó a `active`/sleep).
5. Cleanup de este sub-paso: `sudo systemctl stop doctorjk-test-svc`,
   `sudo systemctl reset-failed doctorjk-test-svc`,
   `sudo rm -f /run/doctorjk-test-svc.marker` — vuelve a cero para la Fase C.

**B2 — los 4 scripts, llamados directo (sin pasar por el pipeline, sin
LLM), en dry-run.** Cada uno se provoca, se llama a mano, se confirma que
no muta nada, y se limpia antes de pasar al siguiente:

- `fix_servicio.sh`: repetir la provocación de B1 (falla una vez) →
  `sudo -n /opt/doctorjk/scripts-fix/fix_servicio.sh doctorjk-test-svc.service`
  → confirmar `[DRY-RUN]` y que sigue `failed` → mismo cleanup que B1.
- `fix_disco.sh`: `fallocate -l "$(cat /tmp/doctorjk-filler-kb)K"
  /var/log/doctorjk-test.log.1.gz && sudo touch -d '10 days ago'
  /var/log/doctorjk-test.log.1.gz` → `sudo -n
  /opt/doctorjk/scripts-fix/fix_disco.sh` → confirmar `[DRY-RUN]` y que el
  archivo sigue ahí → cleanup: `sudo rm -f /var/log/doctorjk-test.log.1.gz`.
- `fix_puerto.sh`: `sudo systemctl start doctorjk-test-occupier` (definida
  igual que `doctorjk-test-owner` en §9.2.1, con `--collect`) → `sudo -n
  /opt/doctorjk/scripts-fix/fix_puerto.sh 18080` → confirmar `[DRY-RUN]` y
  que el ocupante sigue escuchando (no `doctorjk-test-owner`) → cleanup:
  `sudo systemctl stop doctorjk-test-occupier`.
- `fix_memoria.sh`: `sudo systemd-run --unit=doctorjk-test-memhog
  --property=MemoryMax=1200M --property=MemorySwapMax=0 --collect
  python3 /tmp/doctorjk-deploy/memhog.py` (script de una sola asignación,
  ver más abajo) → `sudo -n /opt/doctorjk/scripts-fix/fix_memoria.sh` →
  confirmar `[DRY-RUN]` y que la memoria disponible sigue baja → cleanup:
  `sudo systemctl stop doctorjk-test-memhog`, `sudo rm -f
  /run/doctorjk-test-memhog.marker`.

`memhog.py` (transferido junto con el resto en el Paso 0, o creado igual
que el stub de LLM con un heredoc):

```python
#!/usr/bin/env python3
# Memhog sintetico acotado por MemoryMax del cgroup, para validar
# fix_memoria.sh sin tocar memoria real fuera del cgroup (Gate 4.4).
import os
import time

MARCADOR = "/run/doctorjk-test-memhog.marker"

if os.path.exists(MARCADOR):
    time.sleep(1_000_000)  # ya asigno una vez: el restart debe liberar, no repetir
else:
    open(MARCADOR, "w").close()
    bloque = bytearray(1000 * 1024 * 1024)
    for i in range(0, len(bloque), 4096):
        bloque[i] = 1  # tocar cada pagina para que cuente como RSS real del cgroup
    time.sleep(1_000_000)
```

Al cerrar la Fase B, ningún recurso queda en estado alterado (todas las
unidades de prueba detenidas, sin marcadores, sin filler). Fase C arranca
desde cero.

#### 9.2.4 Fase C — 4 escenarios reales, secuenciales (`dry_run=false`, `auto_fix=true`)

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  sudo sed -i 's/^dry_run = .*/dry_run = false/; s/^auto_fix = .*/auto_fix = true/' /etc/doctorjk/config.toml
  sudo systemctl restart doctorjk.service
"
```

**Corrección del hallazgo 7 — medición de tiempo, igual para los 4:**

- `T_provocación` = hora local justo antes de correr el comando de
  provocación (`date -u +%FT%T`).
- `T_confirmación` = timestamp del journal en la línea `-> incident:` de
  `journalctl -u doctorjk`.
- `T_resuelto` = campo `fin=` (ISO, embebido en el propio mensaje) de la
  línea `resultado=resolved` que loguea `remediador._log_result()`.
- Se exige `T_resuelto - T_confirmación < 120 s`. `T_resuelto -
  T_provocación` se registra también, sin exigir el mismo tope (incluye el
  tiempo de detección, ya acortado por los intervalos temporales de la
  Fase A).

Para cada uno de los 4 tipos, en este orden — **si el cleanup o el chequeo
de salud de alguno falla, se para ahí, no se sigue con el siguiente:**

**(a) `service_failed`** — provocar igual que B1
(`doctorjk-test-svc`, falla una vez). Confirmar remediación real
(`RESOLVED`, la unidad queda `active`/sleep). **Idempotencia directa:**
`sudo -n /opt/doctorjk/scripts-fix/fix_servicio.sh
doctorjk-test-svc.service` con la unidad ya sana → sale 0 sin reiniciar.
Cleanup: `systemctl stop doctorjk-test-svc`, `reset-failed`, borrar
marcador, quitar de `servicios_vigilados`. Salud: `doctorjk-test-svc` no
queda cargada como `failed`.

**(b) `disk_full`** — recalcular el filler (mismo bloque de §9.2.1, el
disco ya pudo variar) y crearlo. Confirmar remediación real: el script
lista el candidato, lo borra, la postcondición pasa. **Idempotencia
directa:** correr `fix_disco.sh` de nuevo con el disco ya bajo el umbral →
"ya está bajo el umbral" sin acción. Cleanup: confirmar que no queda ningún
`doctorjk-test.log*` residual (ya lo borró el propio script). Salud:
`df` vuelve a ~3%.

**(c) `port_occupied`** — `sudo systemctl start doctorjk-test-occupier`
(con `doctorjk-test-owner` detenida). Confirmar remediación real: se
detiene el ocupante, se reinicia `doctorjk-test-owner`, verificado con
`ss` (no solo `is-active`). **Idempotencia directa:** `fix_puerto.sh 18080`
con `doctorjk-test-owner` ya activa → "ya tiene el puerto" sin acción.
**Chequeo adicional (bonus, ejercita el hallazgo del ocupante que ya
desapareció):** repetir el escenario deteniendo `doctorjk-test-occupier` A
MANO antes de correr `fix_puerto.sh` — confirmar que igual reinicia y
verifica `doctorjk-test-owner` con `ss`, sin declarar éxito solo porque
nadie ocupaba el puerto en ese instante. Cleanup: dejar
`doctorjk-test-owner` corriendo (hace falta para la Fase D) o detenerla si
la Fase D no sigue de inmediato. Salud: `ss -tln` muestra 18080 con el PID
de `doctorjk-test-owner`.

**(d) `memory_low`** — arrancar `doctorjk-test-memhog` (mismo diseño que
B2). Confirmar precondición de cgroup, restart real, postcondición
(memoria disponible vuelve sobre el umbral temporal). **Idempotencia
directa:** `fix_memoria.sh` con memoria ya suficiente → "ya hay memoria
suficiente" sin reiniciar. Cleanup: `systemctl stop doctorjk-test-memhog`,
borrar marcador. Salud: `free -m` vuelve cerca de la línea base de §9.1.

#### 9.2.5 Fase D — tipo no mapeado (`port_down`)

Con `doctorjk-test-owner` y `doctorjk-test-occupier` ambas detenidas
(nadie escucha en 18080, pero sigue en `puertos_vigilados`). Confirmar en
el journal: `"sin script de corrección para port_down, queda solo
diagnosticado"`, `RemediationOutcome.NOT_MAPPED` en el informe, y que el
informe generado NO trae sección "Corrección automática". No hay nada que
limpiar (el estado final esperado — nadie escuchando — ya es el estado en
el que se provocó). Salud: igual que antes, nada más cambió.

#### 9.2.6 Fase E — cierre: apagar todo y restaurar

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  sudo systemctl stop doctorjk-test-llmstub doctorjk-test-owner \
    doctorjk-test-occupier doctorjk-test-svc doctorjk-test-memhog 2>/dev/null || true
  sudo systemctl reset-failed doctorjk-test-svc 2>/dev/null || true
  sudo rm -f /run/doctorjk-test-svc.marker /run/doctorjk-test-memhog.marker \
    /var/log/doctorjk-test.log.1.gz /tmp/doctorjk-llmstub.py /tmp/doctorjk-filler-kb
  sudo cp /etc/doctorjk/config.toml.bak-gate44 /etc/doctorjk/config.toml
  sudo systemctl restart doctorjk.service
  systemctl list-units --all 'doctorjk-test-*' --no-pager
"
```

Las unidades `doctorjk-test-*` quedan detenidas y sin marcador; al ser
transitorias nunca se escribieron a disco, así que un reboot del VPS las
borraría igual aunque algo de esto fallara. Verificación final: los mismos
5 chequeos de §9.1 (servicios reales activos, carga, disco ~3%, memoria
~8.9 GiB libres, `config.toml` con `modo_remediacion="diagnostico"`,
`auto_fix=false`, `dry_run=true`, `unidad_memoria_aprobada=""` como estaba)
más `systemctl list-units --all 'doctorjk-test-*'` vacío o todo `inactive`.

### 9.3 Lo que este protocolo NO hace

- No llama a Cloudflare en ningún momento — todas las fases que pasan por
  el LLM usan el stub local de §9.2.2, nunca la API real.
- No toca `nginx`, `postgresql@16-main` ni `appcarga` reales en ningún
  paso — todos los incidentes usan unidades `doctorjk-test-*` propias.
- No deja `auto_fix=true` ni el stub de LLM activos al terminar (Fase E).
- No crea un snapshot nuevo (§ arriba).
- No repite pruebas de carga sostenida (`hey`/`wrk`) — no hacen falta para
  validar Modo 2.
- No cruza el 90% de disco real en ningún momento (§9.2.1 calcula el
  filler antes de crearlo y aborta si superaría 4 GiB).
