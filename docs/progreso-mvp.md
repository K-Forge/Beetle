# Progreso del MVP — traspaso

**Rama:** `mvp/integracion-modo-1` · **Base:** `gate-d/modo-1` (@MauItu + corrección de Gate C)
**Corte:** 2026-08-31 · **Suite:** 158 tests en verde (heredados de `gate-d/modo-1`)

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
| B — Detector | **INVÁLIDA — sin Detector cableado** | Corrida iniciada 2026-08-26, seguía activa al 2026-08-31: 17.040 muestras, 0 transiciones, porque el ejecutable usó `on_snapshot=log_snapshot` y nunca instanció el Detector. Debe detenerse y archivarse como `INVALIDA_SIN_DETECTOR` (Gate 0.2 del plan), no repetirse hasta que el pipeline esté cableado |
| C — Evidencia y privacidad | Cerrado | Corpus real del VPS, 0 fugas |
| D — Modo 1 (hito alfa) | **Código escrito, NO integrado** | El pipeline (`pipeline.py`, `llm.py`, `informe.py`) funciona invocado directamente, pero `doctorjk/main.py` sigue construyendo la app con `on_snapshot=log_snapshot`: nunca corrió como el ejecutable real. No se puede llamar "cerrado" hasta completar Gate 2 del plan de finalización |
| E — Servicio e instalación | Parcial | Unidades validadas; instalación cronometrada pendiente |
| F–I | Sin empezar | — |

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

- **Gate B sigue corriendo** desde `/opt/gate-b` (PIDs del agente y del
  trigger), verificado por Tailscale el 2026-08-31. Debe detenerse con SIGTERM
  por PID exacto (no por patrón amplio), archivarse como corrida inválida y
  solo entonces limpiarse `/opt/gate-b` — ver Gate 0.2 del plan de finalización.
- No existen `/opt/doctorjk`, `/etc/doctorjk` ni `/var/lib/doctorjk`: el
  Modo 1 nunca se instaló de verdad en el VPS.
- Snapshot vigente: `beetle-vps-2026-08-19-1641`, 1 de 5 del cupo gratuito.
- El despliegue automático solo sigue `main`; mientras esto viva en una rama,
  el VPS se queda en la última versión de `main` (`6166bf9`), que solo tiene
  el trigger original.
