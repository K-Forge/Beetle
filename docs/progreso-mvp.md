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

**Bloqueante P0 corregido antes de esta versión (2026-09-01), ya en
código y probado en local:** `fix_puerto.sh` autorizaba a detener al
ocupante consultando `servicios_vigilados` -- la misma lista que dispara
`service_failed`. Detener a un ocupante que también estuviera vigilado le
haría creer al monitor que ese servicio se cayó solo, y `fix_servicio.sh`
lo reiniciaría, pudiendo recrear `port_occupied` en bucle. Se agregó una
allowlist separada, `ocupantes_puerto_aprobados` (clave TOML en español,
atributo Python `approved_port_occupants: tuple[str, ...]`, vacía por
defecto), y `fix_puerto.sh` ahora consulta esa lista, nunca
`servicios_vigilados`, para decidir si puede detener al ocupante. Cubierto
con pruebas nuevas en `test_config.py` (validación, vacío por defecto,
duplicados, metacaracteres, independencia de las dos listas) y en
`test_scripts_fix.py` (un ocupante vigilado-pero-no-aprobado falla
cerrado; uno aprobado-pero-no-vigilado sí se detiene). El ocupante
sintético de este protocolo (`doctorjk-test-occupier.service`) va SOLO en
`ocupantes_puerto_aprobados`, nunca en `servicios_vigilados` (§9.2.1).

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
- **Ningún estado intermedio queda sin revisar contra un incidente
  automático no planeado (revisión pedida, 2026-09-01):** dos defensas
  distintas cubren esto, y se documentan explícitamente dónde se aplica
  cada una en vez de asumirlas en silencio. (1) El detector confirma por
  persistencia, nunca por umbral instantáneo (CONTEXTO-IA.md §5 punto
  4) -- una ventana de pocos segundos entre comandos ejecutados en
  secuencia por SSH normalmente ni llega a confirmarse como incidente,
  aunque el estado momentáneo sea "roto". (2) Para cualquier ventana que sí
  pudiera durar lo suficiente (`ciclos_persistencia`/`puerto_timeout_s` de
  la Fase A, ~10 s) se diseñó explícitamente el estado de partida para que
  esté siempre sano antes de activar `auto_fix`: `doctorjk-test-owner`
  queda corriendo desde la Fase A (nunca detenida "por las dudas", ver
  §9.2.1) y `doctorjk-test-svc` se restaura a `active` al cierre de la
  Fase B, antes del primer `auto_fix=true` (ver esa transición). La única
  ventana que queda deliberadamente sin cerrar del todo es la del chequeo
  bonus de `port_occupied` (Fase C, paso c) -- revisada y aceptada por
  degradar sin riesgo, no por descuido; el razonamiento completo está en
  ese paso.
