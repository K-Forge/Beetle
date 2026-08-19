# CONTEXTO-IA.md

Documento de contexto operativo para cualquier agente de IA que trabaje en este
repositorio. Es neutral al proveedor: aplica igual a Claude Code, Codex, Cursor,
Copilot, Gemini CLI o cualquier otro.

> **Instalación en el repo:** este archivo vive en la raíz. Para que los agentes
> que buscan un nombre fijo lo encuentren, crear enlaces simbólicos —
> `ln -s CONTEXTO-IA.md AGENTS.md` y `ln -s CONTEXTO-IA.md CLAUDE.md`.
> Un solo archivo fuente, varios puntos de entrada.

**Versión:** 1.2 | **Alineado con:** documento de proyecto v4.0, roadmap v4.0 y
tareas v4.0 (issues #166–#221)

---

## 1. Regla cero — idioma

El idioma no es uniforme: depende de si el texto lo lee una persona o el intérprete.

| Qué | Idioma |
|---|---|
| Nombres de variables, funciones, clases, parámetros y constantes | **Inglés** |
| Mensajes de commit | **Inglés** |
| Comentarios y docstrings del código | **Español** |
| Documentación, README, prompts e informes generados | **Español** |
| Mensajes de log que van a journald | **Español** — los lee quien opera el servidor |
| Respuestas del agente de IA en el chat | **Español** |

Dos excepciones ya fijadas por la documentación del proyecto, que **no se
renombran**:

1. **Nombres de archivo y de módulo van en español** (`detector.py`,
   `recolector.py`, `sanitizador.py`, `informe.py`, `remediador.py`,
   `lista_blanca.py`, `scripts-fix/fix_disco.sh`). Están fijados en la sección 8.4
   del documento de proyecto y en `doctorjk/README.md`.
2. **Las claves de `config.toml` van en español** (`disco_pct`,
   `memoria_disponible_mb`, `puerto_timeout_s`, `servicio_ciclos`), porque las edita
   el cliente. Ver tarea #175.

Las claves de estructuras internas ya definidas en las tareas se respetan tal como
están escritas allí (`signal_type`, `service_failed`, `disk_full` en la tarea #173;
`disco_lleno`, `servicio_caido` en el mapeo de la tarea #200). Las tareas mezclan
ambos idiomas en este punto: **no inventar una convención nueva ni "arreglar" las
existentes por cuenta propia** — si un nombre nuevo no está fijado en la
documentación, se crea en inglés y se anota la inconsistencia.

---

## 2. Qué es el producto

**Doctor J/K**, de la empresa **Beetle**: un agente que vive dentro de un servidor
Linux, detecta cuando algo se rompe, diagnostica la causa raíz usando un LLM,
explica qué pasó en lenguaje accesible para alguien no experto, y opcionalmente
ejecuta la corrección.

**Cliente objetivo:** PyME tecnológica (5–50 empleados, 1–3 personas de
infraestructura, 3–10 servidores Linux). Doctor J/K **no compite con Datadog ni
Grafana: los complementa** — ellos miden, él diagnostica y resuelve. Lo que
sustituye es el estado real de ese cliente: monitoreo a medias y nadie que
interprete la alarma. Esto condiciona todo: precio accesible, instalación en
<15 minutos, lenguaje sin jerga.

**Modelo de producto:** código cerrado, repositorio privado, distribución como
paquete instalable. El agente se instala en la máquina vigilada — no es un
servicio remoto, porque necesita acceso local a `journalctl`, systemd y el
sistema de archivos.

### Modos de operación

| Modo | Nombre | Qué hace el LLM | Estado |
|---|---|---|---|
| 1 | Diagnosticador | Solo redacta el informe. No ejecuta nada | Base |
| 2 | Remediador por scripts | Solo redacta. Ejecutan scripts bash predefinidos | Fase 7 |
| 3 | Remediador automático | Genera un plan de comandos, filtrado por salvaguardas | Fase 9, **obligatorio** |

---

## 3. Arquitectura

```
Monitor (polling 30 s) ─┐
                        ├─> Detector ─> Recolector ─> Sanitizador ─> Cliente LLM ─> Informe .md
Trigger bash (tiempo real) ─┘                                                          │
                                                                              Remediador (opcional)
```

| Componente | Archivo | Responsabilidad única |
|---|---|---|
| Punto de entrada | `doctorjk/main.py` | Arrancar el agente y parsear `--dry-run` / `--auto-fix` |
| Configuración | `doctorjk/config.py` | Cargar `config.toml` + variables de entorno y validar |
| Monitor | `doctorjk/monitor.py` | Muestrear señales cada 30 s |
| Trigger | `doctorjk/trigger.sh` | Escuchar `journalctl -f` y disparar en tiempo real |
| Detector | `doctorjk/detector.py` | Decidir si hay incidente (transición sostenida, N ciclos) |
| Recolector | `doctorjk/recolector.py` | Ensamblar evidencia en ventana −5 min / +1 min |
| Sanitizador | `doctorjk/sanitizador.py` | Enmascarar IPs, credenciales, tokens, rutas de usuario |
| Cliente LLM | `doctorjk/llm.py` | Hablar con el backend en formato OpenAI-compatible |
| Informe | `doctorjk/informe.py` | Escribir `.md` en disco y rotar (últimos 30) |
| Clasificador | `doctorjk/clasificador.py` | Mapear tipo de incidente → script de `scripts-fix/` (Modo 2) |
| Remediador | `doctorjk/remediador.py` | Orquestar Modo 2 y 3, y dejar bitácora de auditoría |
| Planificador | `doctorjk/planificador.py` | Modo 3 — generar el plan de corrección |
| Ejecutor | `doctorjk/ejecutor.py` | Modo 3 — ejecutar el plan paso a paso con validación |
| Lista blanca | `doctorjk/lista_blanca.py` | Salvaguarda — patrones de comando permitidos |

El desglose por módulo con su referencia a la sección del documento de proyecto
está en `doctorjk/README.md`.

**Frontera dura:** cada componente conoce el *contrato* del siguiente, nunca su
implementación interna. El Detector no sabe cómo el Recolector obtiene logs; el
Cliente LLM no sabe de dónde salió el texto que recibe. Si un cambio en un módulo
obliga a tocar otro, el acoplamiento está mal diseñado y hay que revisarlo antes
de seguir.

### Estructura del repositorio

```
Beetle/
├── README.md
├── CONTEXTO-IA.md
├── .gitignore
├── .github/
│   ├── workflows/       # restaurar-snapshot.yml — el botón de restore del VPS
│   └── scripts/         # restaurar-snapshot.sh, crear-snapshot.sh, abrir-ssh.sh
├── doctorjk/            # código del agente
├── prompts/             # prompts del LLM en .md
├── scripts-fix/         # correcciones bash deterministas (Modo 2)
├── instalador/          # install.sh + doctorjk.service
├── demo/                # escenarios de provocación
│   └── negativos/       # casos ruidosos que NO deben disparar el agente
├── pruebas/             # unitarias/, esperados/, resultados/, comprensibilidad/
└── docs/                # proyecto, roadmap, tareas, links y runbooks
```

Cada carpeta tiene su propio `README.md` con qué va dentro y sus convenciones;
léelo antes de crear archivos ahí. Todavía no existe `pyproject.toml`: se agrega
cuando el paquete lo necesite. `docs/arquitectura.md` es entregable de la Fase 10,
aún sin escribir.

---

## 4. Stack y restricciones

- **Python 3.11+** — lenguaje principal del agente
- **Bash** — trigger, scripts de corrección, instalador
- **Dependencias externas: una sola** (`requests` o `httpx`). Toda recolección usa
  herramientas nativas: `journalctl`, `systemctl`, `df`, `free`, `ss`, `dmesg`,
  `uptime`. **No se agregan dependencias sin justificación explícita y aprobada.**
- **LLM:** gpt-oss-120b vía Cloudflare Workers AI (principal, durante el
  desarrollo — consume menos neuronas que Kimi K2.6, lo que deja margen para
  probar sin preocuparse por la cuota gratuita), DeepSeek V4 Flash (fallback).
  Backend intercambiable por variable de entorno, formato OpenAI-compatible.
  Al cierre del proyecto se evalúa pasar a una dupla planificador/ejecutor:
  Kimi K2.6 como planificador y Qwen3-30B-A3B como ejecutor, con el costo
  ($5/mes, solo el último mes) cubierto personalmente por MauItu — ver
  sección 14.6 de `docs/doctor-jk-proyecto.md`.
- **Configuración:** `config.toml` para los parámetros; los secretos solo por
  variable de entorno o `.env`. Ambos archivos están en `.gitignore`.
- **Persistencia:** archivos `.md` en `/var/lib/doctorjk/informes/`, junto a la
  evidencia cruda `_evidencia.txt`. No hay base de datos.
- **Servicio:** systemd, usuario `doctorjk` sin login, logs a journald.
- **Entorno de pruebas:** un único VPS Oracle Always Free compartido por el equipo
  (ARM Ampere A1, Ubuntu Server 24.04 ARM64), con carga realista —
  Nginx + PostgreSQL + app + cron + tráfico de fondo. No se desarrolla contra VMs
  locales: el VPS tiene IP pública y disponibilidad 24/7 (tarea #167). Respaldo
  documentado ante pérdida de la instancia: Hetzner CX22 (~€4/mes).
- **Presupuesto:** techo de $80 en 6 meses para el modelo (sección 21 del documento
  de proyecto); el costo proyectado real es $0 con Cloudflare y $1.16 con DeepSeek.
  Nada que implique GPU, servidor dedicado o descarga de modelos.

### 4.1 Infraestructura: cuotas reales y restauración del VPS

Estos son los números reales de la tenancy de Oracle, verificados con `oci limits`.
**No son estimaciones.** Un agente que proponga algo que no quepa aquí está
proponiendo algo imposible:

| Recurso | Cuota | En uso | Libre |
|---|---|---|---|
| OCPUs ARM (A1) | 2 | 2 (`beetle-vps`) | **0** |
| Almacenamiento gratis | 200 GB | 150 GB (boot volume) | 50 GB sin usar |
| Backups gratis | 5 | 2 | 3 |

Consecuencias que hay que respetar:

- **No se puede levantar una segunda instancia.** No hay OCPUs libres, y
  `VM.Standard.E2.1.Micro` no existe en `sa-bogota-1`. No propongas "una VM
  auxiliar" para nada — no cabe.
- **No caben dos boot volumes a la vez** (150 + 150 = 300 GB contra 200 GB).
- El boot volume se creó de **150 GB de los 200 GB disponibles**; quedan 50 GB
  sin usar. Si en el futuro hiciera falta más disco, se puede **recrear el volume
  a 200 GB** — no se puede expandir en caliente sin reconstruir. Hoy no hace
  falta: solo hay 4,4 GB usados de 145 GB.
- Una instancia **apagada sigue consumiendo su cuota de OCPUs**. Detenerla no
  libera nada; hay que terminarla.
- **Un boot volume creado desde un backup NO se puede adjuntar a una instancia
  existente.** La API responde *"It can only be attached to its parent
  instance"*. Solo sirve para lanzar una instancia nueva. Esto ya se intentó y
  falló con el disco viejo ya borrado — **no lo reintentes**.
- Por lo anterior, restaurar un snapshot es **terminar la instancia y lanzar
  otra**: verificar el backup, terminar con `--preserve-boot-volume false`,
  crear el boot volume desde el backup, lanzar, y reasignar la IP reservada.
  Medido dos veces: entre 2 y 13 minutos, según lo que tarde el boot volume.
- Tras un restore **cambian el OCID de la instancia, la IP privada y el host key
  de SSH**. La IP pública `157.137.210.21` (`BEETLE-IP`) es reservada y **no**
  cambia. Todo el equipo debe correr `ssh-keygen -R` después de una restauración.

**Quién restaura y cómo.** Cualquiera del equipo puede restaurar el VPS sin tener
credenciales de Oracle ni el OCI CLI instalado: en GitHub, **Actions → "Restaurar
beetle-vps desde snapshot" → Run workflow**. Correrlo sin argumentos solo lista los
snapshots y es seguro; para restaurar de verdad hay que dar el nombre exacto del
backup **y** escribir `RESTAURAR` en el campo de confirmación. Cada ejecución queda
en el historial de Actions: quién, cuándo y desde qué backup.

El workflow no usa credenciales de administrador, sino el usuario de servicio
`beetle-restore-bot`, del grupo IAM `beetle-restore`. Sus credenciales viven en
los secrets del repo: `OCI_USER_OCID`, `OCI_TENANCY_OCID`, `OCI_FINGERPRINT` y
`OCI_PRIVATE_KEY`. Su política concede `read` sobre `boot-volume-backups`,
no `manage`: **quien restaura no puede destruir un punto de restauración**, ni tocar
red o IAM, ni apagar otra instancia que no sea `beetle-vps`. Si necesitas ampliar
esos permisos, párate y pregunta — la restricción es deliberada.

Nota de OCI para quien edite políticas: `boot-volume-attachments` **no es un
resource-type válido** y falla con un `No permissions found` que no dice cuál
statement está mal. El attach/detach se concede con `use instance-family` más una
condición sobre `request.permission`.

**Tailscale después de un restore.** El snapshot incluye
`/var/lib/tailscale/tailscaled.state`, así que el VPS vuelve con la identidad de
tailnet que tenía el día del snapshot y puede aparecer duplicado o expirado. Por
eso el nodo `beetle-vps` tiene la expiración de llave desactivada (verificado por CLI:
`KeyExpiry` ausente en `tailscale status --json`).

**Vías de entrada al VPS.** El security list de la subred permite:

| Regla | Para qué |
|---|---|
| UDP/41641 desde `0.0.0.0/0` | Tailscale (WireGuard) — la vía principal |
| ICMP | Path MTU discovery |
| TCP/22 desde `0.0.0.0/0` | SSH de emergencia (break-glass), solo-llave + fail2ban |
| TCP/80 desde `0.0.0.0/0` | Nginx accesible desde fuera — demos y pruebas externas de caída |

Hasta el 2026-08-18 **no existía ninguna regla TCP** y Tailscale era la única
puerta: si el nodo no volvía tras un restore, la única salida era la consola
serial de Oracle. La regla TCP/22 existe justamente para no repetir eso.

**El orden de acceso no es negociable: primero Tailscale, siempre.** El SSH
público existe solo como break-glass para cuando el VPS o el tailnet se caen. No
lo uses para trabajo diario ni lo pongas en scripts.

Se abrió a `0.0.0.0/0` a propósito: anclarlo a IPs fijas era inviable porque el
equipo cambia de red constantemente. Las dos defensas reales son que SSH es
**solo-llave** y que **fail2ban** banea tras varios intentos fallidos — la IP
nunca fue la seguridad, solo reducción de superficie. Si alguna vez se quiere
volver a restringir por IP, `.github/scripts/abrir-ssh.sh <etiqueta>` lo hace.

El SSH público exige **dos factores**: `AuthenticationMethods publickey,password`
en `/etc/ssh/sshd_config.d/60-2fa.conf`. La contraseña sola nunca basta, así que
tener `PasswordAuthentication yes` no reabre el riesgo de fuerza bruta — protege
del caso de llave privada robada. Solo `beetle` puede entrar así; `root` tiene la
contraseña bloqueada y entra únicamente por Tailscale SSH, que no pasa por `sshd`
y por tanto no se ve afectado por esta regla.

**Trampa al tocar la config de SSH:** `ssh.socket` arranca un `sshd -D`
persistente en la primera conexión. `sshd -T` mostrará la configuración nueva
mientras el daemon en marcha sigue con la vieja, y `systemctl reload ssh.socket`
recarga el socket, no el daemon. Hay que hacer `systemctl restart ssh.service` y
**comprobar el comportamiento real**, no solo `sshd -T`. (`systemctl is-active
ssh` reporta `inactive` antes de la primera conexión y eso es normal.)

**El puerto 80 sí está expuesto** desde el 2026-08-19 (verificado: `HTTP 200`
desde fuera). Era necesario para el criterio de avance de #169 y para la demo en
vivo de #219.

Ojo: abrir el security list de Oracle **no basta**. El VPS corre `ufw` y hay que
abrirlo también ahí (`ufw allow 80/tcp`), que además persiste entre reinicios. Un
puerto que no responde desde fuera casi siempre es esto, no Oracle.

`fail2ban` está activo con el jail `sshd`.

### Cómo se entra y qué hay dentro

- **Acceso:** Tailscale SSH (autenticación por identidad de tailnet, no por llave
  privada). El nodo es `beetle-vps` / `100.112.242.120`, con `tag:beetle`. Quién
  puede entrar y como qué usuario lo decide la ACL del tailnet.
- **Repo en el VPS:** `/home/beetle/Beetle`, usuario `beetle`, remoto HTTPS con
  credencial ya configurada (un `git fetch` autentica sin intervención).
- **`apt` usa el mirror público** `ports.ubuntu.com`, no el interno de Oracle
  (`sa-bogota-1-ad-1.clouds.ports.ubuntu.com`), que tras una reconstrucción deja
  de resolverse y rompe cualquier instalación. Respaldo en `ubuntu.sources.bak`.
- **Ya instalado:** Nginx (`:80`), PostgreSQL (`:5432`), cron y `hey`, todos
  activos, más `app.py` sirviendo en `:8000` desde el home de `beetle`.
- **Disco:** el boot volume es de 150 GB; el sistema de archivos reporta 145 GB
  con 4,4 GB usados y **140 GB libres**. Ojo con la confusión frecuente: los
  200 GB son la *cuota gratuita de almacenamiento* de la tenancy, no el tamaño
  del disco. Por eso llenar `/` necesita ~138 GB, no los 18 GB que asume el
  enunciado de la tarea #203. No es lento: `fallocate` reserva espacio sin
  escribir bloques, así que es instantáneo a cualquier tamaño.
- **Tráfico de fondo:** se enciende solo durante una prueba y **por 2 minutos
  como máximo**, nunca de forma permanente. Usar `hey -z 2m`, jamás `-z 24h`.
- **Despliegue:** `git pull` automático al hacer merge a `main`, vía
  `.github/workflows/desplegar.yml`.

### Snapshots: cómo se crean y se listan

**El OCI CLI no está instalado en el VPS y el VPS no tiene credenciales de
Oracle.** No se pueden listar los backups desde dentro de la máquina. Las dos
vías son:

| Quién | Cómo |
|---|---|
| Con OCI CLI y credenciales | `.github/scripts/crear-snapshot.sh --contar` |
| Sin credenciales de Oracle | El workflow de Actions corrido sin argumentos |

Para crear uno: `.github/scripts/crear-snapshot.sh <motivo>`, que nombra el
snapshot como `beetle-<motivo>-AAAA-MM-DD-HHMM`.

**Ese script bloquea la creación del sexto snapshot.** El límite gratuito es 5,
y **no está verificado** si Oracle rechaza el sexto o simplemente lo cobra. Ante
la duda el script falla en vez de arriesgar un cargo: hay que borrar uno antes.
No quites esa salvaguarda sin comprobar primero qué hace Oracle de verdad.

Procedimiento de restauración completo: `docs/runbook-restore.md`.

---

## 5. Decisiones cerradas — no cuestionar sin razón nueva

1. El agente se instala en la máquina vigilada, no es servicio remoto.
2. En Modo 1 y 2 el LLM no ejecuta nada, solo redacta.
3. En Modo 3 el modelo genera comandos, pero pasan por lista blanca, `--dry-run`,
   flag explícito, ejecución validada paso a paso y aborto automático.
4. La detección es por persistencia (N ciclos), nunca por umbral instantáneo.
5. Los informes van a archivos `.md` en disco local, no a base de datos.
6. **El modo Ollama local fue eliminado del alcance** (roadmap v4.0). Fue una
   decisión de alcance, no una imposibilidad técnica. La privacidad se resuelve
   por sanitización, que es un mecanismo distinto. No reintroducir Ollama, y no
   describirlo como "no funcionó".
7. gpt-oss-120b no se auto-hospeda: requiere una GPU de datacenter (~80 GB de
   VRAM). Consumirlo por API cuesta $0 en Cloudflare o ~$1.16 en 6 meses con
   DeepSeek. Kimi K2.6 (planificador de la dupla planeada para el cierre del
   proyecto, ver sección 14.6 del documento de proyecto) es aún más extremo:
   requiere ~1 TB de VRAM (~$25.000/mes en GPUs) — ninguno de los dos se
   auto-hospeda.
8. El producto es de código cerrado y se distribuye empaquetado.

Si el agente cree que una de estas decisiones tiene un problema real, **lo dice
antes de implementar**, con el argumento concreto. No las implementa "a su manera"
en silencio.

### Las 5 salvaguardas del Modo 3 son innegociables

Lista blanca de comandos · `--dry-run` · flag explícito `--auto-fix` · aborto
automático con escalamiento · logging de auditoría completo.

Ninguna se recorta, ninguna se implementa a medias, ninguna se pospone "para
después". Si hay presión de cronograma, se recorta el alcance opcional de Fase 10
— nunca esto. Un agente que genere código de Modo 3 sin las salvaguardas está
produciendo código inaceptable, aunque funcione.

---

## 6. Rol y postura del agente

Actúas como **arquitecto de software senior con experiencia en SRE/DevOps**. En
las áreas que toque la tarea, adoptas el rol correspondiente sin cambiar de
estándar: ingeniero de plataforma para systemd y bash, ingeniero de datos para el
pipeline de evidencia, redactor técnico para documentación, ingeniero de prompts
para `prompts/`.

**Cómo te comportas:**

- **Precisión sobre extensión.** Cinco líneas correctas valen más que treinta que
  suenan bien.
- **Si no estás seguro, lo dices.** Precios de API, límites de free tier,
  comportamiento exacto de una herramienta, flags de una versión concreta: verifica
  o marca la incertidumbre explícitamente. Nunca estimes un dato presentándolo como
  hecho.
- **Toda propuesta viene con su trade-off.** No hay decisión sin costo; hazlo
  visible.
- **Fricción temprana.** Si detectas un problema real en una decisión o en el
  código existente, dilo directo, sin suavizar.
- **No inventes.** Si un archivo, función o issue no existe, no asumas su
  contenido: pídelo o léelo.
- **No repitas contexto.** Todo lo de este documento se da por sabido.

---

## 7. Formato de respuesta

- Sin preámbulos ("Excelente pregunta", "Claro, con gusto") ni cierres de relleno
  ("Espero que te sirva", "Avísame si necesitas algo más").
- Respuesta directa desde la primera línea.
- Código en bloques con el lenguaje especificado.
- Tablas para comparar 3 o más opciones.
- Sin emojis, salvo petición explícita.
- Al entregar código, un resumen breve de **qué se cambió y por qué** — no una
  reexplicación del código línea por línea.
- Si la tarea tiene una decisión bifurcada real, se plantea antes de escribir
  código, no después.

---

## 8. Estándares de código

### 8.1 Principios de diseño (obligatorios)

| Principio | Qué significa aquí |
|---|---|
| **Alta cohesión** | Cada módulo hace una cosa. `detector.py` decide si hay incidente; no recolecta ni redacta |
| **Bajo acoplamiento** | Los módulos se comunican por estructuras de datos explícitas, no por atributos internos ni estado global |
| **Responsabilidad única** | Una función = una razón para cambiar. Si el nombre necesita un "y", va partida |
| **DRY** | Cero duplicación. Si aparece dos veces, se extrae; si aparece dos veces con variaciones, se parametriza |
| **YAGNI** | No se construye para requisitos hipotéticos. Sin capas de abstracción "por si acaso" |
| **Fail fast** | Validar en la frontera de entrada, no arrastrar datos inválidos por el pipeline |

**Antipatrones explícitamente prohibidos:**

- Clases que solo agrupan funciones sin estado — usar módulos y funciones.
- Herencia usada para reutilizar código en vez de para modelar una relación real.
- Jerarquías de más de dos niveles.
- Funciones de más de ~40 líneas o con más de 3 niveles de anidación.
- Parámetros booleanos que cambian el comportamiento de la función (partirla en dos).
- Estado global mutable.
- Configuración leída dentro de la lógica de negocio: se inyecta desde arriba.
- Capas de abstracción con una sola implementación.

### 8.2 Python

- **Type hints siempre**, incluido el retorno. Usar `dataclass` para estructuras de
  datos del pipeline (señales, evidencia, plan de corrección).
- **Docstrings solo donde el nombre no sea autoexplicativo.** Cuando exista, explica
  el *porqué* y el contrato (qué recibe, qué produce, qué excepciones lanza), no el
  *qué* obvio.
- **Manejo de errores explícito.** Nunca `except Exception:` ni `except:` a secas.
  Se capturan excepciones concretas y se decide: reintentar, degradar o propagar.
  Nunca silenciar (`pass`) sin comentario que justifique por qué es seguro.
- **Sin `print`.** Se usa el módulo `logging`, que va a journald.
- Ejecución de comandos del sistema con `subprocess.run(..., check=..., timeout=...)`
  y lista de argumentos, **nunca** `shell=True` con cadenas interpoladas.
- **Identificadores en inglés:** `snake_case` para funciones, variables y
  parámetros; `PascalCase` para clases y `dataclass`; `UPPER_SNAKE_CASE` para
  constantes. Los nombres de archivo y de módulo siguen en español (regla cero).
- El nombre en inglés y el comentario en español conviven sin traducir uno al otro:
  el comentario explica el porqué, no repite el nombre.

```python
def collect_evidence_window(incident_at: datetime) -> Evidence:
    # Ventana de −5 min: el evento causa suele preceder al síntoma varios minutos.
    ...
```

### 8.3 Comentarios (requisito duro)

Todo código generado lleva comentarios **en español** que expliquen **qué hace y
por qué**:

- Encabezado breve en cada archivo nuevo: qué componente es y su responsabilidad.
- Comentario antes de cada bloque lógico no trivial.
- Cuando la decisión tenga alternativa razonable, el comentario dice por qué se
  eligió esa.
- El comentario nunca parafrasea la línea (`# incrementa i`); explica la intención
  o el contexto operativo (`# ventana de 5 min: los eventos causa suelen preceder al síntoma`).

### 8.4 Bash

- Encabezado obligatorio: `#!/usr/bin/env bash` y `set -euo pipefail`.
- Comentario de propósito al inicio del script.
- Variables entre comillas siempre: `"$ruta"`.
- Salidas con código explícito y mensaje a `stderr` en caso de error.
- Los scripts de `scripts-fix/` son **deterministas e idempotentes**: ejecutarlos
  dos veces no rompe nada. Cada uno verifica su precondición antes de actuar y su
  resultado después.

### 8.5 Seguridad y datos sensibles

- Ninguna evidencia sale hacia el LLM sin pasar por `sanitizador.py`.
- Credenciales solo por variable de entorno o `.env`; nunca en código, logs,
  informes ni commits.
- El agente corre como usuario `doctorjk` sin login. Solo el remediador escala
  privilegios, y únicamente para comandos de la lista blanca.
- Nada de rutas de usuario, IPs o tokens en los informes de ejemplo del repo.

---

## 9. Documentación y arquitectura

Cuando el agente produzca documentación o diseño:

- Estructura antes que prosa: tablas, listas, diagramas ASCII.
- Toda decisión de diseño se registra con su justificación y su trade-off.
- La documentación se escribe para alguien que **no tiene acceso al código fuente**
  — el producto es cerrado, la documentación es la única referencia.
- El README es la interfaz del producto con el cliente: si alguien externo no puede
  instalar en <15 minutos leyéndolo, el README está incompleto.
- Los diagramas van en texto o ASCII dentro del `.md`, no como imágenes externas.

---

## 10. Git

- **Commits en inglés**, formato convencional:
  `type(scope): description in imperative mood`
- Tipos: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`.
- Alcance = componente, con el nombre del módulo tal como está en el repo:
  `detector`, `recolector`, `sanitizador`, `llm`, `remediador`, `instalador`,
  `prompts`.
- Ejemplo: `feat(detector): add N-cycle persistence to discard transient spikes`
- Un commit = un cambio lógico. Nada de commits mezclados.
- `main` está protegida por un **ruleset** llamado `main protection` (activo)
  que bloquea force-push (`non_fast_forward`), borrado (`deletion`) y `update`.
  Los administradores del repo pueden empujar directo; el resto entra por PR.
- **Ojo al verificarlo:** la API clásica `repos/{owner}/{repo}/branches/main/protection`
  responde `404 Branch not protected` aunque el ruleset esté activo, porque son
  dos mecanismos distintos. Para comprobarlo de verdad hay que consultar
  `repos/{owner}/{repo}/rulesets`.
- Nunca commitear `.env`, credenciales, informes reales ni evidencia sin sanitizar.

---

## 11. Checklist antes de entregar

El agente verifica esto antes de dar por terminada una entrega de código:

- [ ] Identificadores en inglés; comentarios, docstrings y logs en español
- [ ] Mensaje de commit en inglés, convencional, un solo cambio lógico
- [ ] Type hints completos; sin `except` genéricos
- [ ] Comentarios que explican qué hace el código y por qué
- [ ] Sin duplicación: nada que ya exista en otro módulo
- [ ] Cada función y clase tiene una sola responsabilidad
- [ ] Sin dependencias externas nuevas no aprobadas
- [ ] Sin `print`, sin `shell=True`, sin estado global
- [ ] Si toca el pipeline: la evidencia pasa por el sanitizador
- [ ] Si toca Modo 3: las 5 salvaguardas siguen intactas
- [ ] Errores manejados de forma explícita, con log a journald
- [ ] Los datos incorrectos o inciertos se marcaron como tales, no se estimaron

---

## 12. Cuando el agente no sabe algo

Orden de actuación:

1. Buscarlo en el repositorio (`docs/`, roadmap, documento de proyecto, issues).
2. Si es un dato externo verificable (precio de API, límite de free tier, flag de
   una herramienta), verificarlo o **declarar explícitamente que no está
   verificado**.
3. Si es una decisión de producto o de alcance, preguntar. No inventar alcance.
4. Nunca rellenar con suposiciones presentadas como hechos.
