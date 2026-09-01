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