- **Por qué sigue sin hacer falta un snapshot nuevo:** cada mutación es
  reversible por diseño (unidades transitorias que nunca tocan disco,
  backup único de `config.toml` antes de tocar nada, reinstalación
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

tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "sudo /tmp/doctorjk-deploy/instalador/install.sh"

# Backup único de config.toml -- sirve tanto para el rollback de este paso
# como para la restauración final de la Fase E. .env NO se toca en ningún
# paso de este protocolo (llm_url vive en config.toml, no en .env) --
# corrección del hallazgo (f): no duplicar un archivo con la credencial
# real si nunca se va a modificar ni restaurar.
#
# **Corrección crítica (ejecución en vivo, 2026-09-01):** este backup va
# DESPUÉS de install.sh, no antes. La versión anterior lo tomaba antes --
# capturando la config de Gate 3 SIN las claves que la migración de
# install.sh recién agrega -- y un restore de emergencia real durante la
# Fase B con ese backup tumbó doctorjk.service en un crash-loop real
# (ConfigError: "falta(n) unidad_memoria_aprobada, ocupantes_puerto_aprobados"),
# exactamente el bug que la migración existe para evitar. El backup correcto
# es el estado YA migrado -- Gate 3 + las tres claves nuevas con su default
# (fail-closed para dos, `["/"]` para puntos_montaje_vigilados -- ver
# hallazgo 1 de §9.4) -- que es también el estado exacto al que debe
# volver la Fase E.
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  sudo cp /etc/doctorjk/config.toml /etc/doctorjk/config.toml.bak-gate44
"
```

Verificar: `systemd-analyze verify`, `sudo -n -l` para los 4 scripts,
`grep NoNewPrivileges` sobre la unidad instalada (los mismos chequeos que ya
tiene `install.sh`), ambas unidades (`doctorjk`, `doctorjk-trigger`)
activas.

**Bloqueante corregido antes de esta versión (2026-09-01), ya en código y
probado en local:** el `config.toml` real del VPS es de Gate 3 -- nunca
tuvo `unidad_memoria_aprobada`, `ocupantes_puerto_aprobados` ni
`puntos_montaje_vigilados` (esta última agregada después, tras el hallazgo
1 de §9.4), las tres claves que Gate 4 y Gate 4.4 agregaron al esquema
(verificado en `git log`: `servicios_vigilados`/`puertos_vigilados` ya
eran de Gate 3, las tres nuevas llegaron después). Como `install.sh`
preserva un `config.toml` existente sin tocarlo, instalar Gate 4 encima
habría dejado el archivo real del VPS sin esas claves, y `load_config()`
es estricto -- el primer `systemctl restart doctorjk.service` de este
mismo Paso 0 habría tumbado el agente con `ConfigError`, sin ningún aviso
durante la instalación. `install.sh` ahora migra de forma aditiva: si una
clave del esquema falta, la agrega con su default (fail-closed para las
dos primeras -- `""` y `[]` --, `["/"]` para la tercera, ver §9.2.1) sin
tocar ninguna línea existente, y reafirma dueño/modo después. Cubierto con
pruebas que corren la migración real contra un fixture con el esquema
exacto de Gate 3 (`pruebas/unitarias/test_instalador.py`): agrega las tres
claves una sola vez, no las duplica en una segunda corrida, y no toca una
config que ya las tiene. Este Paso 0 ya no necesita ningún paso manual
adicional para esto
-- basta con que `install.sh` sea el de esta rama. Además, `install.sh`
ahora valida el `config.toml` resultante con el `load_config()` real
(venv recién instalado) antes de tocar sudoers o reiniciar unidades: si la
migración hubiera producido algo inválido -- o el archivo ya viniera mal
por otra razón --, el Paso 0 aborta ahí, con el agente anterior (si lo
había) sin tocar, en vez de descubrirlo recién en el primer restart.

**Rollback si algo de esto falla (corrección del hallazgo 6, precisada por
el hallazgo (e), y corregida de nuevo acá — hallazgo propio, ver nota
abajo):** nunca `desinstalar.sh` — dejaría el agente completamente fuera.

**Error propio detectado al escribir esta versión, no reportado por
MauItu:** la versión anterior de este rollback apuntaba a
`/home/beetle/Beetle/instalador/install.sh`, asumiendo que ese checkout de
`main` en `6166bf9` era el origen de Gate 3.2. Es falso: `git show
6166bf9 --stat` muestra que `main` en ese commit **no tiene
`doctorjk/config.py` ni `instalador/install.sh` en absoluto** — es solo el
andamiaje de documentación del repo, nunca se le mergeó código. Según
`docs/progreso-mvp.md` §7.2 (mi propio registro de la instalación real),
Gate 3.2 se desplegó por `tar` sobre Tailscale a `~/mvp-integracion-modo-1`
en el VPS, con el `install.sh` de **esta misma rama**
(`mvp/integracion-modo-1`) en el commit que estaba vigente ese día — no
desde `main`. Ese directorio, si sigue ahí, es el `install.sh` real de
antes de Gate 4 (sin `scripts-fix/`, con `NoNewPrivileges=true`, sin las
tres claves nuevas de config). No hay forma de confirmar que sigue ahí sin
tocar el VPS, así que el Paso 0 ahora empieza con un chequeo de solo
lectura que falla rápido si el supuesto no se sostiene, en vez de
descubrirlo recién en un rollback real:

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net \
  "test -x ~/mvp-integracion-modo-1/instalador/install.sh && echo OK || echo FALTA"
# Si imprime FALTA: no hay rollback automático disponible por esta vía.
# Detenerse acá y decidir a mano -- no inventar otro origen sin confirmar
# primero qué es (podría ser un install.sh de una Gate 4 parcial de un
# intento previo, no de Gate 3.2).
```

Asumiendo que existe: re-correr el instalador viejo **por sí solo no
alcanza para un revert exacto** -- ese `install.sh` no sabe nada de
`scripts-fix/` ni de `/etc/sudoers.d/doctorjk` (no existían en Gate 3.2),
así que no los toca -- si el intento de Gate 4 llegó a crearlos antes de
fallar, quedarían huérfanos en disco. Que `NoNewPrivileges=true` vuelva
(sí lo hace: el `install.sh` viejo reinstala `doctorjk.service` desde su
propia plantilla) los deja inertes -- sudo no podría usarlos igual -- pero
inertes no es lo mismo que removidos, y dejar una concesión de sudoers
huérfana no es un rollback correcto. El rollback completo re-corre el
instalador viejo Y borra explícitamente lo que ese instalador no sabe
limpiar:

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  sudo ~/mvp-integracion-modo-1/instalador/install.sh
  sudo rm -f /etc/sudoers.d/doctorjk
  sudo rm -rf /opt/doctorjk/scripts-fix
"
```

`install.sh` es idempotente y preserva `config.toml` existente (nunca toca
`.env`, ver hallazgo (f) más abajo), así que esto vuelve al estado
funcional de Gate 3.2 sin perder configuración. Verificar tras el rollback,
igual que en el Paso 0 normal: `grep NoNewPrivileges` sobre la unidad
instalada (debe volver a aparecer), `/opt/doctorjk/scripts-fix` inexistente,
`/etc/sudoers.d/doctorjk` inexistente.

#### 9.2.1 Fase A — preparar unidades sintéticas y config temporal (todavía sin provocar nada)

**Corrección del hallazgo 2:** ningún paso de este protocolo detiene Nginx
ni mata PostgreSQL reales. Los 4 tipos de incidente se provocan con
unidades `systemd-run` transitorias propias del protocolo, nunca cargadas
desde disco:

| Unidad | Rol | Notas |
|---|---|---|
| `doctorjk-test-svc.service` | `service_failed` | **simplificado (corrección del hallazgo del segundo bloqueante):** ya no un truco de marcador que "falla la primera vez" -- un `sleep infinity` sano y corriente, provocado con `systemctl kill -s KILL` (el equivalente de `kill -9` sin tener que buscar el PID a mano), igual que Gate 3.2 provocó `postgresql` real. Unidad **real efímera** bajo `/run/systemd/system/` -- ver hallazgo del tercer intento, más abajo |
| `doctorjk-test-owner.service` | dueño esperado del puerto 18080 | se registra una vez en la Fase A y se deja **corriendo** (no detenida -- ver más abajo, por qué). Unidad **real efímera** bajo `/run/systemd/system/` -- ver hallazgo del tercer intento, más abajo |
| `doctorjk-test-occupier.service` | ocupante indebido del puerto 18080 | listening en 18080 mientras `doctorjk-test-owner` está detenida = `port_occupied`. Se define con `--collect`: al detenerla, systemd la descarga de inmediato -- **corrección del hallazgo (b):** cada vez que hace falta, se recrea con el `systemd-run` completo (nunca un `systemctl start doctorjk-test-occupier` a secas, que fallaría con "unit not found" si ya fue recolectada). Nunca coexiste con `doctorjk-test-owner` corriendo -- los dos no pueden enlazar el mismo puerto a la vez. Sigue siendo transitoria a propósito: su rol es crearse y destruirse repetidas veces, nunca detenerse-y-reusarse-después, así que el hallazgo del tercer intento no le aplica |
| `doctorjk-test-memhog.service` | consumidor de memoria acotado | `MemoryMax=1200M`, `MemorySwapMax=0`; asigna ~1000 MB una sola vez (marcador en `/run`), así un `restart` real libera la memoria en vez de reasignarla. También transitoria a propósito: `fix_memoria.sh` la reinicia mientras sigue activa, nunca tras un `stop` separado, así que tampoco le aplica el hallazgo |
| `doctorjk-test-llmstub.service` | stub OpenAI-compatible en `127.0.0.1` | ver §9.2.2 |

**Por qué `doctorjk-test-owner` se deja corriendo, no detenida (hallazgo
propio, ver nota abajo):** con `puerto_timeout_s` bajado a 10 s (Fase A,
más abajo), 18080 sin nadie escuchando se confirma como `port_down` en
~10 s. Si la unidad quedara detenida durante toda la Fase A/B, el puerto
se vería roto desde el arranque mismo -- inofensivo mientras `auto_fix` es
`false` (Fase B nunca ejecuta de verdad), pero en el instante en que la
Fase C activa `auto_fix=true`, ese `port_down` ya confirmado dispararía un
ciclo de diagnóstico automático **antes** de que el protocolo llegue a
provocar nada a propósito -- un incidente no planeado, aunque inofensivo
por ser `NOT_MAPPED`. Dejarla corriendo desde la Fase A evita el problema
de raíz: el puerto está sano salvo en las ventanas breves y deliberadas en
que este protocolo lo rompe a propósito.

**Hallazgo del tercer intento (2026-09-01) -- por qué `doctorjk-test-owner`
y `doctorjk-test-svc` ahora son unidades REALES, no transitorias:** el
borrador anterior registraba ambas con `systemd-run --unit=... ` (sin
`--collect`), asumiendo -- documentado, pero nunca probado en vivo -- que
sin ese flag la unidad queda cargada indefinidamente y `systemctl
stop`/`restart` funcionan repetidas veces. Falso: en el tercer intento,
tras un `systemctl stop doctorjk-test-owner` limpio, systemd la recolectó
igual (el journal muestra `Deactivated successfully` / `Stopped`, y
`systemctl list-unit-files` ya no la lista) antes de que el cleanup de
`fix_puerto.sh` en B2 llegara a `restart` -- *"Unit doctorjk-test-owner.service
not found"*. `doctorjk-test-svc`, que en ese mismo momento seguía cargada
porque terminó `failed` (no `stopped` limpio -- un estado `failed` sí
queda visible hasta `reset-failed`), no mostró el problema, lo que hizo
más fácil pasarlo por alto en la ronda anterior. La diferencia real no es
el flag `--collect`: es que un `stop` limpio a `inactive`/`dead` deja a la
unidad transitoria sin nada que la retenga, y el recolector de basura de
systemd la descarga en la siguiente oportunidad -- una ventana de tiempo,
no un evento inmediato, así que corridas anteriores pudieron no haber
tardado lo suficiente entre el `stop` y el siguiente `restart` para
exponerlo.

Esto habría repetido el mismo fallo en la Fase C real (`port_occupied`
depende exactamente del patrón `stop` dueño → ... → `restart` dueño). La
corrección: `doctorjk-test-owner` y `doctorjk-test-svc` pasan a ser
**unidades reales efímeras** bajo `/run/systemd/system/*.service`
(`root:root`, `0644`) en vez de transitorias vía `systemd-run` -- el mismo
mecanismo que usa cualquier unidad instalada de verdad, solo que vive en
`/run` (tmpfs) y desaparece con un reboot o al borrarla explícitamente, sin
tocar `/etc/systemd/system/`. Cargada así, `stop`/`restart` se comportan
exactamente como sobre un servicio de producción -- porque **no hay
recolector de transitorias de por medio**. Consecuencia deliberada
(pedido explícito, no un detalle): **`fix_puerto.sh` y `fix_servicio.sh`
nunca necesitan recrear nada** -- prueban el mismo `systemctl restart`
que corren en producción, sin ningún workaround de prueba escondido en el
camino que valida.

Preparación (sin provocar nada todavía):

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  cat <<'UNIT' | sudo tee /run/systemd/system/doctorjk-test-svc.service > /dev/null
[Unit]
Description=Doctor J/K Gate 4.4 -- servicio sintetico para service_failed

[Service]
ExecStart=/bin/sleep infinity
Restart=no
UNIT
  cat <<'UNIT' | sudo tee /run/systemd/system/doctorjk-test-owner.service > /dev/null
[Unit]
Description=Doctor J/K Gate 4.4 -- dueno sintetico del puerto 18080

[Service]
ExecStart=/usr/bin/python3 -m http.server 18080 --bind 127.0.0.1
Restart=no
UNIT
  sudo chown root:root /run/systemd/system/doctorjk-test-svc.service /run/systemd/system/doctorjk-test-owner.service
  sudo chmod 0644 /run/systemd/system/doctorjk-test-svc.service /run/systemd/system/doctorjk-test-owner.service
  sudo systemctl daemon-reload
  # doctorjk-test-svc: sleep sano, se deja activa (se provoca con kill -9 más adelante).
  sudo systemctl start doctorjk-test-svc
  # doctorjk-test-owner: se deja CORRIENDO -- ver nota arriba.
  sudo systemctl start doctorjk-test-owner
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

- `servicios_vigilados` += `"doctorjk-test-svc.service"` (sin esto,
  `fix_servicio.sh` escala en vez de reiniciarla).
- `puertos_vigilados` += `{ puerto = 18080, servicio =
  "doctorjk-test-owner.service" }`.
- `ocupantes_puerto_aprobados` += `"doctorjk-test-occupier.service"`
  (**corrección del hallazgo P0, 2026-09-01:** `doctorjk-test-occupier`
  va SOLO acá, nunca en `servicios_vigilados`. `fix_puerto.sh` ahora
  autoriza a detener un ocupante consultando esta allowlist nueva, no
  `servicios_vigilados` -- ver `doctorjk/config.py` y `scripts-fix/
  fix_puerto.sh`. Si el ocupante estuviera también vigilado, detenerlo
  dispararía `service_failed` sobre sí mismo y `fix_servicio.sh` lo
  reiniciaría, pudiendo recrear `port_occupied` en bucle).
- `disco_pct` → `5` (original respaldado en el Paso 0).

**Bloqueante de la ejecución real anterior (2026-09-01), resuelto en
código, no en el protocolo (decisión de MauItu):** `monitor.py`
evaluaba `disco_pct` contra **todos los mount points reales** que reporta
`df`, no solo `/` (a diferencia de `fix_disco.sh`, que sí está acotado a
`/`). Bajar `disco_pct` a 5 sin ese filtro disparaba `disk_full` también
en `/boot`, `/boot/efi` y `efivars` -- ver el intento real fallido en
§9.4. La solución fue una allowlist nueva en el propio agente,
`puntos_montaje_vigilados` (clave TOML) / `monitored_mount_points`
(`AppConfig`), **requerida, no vacía, default `["/"]`** -- `df` se sigue
leyendo completo (la recolección no cambió), pero `normalize_snapshot()`
ahora filtra qué mounts producen señal. Con el default de `["/"]`
(el que trae la migración de `install.sh`, sin que este protocolo tenga
que tocar la clave para nada), bajar `disco_pct` a 5 en la Fase A **ya
solo afecta a `/`** -- el bloqueante queda resuelto sin agregar
complejidad a este paso. Ver `doctorjk/config.py` (`_monitored_mount_points_list`)
y `doctorjk/monitor.py` (`normalize_snapshot`) para la implementación, y
la nota de trade-off en el comentario de `AppConfig.monitored_mount_points`:
un cliente puede agregar otro mount ahí para que Modo 1 lo vigile, pero
`fix_disco.sh` (Modo 2) sigue acotado a `/` nada más -- ese mount extra
quedaría diagnosticado, nunca remediado automáticamente.

**Preflight que confirma el filtro (antes de bajar `disco_pct`):**

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  sudo grep '^puntos_montaje_vigilados' /etc/doctorjk/config.toml
"
# Debe imprimir exactamente puntos_montaje_vigilados = ["/"] -- si no,
# PARAR antes de tocar disco_pct: bajar el umbral sin el filtro activo
# reproduce el incidente no planeado de §9.4.
```
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

1. Provocar con `kill -9` real, igual que Gate 3.2 hizo con `postgresql`
   (**corrección del segundo bloqueante:** ya no el truco de marcador que
   "falla la primera vez" -- `doctorjk-test-svc` es un `sleep infinity`
   sano, `systemctl kill` le manda la señal sin tener que buscar el PID a
   mano): `sudo systemctl kill -s KILL doctorjk-test-svc`.
2. Esperar la confirmación del detector (`journalctl -u doctorjk | grep -- '-> incident:'`).
3. Confirmar en el informe anexado: sección de remediación con
   `[DRY-RUN] Ningún comando fue ejecutado`.
4. Confirmar que NO se ejecutó el restart real: la unidad sigue en estado
   `failed` (no pasó a `active`).
5. **Sin cleanup individual acá (corrección del segundo bloqueante):** se
   deja `failed` a propósito -- B2 reusa el mismo estado roto para su
   propio chequeo de `fix_servicio.sh` sin tener que volver a matarla. La
   restauración a `active` es una única acción al cierre de toda la Fase
   B (ver más abajo), no un paso por sub-prueba.

**B2 — los 4 scripts, llamados directo (sin pasar por el pipeline, sin
LLM), en dry-run.** Cada uno se provoca, se llama a mano, se confirma que
no muta nada, y se limpia antes de pasar al siguiente (excepto
`doctorjk-test-svc`, que sigue `failed` desde B1 -- ver arriba):

- `fix_servicio.sh`: reusa el estado `failed` que dejó B1, sin volver a
  matarla → `sudo -n /opt/doctorjk/scripts-fix/fix_servicio.sh
  doctorjk-test-svc.service` → confirmar `[DRY-RUN]` y que sigue `failed`.
  Sin cleanup acá tampoco (misma razón que B1).
- `fix_disco.sh`: (**corrección del hallazgo (2): `fallocate` sobre
  `/var/log` exige root, faltaba el `sudo`**) `sudo fallocate -l
  "$(cat /tmp/doctorjk-filler-kb)K" /var/log/doctorjk-test.log.1.gz &&
  sudo touch -d '10 days ago' /var/log/doctorjk-test.log.1.gz` (tope de 4
  GiB y cleanup sin cambios, ya calculados en §9.2.1) → `sudo -n
  /opt/doctorjk/scripts-fix/fix_disco.sh /` (**corrección del hallazgo
  (c):** el script exige `$1` = punto de montaje; sin argumento falla con
  "uso: fix_disco.sh <punto-de-montaje>", ni siquiera llega a mirar
  `dry_run`) → confirmar `[DRY-RUN]` y que el archivo sigue ahí → cleanup:
  `sudo rm -f /var/log/doctorjk-test.log.1.gz`. **Este sub-paso corre
  directo contra el `/var/log` real del VPS, sin aislar nada -- es seguro
  porque `dry_run=true` nunca llega a `rm` de verdad** (confirmado en el
  tercer intento: el script listó 28 candidatos reales de `/var/log/nginx`,
  `/var/log/postgresql`, etc., y no tocó ninguno). El aislamiento del
  hallazgo del tercer intento (ver antes de la Fase C, más abajo) hace
  falta recién cuando `dry_run=false` -- acá no aplica.
- `fix_puerto.sh`: **corrección del hallazgo (1) -- orden exacto, porque
  `doctorjk-test-owner` sigue escuchando en 18080 desde la Fase A y el
  ocupante no puede enlazar el mismo puerto:**
  1. `sudo systemctl stop doctorjk-test-owner`.
  2. Recrear el ocupante (corrección del hallazgo (b), ver tabla de
     §9.2.1 -- nunca `systemctl start` a secas): `sudo systemd-run
     --unit=doctorjk-test-occupier --collect python3 -m http.server
     18080 --bind 127.0.0.1`.
  3. `sudo -n /opt/doctorjk/scripts-fix/fix_puerto.sh 18080` → confirmar
     `[DRY-RUN]` y que el ocupante sigue escuchando (no
     `doctorjk-test-owner`).
  4. Cleanup: `sudo systemctl stop doctorjk-test-occupier` (la recolecta
     sola por el `--collect`), luego `sudo systemctl restart
     doctorjk-test-owner` -- **ahora confiable** (hallazgo del tercer
     intento, ver tabla de §9.2.1): `doctorjk-test-owner` es una unidad
     real bajo `/run/systemd/system/`, no transitoria, así que no hay
     ventana de recolección de basura entre el `stop` de arriba y este
     `restart`.
  5. Verificar salud antes de seguir con el siguiente sub-paso de B2:
     `ss -tln` muestra 18080 con el PID de `doctorjk-test-owner` — el
     puerto no puede quedar sin dueño entrando a los sub-pasos de disco o
     memoria (mismo motivo que en §9.2.1: `port_down` confirmado con
     `auto_fix` todavía en `false` es inofensivo, pero dejarlo así sería
     un descuido, no una decisión).
- `fix_memoria.sh`: `sudo systemd-run --unit=doctorjk-test-memhog
  --property=MemoryMax=1200M --property=MemorySwapMax=0 --collect
  python3 /tmp/doctorjk-memhog.py` (creado y validado ANTES de esta línea,
  ver más abajo -- corrección del hallazgo 3) → `sudo -n
  /opt/doctorjk/scripts-fix/fix_memoria.sh` → confirmar `[DRY-RUN]` y que
  la memoria disponible sigue baja → cleanup: `sudo systemctl stop
  doctorjk-test-memhog`, `sudo rm -f /run/doctorjk-test-memhog.marker`.

**`/tmp/doctorjk-memhog.py` (corrección del hallazgo 3):** no es un
archivo del repo -- `git archive HEAD` (Paso 0) solo transfiere lo
comiteado, y esto nunca se comiteó. Documentarlo como si ya estuviera en
`/tmp/doctorjk-deploy/` habría sido una referencia a un archivo
inexistente. Igual que el stub de LLM (§9.2.2), se crea explícitamente en
el VPS con un heredoc, ANTES de la primera vez que un `systemd-run` lo
use, y se valida por hash que llegó completo (un corte a mitad de la
transferencia por SSH produciría un script que falla en runtime, no al
crearlo):

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  cat > /tmp/doctorjk-memhog.py <<'PYEOF'
<contenido de abajo, sin indentar>
PYEOF
  echo 'fb4869cac0160ed3a862cc21be4ab78fa7b75d77d136fdf25b043fc016227c0e  /tmp/doctorjk-memhog.py' \
    | sha256sum -c - \
    || { echo 'memhog.py no coincide con el esperado -- no usar' >&2; exit 1; }
  python3 -m py_compile /tmp/doctorjk-memhog.py \
    || { echo 'memhog.py no compila' >&2; exit 1; }
"
```

Contenido de `/tmp/doctorjk-memhog.py` (el hash de arriba es de este texto
exacto; si se edita, recalcular con `sha256sum` antes de actualizar el
comando):

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

Al cerrar la Fase B, el filler de disco, `doctorjk-test-occupier` y
`doctorjk-test-memhog` quedan limpios (cada bullet de B2 ya se encargó,
incluido volver a dejar `doctorjk-test-owner` escuchando al final de su
propio sub-paso). Solo **`doctorjk-test-svc` sigue `failed`** a propósito
desde B1. Antes de armar `auto_fix=true` falta dejarla sana también:

**Corrección del segundo bloqueante -- por qué esto no puede saltarse:**
`doctorjk-test-svc` sigue en `servicios_vigilados`. Si se activara
`auto_fix=true` mientras sigue `failed`, el incidente `service_failed` ya
confirmado (persistencia cumplida hace rato, durante toda la Fase B) se
remediaría solo, de forma automática y sin cronometrar, apenas
`doctorjk.service` reinicie con la config nueva -- exactamente el
incidente "no planeado" que hay que evitar: la Fase C mide desde una
provocación deliberada, no desde un arrastre de la Fase B.

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  sudo systemctl restart doctorjk-test-svc
"
```

(`doctorjk-test-owner` no necesita nada acá: el sub-paso de `fix_puerto.sh`
en B2 ya la dejó corriendo de nuevo al cerrar, como su propio paso 4 y 5
-- no queda pendiente de esta transición.)

#### 9.2.3bis Aislamiento de `/var/log` y del journal antes de ejecutar `fix_disco.sh` real (hallazgo del tercer intento)

**Cuándo aplica esto -- ventana estrecha, no toda la Fase C (corrección
propia, encontrada al escribir este registro, antes de cualquier
ejecución):** el `BindPaths` de más abajo aísla `/var/log` Y
`/run/log/journal` para **todo** `doctorjk.service`, no solo para
`fix_disco.sh` -- `recolector.py` llama `journalctl` directamente como
subproceso del propio `doctorjk.service` (ver `doctorjk/recolector.py`)
para juntar evidencia de **cualquier** tipo de incidente, no solo
`disk_full`. Si este aislamiento quedara activo durante toda la Fase C, la
recolección de evidencia de `service_failed`, `port_occupied` y
`memory_low` vería un journal vacío/aislado en vez del real, rompiendo
esos tres escenarios sin necesidad. La ventana correcta es: montar el
`BindPaths` **inmediatamente antes** del escenario (b), y retirarlo
**inmediatamente después** de su cleanup, antes de seguir con (c). El
orden de los 4 escenarios de la Fase C ya pone a `disk_full` segundo
-- ver más abajo -- así que la ventana aislada queda acotada a ese único
sub-paso.

**Hallazgo:** en B2 (sub-paso anterior), `fix_disco.sh` en dry-run listó 28
candidatos reales bajo `/var/log` -- `nginx/access.log.*.gz`,
`postgresql/postgresql-16-main.log.2.gz`, `auth.log.*.gz`, `kern.log.*`,
`apt/*.gz`, `fail2ban.log.*.gz`, etc. Inofensivo en dry-run (nunca llega a
`rm`), pero la Fase C (b) corre el mismo script con `dry_run=false`: sin
aislar, borraría logs legítimos de un VPS compartido con Nginx +
PostgreSQL reales. **Prohibido ejecutar el escenario real de disco sin
aislamiento verificado.**

**Cómo funciona el almacenamiento de journald (investigado para diseñar el
aislamiento, no asumido):** `Storage=` en `journald.conf` (default `auto`)
decide el destino. En `auto`: si `/var/log/journal/` existe, se usa
almacenamiento persistente ahí (`/var/log/journal/<machine-id>/`); si no
existe, cae a volátil bajo `/run/log/journal/<machine-id>/`.
`Storage=persistent` fuerza siempre `/var/log/journal` (creándolo si
falta); `Storage=volatile` fuerza siempre `/run/log/journal`.
`journalctl --vacuum-size=SIZE` sin `--root`/`-D`/`--file` -- como lo
llama `fix_disco.sh` -- actúa sobre el directorio que esté efectivamente
en uso. **Cuál de los dos modos usa este VPS todavía no está confirmado
por lectura directa**, así que aislar solo `/var/log` no alcanza: si el
journal fuera volátil, `/run/log/journal` queda completamente afuera y
`--vacuum-size` seguiría tocando el journal real del host. Se aíslan las
dos rutas.

**Mecanismo -- `BindPaths` efímero sobre `doctorjk.service`:**
`doctorjk.service` YA corre con `ProtectSystem=strict` (namespace de
montaje privado activo por diseño, ver `instalador/doctorjk.service`), con
`/var/log` como una de las dos únicas rutas escribibles
(`ReadWritePaths=/var/lib/doctorjk /var/log`) -- exactamente la ruta a
remapear. Un drop-in agrega `BindPaths=` para redirigir esa ruta (y la del
journal volátil) hacia directorios de prueba en disco, dentro del mismo
namespace que ya existe -- no hace falta crear un namespace nuevo,
`BindPaths` lo reusa. `sudo -n fix_disco.sh`, como hijo del proceso de
`doctorjk.service`, hereda ese namespace igual que hereda el resto del
hardening (mismo razonamiento que el propio comentario de
`ReadWritePaths` en `instalador/doctorjk.service`: los namespaces de
montaje se heredan por fork/exec, y `sudo` no los levanta aunque el hijo
pase a UID 0).

`/run/systemd/system/doctorjk.service.d/99-gate44-aislar-logs.conf`:
```ini
[Service]
# Efimero (Gate 4.4): redirige /var/log y /run/log/journal, DENTRO del
# namespace de doctorjk.service y sus hijos (incluidos los scripts de Modo
# 2 via "sudo -n"), hacia directorios de prueba en disco. Ningun archivo
# real del host queda visible ni escribible desde ahi. df / no se ve
# afectado -- el bind es sobre subdirectorios, nunca sobre / -- asi que
# sigue midiendo el filesystem raiz real.
BindPaths=/var/tmp/doctorjk-gate4-varlog:/var/log
BindPaths=/var/tmp/doctorjk-gate4-runlog-journal:/run/log/journal
```

Preparación:

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  # Manifest ANTES -- referencia para confirmar en la Fase E que el
  # /var/log real del host no cambió ni un byte durante toda la ventana
  # aislada.
  sudo find /var/log -type f -printf '%p %s %T@\n' | sort | sha256sum \
    > /tmp/doctorjk-varlog-manifest-antes.sha256
  cat /tmp/doctorjk-varlog-manifest-antes.sha256

  sudo mkdir -p /var/tmp/doctorjk-gate4-varlog /var/tmp/doctorjk-gate4-runlog-journal
  # Decoy: un log activo, sin sufijo de rotación, que fix_disco.sh NUNCA
  # debe tocar -- confirma que el patrón sigue discriminando bien dentro
  # del directorio aislado, no solo que el filler se borra.
  echo 'log activo, no debe borrarse' | sudo tee /var/tmp/doctorjk-gate4-varlog/app.log > /dev/null

  sudo mkdir -p /run/systemd/system/doctorjk.service.d
  cat <<'DROPIN' | sudo tee /run/systemd/system/doctorjk.service.d/99-gate44-aislar-logs.conf > /dev/null
[Service]
BindPaths=/var/tmp/doctorjk-gate4-varlog:/var/log
BindPaths=/var/tmp/doctorjk-gate4-runlog-journal:/run/log/journal
DROPIN
  sudo systemctl daemon-reload
  sudo systemctl restart doctorjk.service
"
```

**Verificación OBLIGATORIA -- gate antes de autorizar `dry_run=false` sobre
`fix_disco.sh`. Si cualquiera de estos chequeos no confirma aislamiento
total, NO se ejecuta el escenario real de disco: se documenta como no
ejecutado por esta razón y se sigue con los otros 3 escenarios de la Fase
C (servicio, puerto, memoria) y con la Fase D -- perder un escenario real
es aceptable; borrar un log de producción no lo es.**

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  echo '--- sintaxis del drop-in ---'
  sudo systemd-analyze verify doctorjk.service

  echo '--- que ve REALMENTE el namespace del servicio (autoridad final) ---'
  pid=\$(systemctl show doctorjk.service -p MainPID --value)
  sudo nsenter --mount=/proc/\$pid/ns/mnt -- ls -la /var/log
  sudo nsenter --mount=/proc/\$pid/ns/mnt -- ls -la /run/log/journal 2>&1

  echo '--- df / sigue midiendo la raiz real (no debe moverse por el bind) ---'
  df -h /
"
```

Criterio de aprobación, los tres a la vez:

1. `systemd-analyze verify` no reporta error sobre el drop-in.
2. `ls /var/log` desde el namespace muestra **solo** `app.log` (el decoy)
   -- ningún `nginx/`, `postgresql/`, `auth.log`, `kern.log`, etc. real.
   Lo mismo para `/run/log/journal` (vacío, o solo lo que el propio
   journald del namespace haya podido crear ahí -- nunca los directorios
   de machine-id reales del host).
3. `df -h /` coincide con la línea base de §9.1 -- confirma que el bind no
   movió la medición de la raíz.

Si el punto 2 muestra cualquier archivo que no sea el decoy, o si
`/run/log/journal` no existe como destino de bind válido y systemd lo
reporta como error de montaje: **parar, no autorizar la ejecución real de
`fix_disco.sh`, no inventar un mecanismo alternativo en el momento.**

El filler real de la Fase C (b) se crea dentro de
`/var/tmp/doctorjk-gate4-varlog/`, nunca directo en `/var/log` -- el
namespace lo hace aparecer en `/var/log` para `fix_disco.sh`, pero el
archivo físico vive en `/var/tmp`, en el mismo filesystem raíz que mide
`df /` (VPS de una sola partición, §9.1), así que sigue contando para
cruzar el umbral.

**Retiro del aislamiento -- inmediatamente después del cleanup del
escenario (b), ANTES de (c), incluida la verificación de integridad final
(no esperar a la Fase E: fail fast, igual que cualquier otro chequeo de
salud de este protocolo):**

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  sudo rm -rf /run/systemd/system/doctorjk.service.d
  sudo systemctl daemon-reload
  sudo systemctl restart doctorjk.service
  sudo rm -rf /var/tmp/doctorjk-gate4-varlog /var/tmp/doctorjk-gate4-runlog-journal

  sudo find /var/log -type f -printf '%p %s %T@\n' | sort | sha256sum \
    > /tmp/doctorjk-varlog-manifest-despues.sha256
  diff /tmp/doctorjk-varlog-manifest-antes.sha256 /tmp/doctorjk-varlog-manifest-despues.sha256 \
    && echo 'MANIFEST IDÉNTICO: /var/log real intacto' \
    || echo 'DIVERGENCIA: PARAR -- no seguir con (c) hasta entenderla'
  sudo rm -f /tmp/doctorjk-varlog-manifest-antes.sha256 /tmp/doctorjk-varlog-manifest-despues.sha256
"
```

Verificar antes de seguir con (c): `sudo ls /var/log | head` muestra los
directorios reales del host (`nginx`, `postgresql`, etc.), no el decoy --
confirma que la vista real volvió, y el manifest de arriba dio idéntico.
Si el escenario (b) se saltó por no
haber aprobado el gate, este bloque no hace falta (nada quedó montado).

#### 9.2.4 Fase C — 4 escenarios reales, secuenciales (`dry_run=false`, `auto_fix=true`)

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  sudo sed -i 's/^dry_run = .*/dry_run = false/; s/^auto_fix = .*/auto_fix = true/' /etc/doctorjk/config.toml
  sudo systemctl restart doctorjk.service
"
```

Punto de partida antes del primer escenario, ya verificado por el paso de
arriba: `doctorjk-test-svc` activa, `doctorjk-test-owner` escuchando en
18080, sin filler de disco, sin `doctorjk-test-memhog` corriendo -- nada
pendiente de remediar cuando `auto_fix` se activa.

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

**(a) `service_failed`** — provocar igual que B1: `sudo systemctl kill -s
KILL doctorjk-test-svc`. Confirmar remediación real
(`RESOLVED`, la unidad queda `active`/sleep). **Idempotencia directa:**
`sudo -n /opt/doctorjk/scripts-fix/fix_servicio.sh
doctorjk-test-svc.service` con la unidad ya sana → sale 0 sin reiniciar.
**Cleanup (corrección del hallazgo (a)):** ninguno acá. `doctorjk-test-svc`
sigue en `servicios_vigilados` con `auto_fix=true` durante el resto de la
Fase C/D -- detenerla ahora la dejaría `failed` de nuevo mientras sigue
vigilada y con remediación real habilitada, y el propio monitor (con los
intervalos rápidos de la Fase A) podría reiniciarla sola antes de que este
protocolo termine de editar `servicios_vigilados`, o competir con ese
edit. Se la deja **activa** (ya sana) hasta la Fase E: recién ahí, con
`config.toml` restaurado y `doctorjk.service` ya reiniciado con la config
original, se la detiene. Salud de este paso: la unidad quedó `active`, no
`failed`.

**(b) `disk_full`** — **secuencia completa de §9.2.3bis, autocontenida en
este único sub-paso (hallazgo propio: el aislamiento rompe la recolección
de evidencia de los otros 3 escenarios si queda montado más tiempo del
necesario -- ver la nota "Cuándo aplica esto" al inicio de esa sección):**

1. Manifest antes + montar el `BindPaths` (bloque "Preparación" de
   §9.2.3bis).
2. Verificación obligatoria (bloque "Verificación OBLIGATORIA" de
   §9.2.3bis) -- **gate: si no confirma aislamiento total, se salta este
   escenario por completo, se documenta el motivo, y se sigue directo con
   (c) sin haber montado nada que retirar.**
3. Con el gate aprobado: recalcular el filler (mismo bloque de §9.2.1, el
   disco ya pudo variar) y crearlo **dentro de
   `/var/tmp/doctorjk-gate4-varlog/`** (nunca directo en `/var/log`), con
   el mismo nombre y mtime de siempre para que el patrón de
   `fix_disco.sh` lo reconozca.
4. Confirmar remediación real: el script lista el candidato, lo borra, la
   postcondición pasa. **Idempotencia directa:**
   `sudo -n /opt/doctorjk/scripts-fix/fix_disco.sh /` con el disco ya bajo
   el umbral (corrección del hallazgo (c): siempre con el argumento `/`)
   → "ya está bajo el umbral" sin acción.
5. **Verificación del decoy (hallazgo del tercer intento):** `app.log`
   (el decoy de §9.2.3bis) sigue existiendo con su contenido intacto --
   confirma que el patrón de borrado discriminó bien también en ejecución
   real, no solo en dry-run.
6. Cleanup del filler: confirmar que no queda ningún `doctorjk-test.log*`
   residual dentro del directorio aislado (ya lo borró el propio script).
7. **Retiro del aislamiento** (bloque "Retiro del aislamiento" de
   §9.2.3bis) -- obligatorio antes de pasar a (c), con o sin gate
   aprobado en el paso 2.

Salud de este sub-paso: `df` vuelve a ~3% (mide la raíz real, el bind no
lo afecta) Y, tras el paso 7, `/var/log` real vuelve a ser visible desde
el namespace del servicio.

**(c) `port_occupied`** — `doctorjk-test-owner` está corriendo desde la
Fase A (§9.2.1); hay que liberar el puerto ANTES de poder crear el
ocupante, los dos no pueden enlazar 18080 a la vez. Este es exactamente el
patrón stop-luego-restart-por-separado que expuso el hallazgo del tercer
intento -- confiable ahora porque `doctorjk-test-owner` es una unidad real
bajo `/run/systemd/system/`, no transitoria (ver tabla de §9.2.1):

1. `sudo systemctl stop doctorjk-test-owner`.
2. Recrear el ocupante (corrección del hallazgo (b): `systemd-run
   --unit=doctorjk-test-occupier --collect python3 -m http.server 18080
   --bind 127.0.0.1`, nunca `systemctl start` a secas — ver tabla de
   §9.2.1).
3. Confirmar remediación real: se detiene el ocupante, se reinicia
   `doctorjk-test-owner`, verificado con `ss` (no solo `is-active`).

**Idempotencia directa:** `fix_puerto.sh 18080` con `doctorjk-test-owner`
ya activa → "ya tiene el puerto" sin acción.

**Chequeo adicional (bonus, ejercita el hallazgo del ocupante que ya
desapareció) — corrección del segundo bloqueante, orden exacto:**

1. `sudo systemctl stop doctorjk-test-owner` (libera el puerto de nuevo).
2. Recrear el ocupante (mismo `systemd-run --collect` de arriba).
3. `sudo systemctl stop doctorjk-test-occupier` (se recolecta sola por el
   `--collect` — el punto es que YA NO ocupa el puerto cuando corra
   `fix_puerto.sh`).
4. `sudo -n /opt/doctorjk/scripts-fix/fix_puerto.sh 18080` — confirmar que
   igual reinicia y verifica `doctorjk-test-owner` con `ss`, sin declarar
   éxito solo porque nadie ocupaba el puerto en ese instante.

**Sobre la ventana entre los pasos 1 y 4 del bonus (revisión pedida:
¿puede disparar un incidente no planeado?):** sí, en teoría -- con
`auto_fix=true` ya activo, el mismo `fix_puerto.sh` automático que este
protocolo valida podría, en principio, adelantarse y remediar el
`port_occupied` real solo, antes de que el paso 4 (la llamada directa)
llegue a correr. Se revisó y se acepta: el detector confirma por
persistencia (`ciclos_persistencia`/`puerto_timeout_s`, CONTEXTO-IA.md §5
punto 4), así que una ventana de pocos segundos entre estos pasos —
ejecutados en secuencia inmediata por SSH — normalmente ni llega a
confirmarse. Si de todas formas se adelantara, el resultado es
inofensivo: la llamada directa del paso 4 encontraría a
`doctorjk-test-owner` ya activa y tomaría la rama idempotente ("ya tiene
el puerto"), degradando el chequeo bonus a una confirmación de
idempotencia en vez de una prueba fresca de la rama "ocupante
desaparecido" -- pérdida de cobertura en esa corrida puntual, nunca un
estado incorrecto o sin acotar (esa rama ya tiene cobertura aparte con
dobles en `pruebas/unitarias/test_scripts_fix.py`, así que no es la única
red). No se rediseñó para eliminar la ventana por completo porque hacerlo
exigiría otro ciclo de apagar/reencender `auto_fix` a mitad de la Fase C,
más riesgo que el que evita.

Cleanup tras el bonus: `doctorjk-test-occupier` ya quedó recolectada (no
existe más, por el `--collect`) — nada que detener ahí.
`doctorjk-test-owner` termina **corriendo** (postcondición tanto del
escenario principal como del bonus) — la usa la Fase D tal cual, no hace
falta recrearla. Salud: `ss -tln` muestra 18080 con el PID de
`doctorjk-test-owner`, y `systemctl list-units doctorjk-test-occupier*` no
encuentra nada cargado.

**(d) `memory_low`** — arrancar `doctorjk-test-memhog` (mismo diseño que
B2). Confirmar precondición de cgroup, restart real, postcondición
(memoria disponible vuelve sobre el umbral temporal). **Idempotencia
directa:** `fix_memoria.sh` con memoria ya suficiente → "ya hay memoria
suficiente" sin reiniciar. Cleanup: `systemctl stop doctorjk-test-memhog`,
borrar marcador. Salud: `free -m` vuelve cerca de la línea base de §9.1.

#### 9.2.5 Fase D — tipo no mapeado (`port_down`)

Detener `doctorjk-test-owner` (`doctorjk-test-occupier` ya no existe desde
el `--collect` del paso anterior) — nadie escucha en 18080, pero sigue en
`puertos_vigilados`.

**Corrección del hallazgo (d):** `remediador._skip()` (la rama que produce
`NOT_MAPPED`) nunca llama a `_log_result()` -- eso solo pasa cuando
`classify()` sí encuentra un script y se llega a ejecutarlo. Lo único
observable desde afuera para `NOT_MAPPED` es: (1) el mensaje que sí loguea
`remediador.remediate()` directamente antes de retornar, y (2) que
`informe.append_remediation()` no escribe nada para este resultado. No hay
forma de "ver" el valor `RemediationOutcome.NOT_MAPPED` en el informe --
no aparece ahí, ni podría, porque la función que lo devuelve nunca llega a
escribir esa sección. Confirmar entonces, sin afirmar el outcome dentro
del informe:

- En el journal: `"sin script de corrección para port_down, queda solo
  diagnosticado"`.
- En el informe generado para este incidente: el diagnóstico del LLM (del
  stub) está, pero NO hay sección "Corrección automática" -- su ausencia
  es la evidencia, no un texto que la nombre.

No hay nada que limpiar (el estado final esperado — nadie escuchando — ya
es el estado en el que se provocó, y `doctorjk-test-owner` de todos modos
se detiene en la Fase E). Salud: igual que antes, nada más cambió.

#### 9.2.6 Fase E — cierre: apagar todo y restaurar

**Corrección del hallazgo (a) -- el orden acá importa:** `config.toml` se
restaura y `doctorjk.service` se reinicia **primero**. Recién con el
agente ya corriendo la config original (`servicios_vigilados` sin
`doctorjk-test-svc`, `auto_fix=false`) es seguro detener las unidades de
prueba -- si se detuvieran antes, con la config temporal todavía activa y
los intervalos rápidos de la Fase A, el propio monitor podría reaccionar a
mitad de este bloque. **Hallazgo del tercer intento:** el drop-in de
aislamiento de `/var/log` (§9.2.3bis) ya debería estar retirado desde el
cierre del escenario (b) de la Fase C -- el `rm -rf` de ese directorio acá
es un respaldo idempotente (no falla si ya no existe), no el punto
principal de remoción. Si por algún aborto llegó hasta acá todavía
montado, este mismo bloque lo retira junto con la config: un solo
`daemon-reload` + `restart` alcanza para que `doctorjk.service` vuelva a
la config original Y a ver el `/var/log` real a la vez.

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  sudo cp /etc/doctorjk/config.toml.bak-gate44 /etc/doctorjk/config.toml
  sudo rm -rf /run/systemd/system/doctorjk.service.d
  sudo systemctl daemon-reload
  sudo systemctl restart doctorjk.service
  sudo systemctl stop doctorjk-test-llmstub doctorjk-test-owner \
    doctorjk-test-svc doctorjk-test-memhog 2>/dev/null || true
  sudo systemctl reset-failed doctorjk-test-svc 2>/dev/null || true
  sudo rm -f /run/systemd/system/doctorjk-test-owner.service \
    /run/systemd/system/doctorjk-test-svc.service
  sudo systemctl daemon-reload
  sudo rm -f /run/doctorjk-test-memhog.marker \
    /var/log/doctorjk-test.log.1.gz /tmp/doctorjk-llmstub.py \
    /tmp/doctorjk-memhog.py /tmp/doctorjk-filler-kb
  sudo rm -rf /var/tmp/doctorjk-gate4-varlog /var/tmp/doctorjk-gate4-runlog-journal
  systemctl list-units --all 'doctorjk-test-*' --no-pager
  systemctl list-unit-files --all 'doctorjk-test-*' --no-pager
"
```

(`doctorjk-test-occupier` no aparece en este `stop`: ya fue recolectada
sola por su propio `--collect` en la Fase C. `doctorjk-test-owner` y
`doctorjk-test-svc` sí necesitan el `rm` explícito de su unit file --
hallazgo del tercer intento: al ser unidades reales, no transitorias, no
desaparecen solas con un `stop`, hay que borrar el archivo y recargar.)

**Verificación de integridad de `/var/log` real -- respaldo, no el chequeo
principal:** el escenario (b) de la Fase C (§9.2.3bis, bloque "Retiro del
aislamiento") ya corre este mismo diff inmediatamente después de retirar
el `BindPaths`, antes de seguir con (c) -- fail fast, no esperar a la
Fase E para descubrir una divergencia. Este bloque es solo una red por si
el protocolo se abortó a mitad del escenario (b), antes de llegar a ese
paso, dejando el manifest "antes" sin comparar:

```bash
tailscale ssh beetle@beetle-vps.tail1e5d4e.ts.net "
  if [[ -f /tmp/doctorjk-varlog-manifest-antes.sha256 ]]; then
    sudo find /var/log -type f -printf '%p %s %T@\n' | sort | sha256sum \
      > /tmp/doctorjk-varlog-manifest-despues.sha256
    diff /tmp/doctorjk-varlog-manifest-antes.sha256 /tmp/doctorjk-varlog-manifest-despues.sha256 \
      && echo 'MANIFEST IDÉNTICO: /var/log real intacto' \
      || echo 'DIVERGENCIA: revisar antes de continuar'
    sudo rm -f /tmp/doctorjk-varlog-manifest-antes.sha256 /tmp/doctorjk-varlog-manifest-despues.sha256
  else
    echo 'sin manifest pendiente -- ya se verificó en el escenario (b), o el aislamiento nunca se usó en este intento'
  fi
"
```

Un `diff` con salida (cualquier línea) es una divergencia real -- pararse
ahí y no dar la Fase E por terminada hasta entenderla, igual que cualquier
otro chequeo de salud de este protocolo.

Las unidades `doctorjk-test-*` quedan detenidas, sin unit files y sin
marcador. `.env` nunca se tocó (hallazgo (f)), así que no hay nada que
restaurar ahí. Verificación final: los mismos 5 chequeos de §9.1
(servicios reales activos, carga, disco ~3%, memoria ~8.9 GiB libres,
`config.toml` con `modo_remediacion="diagnostico"`, `auto_fix=false`,
`dry_run=true`, `unidad_memoria_aprobada=""`, `ocupantes_puerto_aprobados=[]`,
`puntos_montaje_vigilados=["/"]` como estaba) más `systemctl list-units
--all 'doctorjk-test-*'` vacío o todo `inactive`, `systemctl
list-unit-files --all 'doctorjk-test-*'` sin las unidades reales de
`doctorjk-test-owner`/`doctorjk-test-svc`, y el manifest de `/var/log`
idéntico antes/después si se usó el aislamiento.

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

### 9.4 Intento real en el VPS (2026-09-01) — Paso 0 y Fase A completos, Fase B parcial, Fase C no arrancada

Ejecutado con punto de control explícito de MauItu: solo §9.2.0 + Fase A +
Fase B dry-run, sin activar `auto_fix`. Preflight (rollback, timer apt,
línea base) en verde antes de empezar.

**Completo y verificado:** Paso 0 (deploy por `git archive HEAD`,
migración real de las dos claves, validación real con `load_config()`,
sudoers/unidades instaladas, `sudo -n -l` confirmado como usuario
`doctorjk` real). Fase A (unidades sintéticas registradas, filler
calculado sin crear, stub de LLM y `memhog.py` creados y validados por
hash). B1 (kill -9 real a `doctorjk-test-svc`, detector confirmó en 2
ciclos, pipeline completo corrió con el stub, informe con `[DRY-RUN]`,
sin restart real).

**Se paró antes de B2**, por dos hallazgos en vivo, no anticipados en el
borrador:

1. `disco_pct = 5` disparó `disk_full` también en `/boot`, `/boot/efi` y
   `/sys/firmware/efi/efivars` (monitor.py evalúa todos los mount points,
   no solo `/`) — inofensivo pero no planeado. Ver nota en §9.2.1; queda
   como decisión pendiente antes de reintentar.
2. El backup de config.toml se tomaba ANTES de la migración de
   install.sh (bug real, ya corregido en §9.2.0 arriba): al restaurarlo
   para parar de forma segura, `doctorjk.service` entró en crash-loop real
   (`ConfigError`, 7 reinicios) por faltarle las dos claves nuevas.
   Corregido en el momento agregándolas a mano con su default fail-closed
   (mismo resultado que hubiera dado el backup correcto), verificado
   estable, y corregido en el protocolo para que no vuelva a pasar.

**Cleanup y salud final, verificados:** las 3 unidades de prueba
detenidas/removidas, los 4 informes espurios (3× `disk_full` de los mounts
de sistema + 1× `service_failed` de B1) borrados, temporales de `/tmp`
borrados, `config.toml.bak-gate44` (el backup con el bug) borrado. Estado
final idéntico a la línea base de §9.1: los 6 servicios activos, carga
0.01, disco 3%, memoria 8.9 GiB libres, sin swap, `config.toml` en
`modo_remediacion="diagnostico"`/`auto_fix=false`/`dry_run=true` con las
dos claves migradas en su default, sin unidades `doctorjk-test-*`
cargadas, sin marcadores en `/run`. Ningún incidente real se ejecutó,
ninguna llamada a Cloudflare, ningún `push`/`merge`.

**Hallazgo 1 resuelto (2026-09-01, commit `f3c556d`):** se agregó
`puntos_montaje_vigilados`/`monitored_mount_points` (default `["/"]`,
requerida, no vacía) y `normalize_snapshot()` ahora filtra por ella --
ver §9.2.1 para el detalle y el preflight que lo confirma. El hallazgo 2
(orden del backup) ya estaba resuelto en el protocolo antes de este
intento (§9.2.0).

**Pendiente antes de reintentar:** retomar desde B2 (los 4 dry-runs
directos no llegaron a correrse) con Fase A repetida desde cero (nada
quedó de pie para reusar). El código nuevo (allowlist de mounts,
migración de 3 claves, validación con `-I`) todavía no se probó en el VPS
real -- el próximo Paso 0 lo ejercita por primera vez ahí.

### 9.5 Segundo intento real en el VPS (2026-09-01) — Paso 0, Fase A y smoke test del filtro de mounts OK; parado en el primer script de B2

Ejecutado con punto de control explícito de MauItu: Paso 0 con HEAD nuevo
(commit `2dd0f73`), Fase A completa y B2 (los 4 dry-runs directos); B1 no se
repitió (ya estaba cubierto por el intento anterior), salvo un smoke test
mínimo del filtro de mounts nuevo. Preflight en verde: timer de
`apt-daily-upgrade` a 21h de distancia, rollback confirmado, línea base
idéntica a §9.1, sin unidades ni backups residuales del intento anterior.

**Completo y verificado:** Paso 0 (deploy por `git archive HEAD` con el
commit que agrega `puntos_montaje_vigilados`, migración agregó exactamente
esa clave -- las otras dos ya estaban de un intento previo --, `sudo -n -l`
confirma los 4 scripts, backup tomado DESPUÉS de la migración). Fase A
(unidades sintéticas activas, filler calculado sin crearlo, stub de LLM y
`memhog.py` transferidos y verificados por hash). **Smoke test del filtro de
mounts, la validación pendiente del hallazgo 1 de §9.4:** con
`puntos_montaje_vigilados = ["/"]` confirmado por el preflight de §9.2.1, se
bajó `disco_pct` a 5 y se esperaron >2 ciclos de monitor (25 s con
`intervalo_monitor_s=5`) -- cero incidentes `disk_full` sobre `/boot` o
`efivars` en la ventana. El filtro funciona en el VPS real, no solo en las
pruebas locales.

**Se paró en el primer script de B2** (`fix_servicio.sh`, llamado directo
en dry-run tras provocar `service_failed` con `kill -9` sobre
`doctorjk-test-svc`, reproduciendo solo la provocación de B1 sin repetir
todo su pipeline): el script falló con
`ERROR: /etc/doctorjk/config.toml tiene permisos de escritura demasiado
amplios (modo 640); no se confía` -- el modo exacto que `install.sh` pone
con `chmod 0640`. Hallazgo P0 nuevo, no anticipado: `comun.sh::
_verify_config_ownership` tenía un bug de aritmética -- `8#$mode` ya
convierte el string octal a un entero decimal, y aplicarle `/10 % 10` y
`% 10` después extrae los dígitos DECIMALES de ese entero, no los dígitos
OCTALES de `$mode`. Para modo 640 (`8#640` = decimal 416), `416 % 10 = 6`
trae el bit 2 encendido por pura coincidencia decimal, sin relación con el
bit real de "otros escribible" de 640 (que es 0). El resultado: **todo
Modo 2 fallaba cerrado en cualquier instalación correcta**, no solo en este
VPS -- reproducido de inmediato en local, sin ningún acceso al VPS, con un
`bash -c` aislado.

**Por qué ningún test local lo había atrapado antes:** `test_scripts_fix.py`
prueba los 4 `fix_*.sh` contra un DOBLE de `comun.sh` que no verifica
dueño/permisos en absoluto (documentado explícitamente en su propio
encabezado) -- la única cobertura que existía para
`_verify_config_ownership` era indirecta (`bash -n`, `shellcheck -x`,
revisión de código), y ninguna de esas tres ejecuta la aritmética. `bash -n`
valida sintaxis, no semántica.

**Corregido en el momento, en local, no en el VPS:** la condición ahora usa
una máscara octal directa sobre el valor ya convertido
(`(8#$mode & 8#020) || (8#$mode & 8#002)`), que además maneja
correctamente un cuarto dígito de setuid/sticky si `%a` lo trajera.
Cobertura nueva en `pruebas/unitarias/test_comun_permisos.py`: fuente el
`comun.sh` REAL (no un doble) con `stat` falseado por variables de entorno
para controlar dueño/modo sin necesitar root -- 640/600/444/4640/1644 deben
aceptarse, 660/642/666 deben rechazarse, dueño no-root debe rechazarse.
Confirmado que estas 9 pruebas fallan (5 de 9) contra el código viejo antes
de aplicar el fix, y pasan las 9 después. Suite completa: 297/297 (antes
288, +9). Búsqueda en todo el repo (`rg '8#\$'`) confirma que esta era la
única ocurrencia de este patrón.

**Cleanup y salud final, verificados:** unidades de prueba detenidas y sin
carga, `config.toml.bak-gate44` borrado, temporales de `/tmp` borrados, sin
informes espurios (la recolección de evidencia del `service_failed`
provocado para el smoke de B2 estaba programada para +1 min y el propio
restart de config del cierre la cortó antes de que escribiera nada -- se
verificó que el directorio de informes no tiene archivos nuevos). Estado
final idéntico a la línea base de §9.1. Ningún incidente real se ejecutó,
ninguna llamada a Cloudflare, ningún `push`/`merge`.

**Segunda P0 encontrada en local, sin volver al VPS, revisando qué seguía
en el camino de B2 después del fix de arriba:** `read_config_attr` en
`comun.sh` llamaba `load_config(sys.argv[1])` con el string crudo de
`argv` -- el mismo bug que `install.sh` ya había corregido en su propio
paso de validación (`load_config()` exige `Path` y llama
`path.read_bytes()`). Como los 4 `fix_*.sh` reales llaman a
`read_config_attr` para `dry_run` como mínimo (y cada uno además para su
propia allowlist), este bug habría reventado el primer script de B2 con
`AttributeError` apenas se hubiera corregido el hallazgo de
`_verify_config_ownership` -- el reintento en el VPS lo habría encontrado
de inmediato, un paso más adelante del mismo B2. Corregido con
`Path(sys.argv[1])` e `import Path`, mismo patrón que `install.sh`.
`rg 'load_config\('` confirma que era el único call site restante con un
`str` crudo (`main.py` y `install.sh` ya envolvían en `Path()`).
`test_comun_permisos.py` ahora también corre `read_config_attr` real
(intérprete real del venv del repo, vía `sys.executable`, no un doble)
contra un TOML completo y válido: `dry_run`, `disk_pct_threshold`,
`monitored_ports` y las tres listas nuevas de Gate 4/4.4
(`monitored_mount_points`, `approved_memory_unit`,
`approved_port_occupants`). Confirmadas las 6 fallando con el
`AttributeError` exacto contra el código viejo, pasando las 6 con el fix.
Suite completa: 303/303 (antes 297, +6).

**Cobertura de regresión agregada antes de un tercer intento (commit
`f0a61a7`):** `test_scripts_fix_integracion_real.py` corre los 4
`fix_*.sh` REALES contra el `comun.sh` REAL, un `config.toml` completo
real y el intérprete real del venv del repo -- solo se falsean `stat`
(root/640) y los comandos de sistema que cada script invoca
(`systemctl`/`ss`/`df`/`free`/`journalctl`/`sleep`). Cubre camino
exitoso, dry-run sin mutación e idempotencia para los 4 tipos de
incidente. Confirmado por mutación que estos 12 tests hubieran atrapado
los dos P0 de esta ronda: fallan los 12 contra el `comun.sh` original
(los dos bugs juntos), fallan los 12 contra el árbol de `cc05ef9` (solo
el bug de `Path` presente) y fallan los 12 con el chequeo octal
reintroducido en aislado (con el fix de `Path` puesto) -- cada caso con
el error exacto esperado. Aprovechado para extraer a `ayudantes.py`
(módulo de helpers ya existente en el repo, antes solo usado por
`test_monitor.py`) los dobles de comandos y el helper de instalación que
`test_scripts_fix.py` y `test_comun_permisos.py` ya duplicaban entre sí,
en vez de sumar una tercera copia. Suite completa: 315/315 (antes 303).

**Pendiente antes de reintentar:** los dos fixes de `comun.sh` de esta
ronda (aritmética octal + `Path()`) **todavía no se probaron juntos en
el VPS real** -- el próximo Paso 0 es la primera vez que se ejercitan ahí,
ahora con cobertura de regresión local que los habría atrapado a ambos.
Retomar desde B2 (ninguno de los 4 dry-runs directos llegó a completarse)
con Fase A repetida desde cero.

### 9.6 P0 de interacción entre señales, encontrado en revisión local antes del tercer intento

**Hallazgo:** `normalize_snapshot()` (`doctorjk/monitor.py`) emitía
`SERVICE_FAILED` para TODOS los `service_states`, sin importar el motivo de
la inactividad, y por separado `PORT_OCCUPIED` cuando el dueño esperado de
un puerto vigilado está `inactive` y otro proceso escucha ahí. Cuando las
dos condiciones coinciden en el mismo servicio -- el dueño cayó Y otro
proceso ya le tomó el puerto -- ambas señales cruzan en el mismo snapshot,
y con `servicio_ciclos`/`puerto_timeout_s` iguales (como en la Fase A de
este protocolo) ambos incidentes se confirman en el mismo ciclo. El
remediador dispararía `fix_servicio.sh` (reinicia al dueño) mientras el
puerto sigue tomado por el otro proceso -- el bind vuelve a fallar, falla o
ruido sin necesidad -- antes de que `fix_puerto.sh` llegara a liberar el
puerto.

**Corrección -- priorizar la señal específica:** se precalcula, antes del
bloque de servicios, qué servicios monitoreados están indebidamente
ocupados en su puerto vigilado en ESE snapshot puntual (mismo criterio que
`PORT_OCCUPIED`, calculado una sola vez y reutilizado en ambos bloques para
no duplicar lógica). `SERVICE_FAILED` se omite -- no se emite, ni sana ni
cruzada -- para esos servicios en ese snapshot: `PORT_OCCUPIED` ya es el
diagnóstico correcto y tiene su propio script (`fix_puerto.sh`).

**Por qué se omite en vez de forzar `crossed=False`:** `detector.py`
documenta explícitamente que una clave ausente en un ciclo "no se toca: ni
avanza ni se reinicia su contador" (`Detector.evaluate()`). Omitir es la
opción conservadora: no arriesga confirmar `SERVICE_FAILED` de más
(avanzando un contador que no debería avanzar) ni resolverlo de más
(un `crossed=False` forzado empujaría un `INCIDENT` ya confirmado hacia
`RESOLVED` sin que el servicio realmente esté sano, solo enmascarado por el
puerto ocupado). El estado de esa clave queda congelado mientras dura la
ocupación indebida, y se retoma normal en cuanto deja de estar
indebidamente ocupada.

**Por qué NO se suprime cuando nadie escucha (`PORT_DOWN`, no
`PORT_OCCUPIED`):** `PORT_DOWN` no tiene script de Modo 2 -- queda
`NOT_MAPPED` (`remediador.py::_skip()`) -- así que `fix_servicio.sh` sigue
siendo la única corrección automática posible para ese caso.
`SERVICE_FAILED` se conserva sin excepción cuando el puerto está caído,
libre o no vigilado.

**Trade-off documentado:** la supresión es específica al servicio, no un
apagado general de `SERVICE_FAILED` en el snapshot -- un servicio ajeno al
puerto ocupado (o incluso otro servicio vigilado, sin relación) sigue
emitiendo su propia señal sin tocar. Si más adelante `servicio_ciclos` y
`puerto_timeout_s` llegaran a tener persistencias muy distintas, la
ventana en la que una señal está confirmada y la otra todavía no podría
crecer -- no cambia la corrección (sigue siendo correcto priorizar
`PORT_OCCUPIED`), pero sí el tiempo que un cliente ve el incidente
diagnosticado antes de que el modo automático lo tome.

**Pruebas nuevas** (`pruebas/unitarias/test_normalizacion.py`): dueño
inactivo + otro proceso escuchando → solo `PORT_OCCUPIED` cruza, sin
`SERVICE_FAILED` para el dueño; dueño inactivo + nadie escucha → se
conservan `SERVICE_FAILED` y `PORT_DOWN`; un servicio ajeno al puerto
ocupado (`cron.service`, sin puerto vigilado propio) no se suprime aunque
otro servicio sí lo esté; recuperación del dueño → `SERVICE_FAILED` vuelve
a emitirse sano, lo que el detector necesita para poder resolver cualquier
candidato/incidente que hubiera quedado abierto sobre esa clave. Confirmado
por reversión que los dos primeros casos fallan contra el código viejo
(los otros dos no dependen del fix, sirven de cobertura de completitud, no
de regresión). Corregido de paso un test existente en `test_main.py`
(`test_dos_recursos_mantienen_estado_independiente`) que, sin saberlo,
modelaba exactamente este mismo escenario de interacción y esperaba 2
informes donde ahora corresponde 1 -- reescrito con dos servicios
genuinamente independientes (sin relación de puerto entre ellos), que es
lo que el test siempre quiso probar. Suite completa: 319/319 (antes 315).

**No probado en el VPS real todavía** -- se suma a los dos fixes de
`comun.sh` de §9.5 como parte de lo que el próximo Paso 0 ejercita por
primera vez ahí.

### 9.7 Tercer intento real en el VPS (2026-09-01) — Paso 0, Fase A y B2 completos; parado en el cleanup de `fix_puerto.sh` por un hallazgo nuevo

Ejecutado con punto de control explícito de MauItu: intento completo de
Paso 0 + Fase A + B2 dry-run (B1 no se repitió, solo el smoke mínimo de
provocar `doctorjk-test-svc` para la precondición de `fix_servicio.sh`).
Preflight en verde: timer de `apt-daily-upgrade` a 18h de distancia,
rollback confirmado, línea base idéntica a §9.1, sin unidades/backups
residuales de intentos anteriores.

**Completo y verificado -- primera vez en el VPS real para los tres fixes
de código de esta sesión (allowlist de mounts, aritmética octal de
`comun.sh`, `Path()` en `read_config_attr`):** Paso 0 (deploy, sin claves
nuevas que migrar -- ya estaban de la ronda anterior --, validación real,
backup post-migración). Fase A (unidades sintéticas, filtro de mounts
confirmado antes de bajar `disco_pct`). B2 completo hasta el cleanup de
`fix_puerto.sh`: `fix_servicio.sh` dry-run OK, `fix_disco.sh` dry-run OK
(listó 28 candidatos reales de `/var/log` sin tocar ninguno -- el hallazgo
que motivó §9.2.3bis), `fix_puerto.sh` dry-run OK. El `kill -9` de
`doctorjk-test-svc` disparó de paso el pipeline completo real (no
buscado, pero confirma que el smoke de B1 sigue sano): detectado
11:53:45, confirmado 11:53:51, informe generado 11:54:51 vía el stub, sin
mutación real. Evidencia capturada, informe borrado antes de la
restauración.

**Se paró en el cleanup de `fix_puerto.sh`** (`sudo systemctl restart
doctorjk-test-owner` tras el `stop` del mismo sub-paso): *"Unit
doctorjk-test-owner.service not found"*. Investigado en el momento (solo
lectura): el journal mostró un `stop` limpio (`Deactivated successfully` /
`Stopped`) seguido de la desaparición total de la unidad de
`systemctl list-unit-files` -- systemd la recolectó como transitoria pese
a haberse registrado sin `--collect`, contradiciendo lo que la versión
anterior de este protocolo daba por probado. `doctorjk-test-svc`, que en
ese momento seguía `failed` (nunca se detuvo limpio), no mostró el
problema -- la diferencia real es el `stop` limpio a `inactive`, no el
flag `--collect`. Detalle completo y la corrección (unidades reales bajo
`/run/systemd/system/`) en la tabla de §9.2.1.

