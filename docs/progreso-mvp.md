# Progreso del MVP — traspaso

**Rama:** `gate-d/modo-1` · **Base:** `AIprototipo` (@MauItu) + corrección de Gate C
**Corte:** 2026-08-26 · **Suite:** 158 tests en verde

Este documento existe para que alguien retome sin leer el historial completo.
Dice qué está hecho, qué está **verificado contra el VPS real** y qué sigue
pendiente a propósito. Donde no hay medición, lo dice; no hay resultados
inventados (plan-mvp.md §4, regla 10).

---

## 1. Estado por gate

| Gate | Estado | Verificación |
|---|---|---|
| A — Base | Hecho por @MauItu | 105 tests |
| B — Detector | **Corriendo** | 24 h en el VPS, termina 2026-08-27 04:41 UTC |
| C — Evidencia y privacidad | **Cerrado** | Corpus real del VPS, 0 fugas |
| D — Modo 1 (hito alfa) | **Cerrado** | Incidente real en `beetle-vps` |
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

**Inmediato, cuando termine Gate B (2026-08-27 04:41 UTC):**

1. Contar incidentes declarados en `/opt/gate-b/gate-b.log`. Cualquiera es un
   falso positivo: el servidor estuvo sano toda la corrida.
2. **Dato para la evaluación:** se inyectaron 7 líneas en prioridad `warning`
   alrededor de las 04:43 UTC para armar el corpus de Gate C. Si el detector
   declaró un incidente por eso, es un falso positivo legítimo que hay que
   contar, no descontar.
3. Restaurar el VPS desde snapshot y cerrar Gate E con la instalación cronometrada.

**Antes de confiar en el Modo 1:** una llamada real al proveedor.

**Después:** Gate F (Modo 2 determinista) y Gate G. Recordar que **#203 dice
provocar la caída con `systemctl stop postgresql`, y eso no genera ningún
evento** — parar un servicio limpiamente no es un fallo. Hay que matar el
proceso. Está documentado en el comentario de #172.

---

## 7. Infraestructura del VPS

- **Gate B corriendo** desde `/opt/gate-b` (PIDs del agente y del trigger).
  Al terminar, borrar ese directorio.
- Snapshot vigente: `beetle-vps-2026-08-19-1641`, 1 de 5 del cupo gratuito.
- El despliegue automático solo sigue `main`; mientras esto viva en una rama,
  el VPS se queda en la última versión de `main`.