**Restaurado y verificado:** config repuesta, `doctorjk.service`
reiniciado, unidades de prueba detenidas y limpias (incluida la unidad
`doctorjk-test-owner` ya recolectada, que no necesitó `rm` porque
literalmente no existía), sin filler/marcador/temporales, sin informes
espurios. Estado final idéntico a la línea base: 6 servicios reales +
`doctorjk`/`trigger` activos, carga ~0, disco 3%, memoria ~8.9 GiB
libres. Ningún push/merge, ninguna llamada a Cloudflare, ningún servicio
real tocado, ninguna Fase C ni D ejecutada.

**Segundo hallazgo, encontrado por revisión propia al escribir este
registro, no por ejecución en vivo:** B2 (`fix_disco.sh` en dry-run) listó
28 candidatos REALES bajo `/var/log` -- `nginx/`, `postgresql/`,
`auth.log`, etc. Inofensivo en dry-run, pero la Fase C corre el mismo
script con `dry_run=false`: sin aislar, habría borrado logs legítimos del
VPS compartido en el intento siguiente. Se revisó antes de que llegara a
ejecutarse, no después de un daño real.

**Corregido en el protocolo, ambos hallazgos, todavía no probado en el
VPS:**

1. `doctorjk-test-owner` y `doctorjk-test-svc` pasan a ser unidades reales
   efímeras bajo `/run/systemd/system/*.service` (§9.2.1) -- `stop`/`restart`
   se comportan como sobre un servicio de producción, sin ningún
   recolector de transitorias de por medio, y ningún script de Modo 2
   necesita recrear nada: prueban el mismo `systemctl restart` que corren
   en producción.
2. Aislamiento de `/var/log` y de `/run/log/journal` con un `BindPaths`
   efímero sobre `doctorjk.service` (§9.2.3bis), aprovechando el
   `ProtectSystem=strict` que la unidad ya tiene -- investigado y
   documentado ahí cómo decide `journald` entre almacenamiento persistente
   y volátil, y por qué aislar solo `/var/log` no alcanza. Verificación
   obligatoria vía `nsenter` al namespace real del proceso (no solo leer
   la config del drop-in) antes de autorizar la ejecución real de
   `fix_disco.sh`, con gate explícito: si no se puede confirmar el
   aislamiento, no se ejecuta ese escenario, se documenta como saltado, y
   se sigue con los otros tres. Ventana acotada al escenario (b) nada más
   (hallazgo propio, encontrado en revisión antes de correr nada:
   `recolector.py` llama `journalctl` para CUALQUIER incidente, así que
   dejar el aislamiento montado durante toda la Fase C habría roto la
   evidencia de los otros tres escenarios) -- se monta, se verifica, se
   usa y se retira dentro del propio sub-paso (b), con manifest hash de
   `/var/log` real antes/después verificado ahí mismo (fail fast), no
   diferido a la Fase E.

**Pendiente antes de un cuarto intento:** ninguno de los dos mecanismos
nuevos (unidades reales efímeras, aislamiento de `/var/log`/journal) se
probó todavía en el VPS -- el próximo Paso 0/Fase A los ejercita por
primera vez ahí. Retomar desde el cleanup de `fix_puerto.sh` en B2 (el
resto de B2, la transición a Fase C, y las Fases C/D/E completas no se
llegaron a correr) con Fase A repetida desde cero.
