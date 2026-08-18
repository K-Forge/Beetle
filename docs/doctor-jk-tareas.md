# Doctor J/K — Beetle
## Tareas del Proyecto
**Versión 4.0 — Agosto 2026**

**Total:** 56 tareas activas (issues #166–#221)

---

## Fase 0 — Preparación

### #166 — Crear repositorio privado en GitHub

**Label:** `fase-0`

## Qué es esta tarea

Crear el repositorio privado en GitHub que albergará todo el código fuente de Doctor J/K. Privado porque el producto es de código cerrado (sección 23 del documento de proyecto) — el código nunca se publica.

## Qué se debe hacer

- Crear el repositorio en la organización con visibilidad **privada**
- Configurar la estructura de carpetas según la sección 8.4 del documento de proyecto: `doctorjk/`, `prompts/`, `scripts-fix/`, `instalador/`, `demo/`, `pruebas/`, `docs/`
- Crear `.gitignore` para Python (incluir `.env`, `__pycache__`, `*.pyc`, archivos de IDE)
- Escribir un README base con nombre del proyecto, descripción de una línea y estructura del repo
- Configurar branch protection en `main` (al menos requerir PR)

## Por qué importa

Es el primer paso de todo el proyecto — nada se puede versionar, compartir ni iterar sin el repositorio. La decisión de hacerlo privado viene del modelo de producto (sección 23): Doctor J/K se distribuye como paquete instalable, no como código fuente.

## Criterio de avance

Repositorio privado creado en GitHub, con la estructura de carpetas completa, `.gitignore` configurado y README base presente. Todos los miembros del equipo tienen acceso.

---

### #167 — Configurar VPS Oracle Always Free

**Label:** `fase-0`

## Qué es esta tarea

Configurar el VPS de Oracle Always Free que servirá como entorno de desarrollo y pruebas durante todo el proyecto. Es el servidor donde se instala, ejecuta y prueba Doctor J/K. La instancia pertenece a Brian; todos los miembros del equipo que necesiten operar en el servidor tendrán acceso SSH.

## Qué se debe hacer

- Crear una instancia ARM Ampere A1 en Oracle Always Free (si no existe)
- Instalar Ubuntu Server 24.04 LTS (ARM64)
- Configurar acceso SSH para Brian y Mauricio
- Verificar conectividad desde las máquinas de ambos
- Confirmar recursos disponibles (OCPU, RAM, disco) con los comandos correspondientes

## Por qué importa

Todo el desarrollo y las pruebas destructivas se ejecutan sobre este VPS. A diferencia de una VM local, el VPS tiene IP pública y está disponible 24/7 — permite pruebas de observación prolongada y demo en vivo sin depender de la máquina de un miembro del equipo.

## Criterio de avance

VPS accesible por SSH desde las máquinas de Brian y Mauricio, con Ubuntu Server 24.04 funcional. Recursos verificados con `free -m`, `df -h` y `nproc`.

---

### #168 — Snapshot de VPS limpio

**Label:** `fase-0`

## Qué es esta tarea

Tomar un snapshot del VPS recién configurado, antes de instalar carga realista ni modificar nada. Es el punto de restauración limpio al que se vuelve después de cada prueba destructiva.

## Qué se debe hacer

- Tomar un boot volume backup desde la consola de Oracle Cloud
- Nombrar el snapshot con fecha y descripción (ej: `base-limpia-2026-08-XX`)
- Probar la restauración: crear una instancia desde el backup y verificar que el VPS vuelve al estado exacto
- Documentar el procedimiento para que cualquier miembro del equipo pueda restaurar

## Por qué importa

Las pruebas de Fase 8 rompen el servidor intencionalmente (disco lleno, OOM, servicios caídos). Sin un snapshot de restauración rápida, cada prueba requeriría reinstalar el SO desde cero — horas en vez de minutos (sección 8.3 del documento de proyecto).

## Criterio de avance

El VPS puede restaurarse desde el snapshot. Documentar el tiempo real de restauración en Oracle (típicamente 5–15 minutos, no 60 segundos como una VM local).

---

### #169 — Instalar carga realista

**Label:** `fase-0`

## Qué es esta tarea

Instalar servicios reales en el VPS para que se parezca a un servidor de producción de una PyME. Sin carga realista, los logs están vacíos y los incidentes son triviales — el valor del detector está en encontrar la señal entre el ruido (sección 8.3 del documento de proyecto).

## Qué se debe hacer

- Instalar y configurar **Nginx** sirviendo una aplicación web mínima
- Instalar **PostgreSQL** y cargar una base de datos con ~50.000 filas
- Configurar un **cron job** que corra cada minuto (ej: limpieza, rotación, health check)
- Instalar una **app pequeña** (puede ser una API mínima en Python/Node que use la DB)
- Generar tráfico de fondo con `hey` o `wrk` para que los logs tengan contenido

## Por qué importa

El detector (Fase 2) necesita distinguir incidentes reales de picos normales de operación. Un servidor vacío no produce ruido — y sin ruido, no hay nada que distinguir. Esta carga simula el entorno real del buyer persona (Mateo, sección 2.1): 3–10 servidores Linux corriendo servicios web con bases de datos.

## Criterio de avance

Nginx responde en el puerto 80, PostgreSQL tiene ~50k filas consultables, el cron corre cada minuto, y `journalctl` muestra actividad real de múltiples servicios.

---

### #170 — Configurar Cloudflare

**Label:** `fase-0`

## Qué es esta tarea

Crear una cuenta en Cloudflare y obtener las credenciales necesarias para consumir gpt-oss-120b vía Workers AI. Es el backend principal de inferencia del proyecto durante el desarrollo — gratis y sin límite práctico para el volumen del prototipo.

## Qué se debe hacer

- Registrarse en dash.cloudflare.com (si no hay cuenta)
- Ir a AI → Workers AI → aceptar términos de servicio
- Ir a My Profile → API Tokens → crear token con permiso "Workers AI read/write"
- Copiar el Account ID (aparece en la página de Workers AI)
- Guardar ambos valores en un archivo `.env` en el VPS:
  ```
  DOCTORJK_LLM_BASE_URL=https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/v1
  DOCTORJK_LLM_MODEL=@cf/openai/gpt-oss-120b
  DOCTORJK_LLM_API_KEY=...
  ```
- Verificar con un curl de prueba que el token funciona

## Por qué importa

Cloudflare Workers AI con gpt-oss-120b es el motor principal de inferencia del proyecto durante el desarrollo — costo $0 (sección 10 del documento de proyecto) y consume menos neuronas de Workers AI que Kimi K2.6, lo que permite iterar y probar sin preocuparse por la cuota gratuita. Todo el pipeline de diagnóstico depende de esta conexión. Configurarlo mal bloquea las fases 3–9.

## Criterio de avance

Un curl desde el VPS hacia el endpoint de Cloudflare Workers AI devuelve una respuesta válida del modelo gpt-oss-120b.

---

## Fase 1 — Monitor + Trigger

### #171 — Monitor con polling

**Label:** `fase-1`

## Qué es esta tarea

Escribir el script Python que cada 30 segundos muestrea el estado del servidor: servicios, disco, memoria, puertos y carga. Es el primer mecanismo de vigilancia — la detección pasiva que alimenta al detector (Fase 2).

## Qué se debe hacer

- Crear `doctorjk/monitor.py`
- Implementar muestreo cada 30 segundos usando herramientas nativas del sistema:
  - Servicios: `systemctl list-units --failed --no-pager`
  - Disco: `df -h --output=source,pcent,target`
  - Memoria: `free -m`
  - Puertos: `ss -tlnp`
  - Carga: `uptime`
- Cada lectura produce un diccionario con timestamp y valores actuales
- El script debe correr en loop sin consumir más del 1% de CPU

## Por qué importa

Es uno de los dos mecanismos de detección del agente (sección 5.1 del documento de proyecto). El polling cada 30s cubre las condiciones sostenidas (disco llenándose, memoria bajando), mientras que el trigger bash (tarea siguiente) cubre los eventos puntuales. Sin el monitor, el detector no tiene datos para decidir.

## Criterio de avance

El script corre 1+ hora sin errores, produce lecturas coherentes y reproducibles, y no impacta el rendimiento del servidor (según el criterio de la Fase 1 en el roadmap).

---

### #172 — Trigger bash en tiempo real

**Label:** `fase-1`

## Qué es esta tarea

Escribir un script bash que escucha los logs del sistema en tiempo real y dispara el agente cuando detecta una línea de error relevante. Complementa al monitor por polling: el polling cubre condiciones sostenidas, el trigger cubre eventos puntuales e inmediatos.

## Qué se debe hacer

- Crear `doctorjk/trigger.sh`
- Escuchar `journalctl -f` filtrado por prioridad de error (`-p err`)
- Cuando aparece una línea relevante, ejecutar el agente inmediatamente
- Incluir filtro básico para ignorar errores conocidos e inofensivos
- El script debe correr como proceso de fondo junto al monitor

## Por qué importa

El polling tiene un delay inherente de hasta 30 segundos. Para errores puntuales (un servicio que muere, un OOM kill), 30 segundos es demasiado — la evidencia puede cambiar. El trigger bash detecta el error en tiempo real y dispara la recolección inmediatamente (sección 5.1 del documento de proyecto).

## Criterio de avance

Cuando se provoca un error (ej: `systemctl stop postgresql`), el trigger lo detecta en menos de 2 segundos y lanza el agente sin intervención manual.

---

### #173 — Normalizar señales

**Label:** `fase-1`

## Qué es esta tarea

Definir un formato de diccionario único al que se convierten todas las señales del monitor y del trigger, independientemente de su origen. Es la interfaz entre la capa de detección y el detector (Fase 2).

## Qué se debe hacer

- Definir la estructura del diccionario de señal:
  ```python
  {
      "timestamp": "2026-08-12T03:41:00Z",
      "signal_type": "service_failed",
      "value": "postgresql.service",
      "threshold": "active",
      "crossed": True
  }
  ```
- Implementar la conversión desde cada fuente (systemctl, df, free, ss, uptime, journalctl)
- Cada tipo de señal (`disk_full`, `memory_low`, `service_failed`, `port_down`, `high_load`) tiene su propio mapeo
- Validar que todas las señales se normalizan sin pérdida de información relevante

## Por qué importa

El detector (Fase 2) necesita una entrada uniforme para aplicar lógica de persistencia, umbrales y máquina de estados. Sin normalización, cada tipo de señal requeriría lógica ad hoc en el detector — más código, más bugs, más difícil de extender.

## Criterio de avance

Todas las lecturas del monitor y del trigger se convierten al diccionario normalizado. El detector puede consumirlas sin saber de qué fuente vinieron.

---

## Fase 2 — Detector

### #174 — Contadores de persistencia

**Label:** `fase-2`

## Qué es esta tarea

Implementar un contador por señal que confirma un incidente solo si la condición anómala persiste durante N ciclos consecutivos. Es el mecanismo central para distinguir un pico temporal de un problema real.

## Qué se debe hacer

- Mantener un contador por cada señal normalizada
- Incrementar el contador cada vez que la señal cruza el umbral
- Resetear el contador si la señal vuelve a la normalidad
- Confirmar incidente solo cuando el contador alcanza N (configurable, ej: 2 ciclos = 60s con polling de 30s)
- Exponer el estado del contador para logging y debugging

## Por qué importa

Sin persistencia, un `apt upgrade` que satura la memoria por 20 segundos dispararía una falsa alarma. La persistencia es lo que hace que el detector sea útil en un servidor real con tráfico (sección 5.1 del documento de proyecto). Es una de las 5 tareas de la Fase 2, que concentra el 80% del riesgo técnico del proyecto.

## Criterio de avance

Un pico temporal de una sola lectura NO dispara incidente. Una condición sostenida durante N ciclos SÍ lo dispara. Verificado con ambos escenarios en el VPS con carga.

---

### #175 — Umbrales configurables

**Label:** `fase-2`

## Qué es esta tarea

Crear un archivo de configuración donde se definen los umbrales que determinan cuándo una señal es anómala. Los valores por defecto cubren los escenarios comunes de una PyME, pero deben ser modificables sin tocar código.

## Qué se debe hacer

- Crear un archivo `config.toml` con los umbrales:
  ```toml
  [umbrales]
  disco_pct = 90          # dispara si uso > 90%
  memoria_disponible_mb = 400  # dispara si disponible < 400 MB
  puerto_timeout_s = 60   # dispara si puerto no escucha > 60s
  servicio_ciclos = 2     # ciclos consecutivos para confirmar
  ```
- Implementar la lectura del archivo en `config.py`
- Los umbrales se cargan al inicio y se usan en el detector
- Si el archivo no existe, usar valores por defecto razonables

## Por qué importa

Cada servidor tiene necesidades distintas. Un servidor con 2 GB de RAM necesita un umbral de memoria diferente a uno con 16 GB. La configurabilidad por TOML permite que el cliente (PyME) ajuste sin tocar código — coherente con la meta de instalación en <15 minutos (sección 2.2 del documento de proyecto).

## Criterio de avance

El detector respeta los umbrales del archivo TOML. Cambiar un valor en el archivo cambia el comportamiento del detector sin reiniciar el servicio (o con un reinicio limpio).

---

### #176 — Máquina de estados

**Label:** `fase-2`

## Qué es esta tarea

Implementar la máquina de estados que modela el ciclo de vida de un incidente: desde la normalidad hasta la resolución. Es la lógica central del detector que gobierna cuándo se dispara y cuándo se cierra un incidente.

## Qué se debe hacer

- Implementar las transiciones de estado:
  ```
  normal → candidato → incidente → resuelto → normal
  ```
- **normal → candidato**: señal cruza umbral por primera vez
- **candidato → incidente**: señal persiste N ciclos (contadores de persistencia)
- **candidato → normal**: señal vuelve bajo umbral antes de N ciclos (pico temporal, se ignora)
- **incidente → resuelto**: señal vuelve a la normalidad
- **resuelto → normal**: después de un periodo de enfriamiento
- Registrar cada transición con timestamp

## Por qué importa

Sin máquina de estados, el detector no distingue entre un pico temporal (candidato que vuelve a normal) y un incidente real (candidato que persiste). Además, previene re-disparos: un incidente activo no puede volver a dispararse hasta que se resuelva (sección 5.1, sección 17.4 del documento de proyecto).

## Criterio de avance

Las 4 transiciones funcionan correctamente. Un pico de <N ciclos se descarta como candidato. Un incidente confirmado pasa a resuelto solo cuando la condición se normaliza. Probado con los 4 escenarios básicos.

---

### #177 — Deduplicación

**Label:** `fase-2`

## Qué es esta tarea

Implementar la lógica que impide que un incidente activo vuelva a disparar el pipeline de diagnóstico. Mientras un incidente de disco lleno esté en estado "incidente", no debe generarse un segundo informe por el mismo problema.

## Qué se debe hacer

- Mantener un registro de incidentes activos (tipo + recurso)
- Antes de confirmar un nuevo incidente, verificar que no hay uno activo del mismo tipo y recurso
- Solo permitir re-disparo cuando el incidente anterior pase a "resuelto"
- Registrar en log cuando se suprime un disparo duplicado

## Por qué importa

Sin deduplicación, un disco al 95% generaría un informe nuevo cada 60 segundos (2 ciclos de polling). Eso saturaría los tokens del LLM, llenaría el disco de informes repetidos y haría inútil el sistema. La deduplicación es lo que permite que el agente corra 24/7 sin intervención (sección 5.1 del documento de proyecto).

## Criterio de avance

Un incidente activo de disco lleno no genera un segundo informe aunque la condición persista. Cuando el disco se libera y vuelve a llenarse, sí se genera un nuevo informe.

---

### #178 — Registro de decisiones

**Label:** `fase-2`

## Qué es esta tarea

Registrar en un log estructurado la razón por la cual el detector tomó cada decisión: por qué disparó un incidente, por qué lo descartó como pico temporal, por qué lo suprimió por deduplicación. Es la trazabilidad del detector.

## Qué se debe hacer

- Para cada ciclo de evaluación, registrar:
  - Señales recibidas y sus valores
  - Estado actual de cada contador de persistencia
  - Decisión tomada (ignorar / marcar candidato / confirmar incidente / suprimir duplicado)
  - Razón de la decisión en texto legible
- Usar el módulo `logging` de Python con salida a journald
- Nivel INFO para decisiones normales, WARNING para incidentes confirmados

## Por qué importa

Cuando el detector falla (falso positivo o falso negativo), el registro de decisiones es lo que permite diagnosticar el bug. Sin él, depurar la lógica de detección requiere adivinar. Es especialmente crítico porque la Fase 2 concentra el 80% del riesgo técnico del proyecto (roadmap, sección de dependencias).

## Criterio de avance

Cada decisión del detector (disparar, descartar, suprimir) queda registrada en journald con timestamp, señales involucradas y razón. Se puede consultar con `journalctl -u doctorjk` y reconstruir la secuencia de decisiones.

---

## Fase 3 — Recolector + Sanitización

### #179 — Recorte de ventana temporal

**Label:** `fase-3`

## Qué es esta tarea

Cuando el detector confirma un incidente en t=0, el recolector debe obtener los logs del sistema en una ventana temporal de −5 minutos a +1 minuto alrededor del evento. Este recorte limita el volumen de datos y captura la cronología relevante.

## Qué se debe hacer

- Calcular los timestamps de inicio (t-5min) y fin (t+1min) a partir del momento de detección
- Ejecutar `journalctl --since "..." --until "..." -p warning` con esos timestamps
- Capturar la salida como texto para pasarla al ensamblado de evidencia
- Si la ventana produce más de ~200 líneas, truncar por el extremo más antiguo

## Por qué importa

Enviar todos los logs del servidor sería demasiado (miles de líneas, decenas de miles de tokens). Enviar solo la última línea de error perdería el contexto. La ventana de −5 a +1 minutos captura la cronología del incidente — qué pasó antes y qué pasó justo después (sección 5.2 del documento de proyecto).

## Criterio de avance

Los logs recolectados cubren exactamente la ventana temporal definida. No se incluyen logs fuera de la ventana. El volumen es manejable (~200 líneas o menos).

---

### #180 — Filtrado por prioridad

**Label:** `fase-3`

## Qué es esta tarea

Filtrar los logs recolectados para quedarse solo con mensajes de prioridad warning o superior, descartando info y debug. Reduce el volumen de tokens enviados al modelo sin perder información relevante para el diagnóstico.

## Qué se debe hacer

- Aplicar filtro de prioridad en la llamada a journalctl: `-p warning` (incluye warning, err, crit, alert, emerg)
- Si se recolectan logs de otras fuentes (archivos de aplicación), aplicar filtro equivalente
- Verificar que no se pierden líneas de error relevantes por el filtrado

## Por qué importa

Los mensajes de nivel info y debug son la mayoría del volumen de logs pero rara vez contienen información sobre la causa de un incidente. Filtrarlos reduce el tamaño de la evidencia (objetivo: <12k tokens total, sección del criterio de Fase 3 en el roadmap) y mejora la relación señal-ruido para el modelo.

## Criterio de avance

Los logs recolectados no contienen mensajes de nivel info o debug. Los mensajes de warning y superiores sí aparecen completos. El volumen se reduce al menos un 50% comparado con sin filtro.

---

### #181 — Ensamblado de evidencia

**Label:** `fase-3`

## Qué es esta tarea

Armar el bloque de evidencia completo que se enviará al modelo: un documento estructurado con secciones etiquetadas que contiene toda la información que el modelo necesita para diagnosticar el incidente.

## Qué se debe hacer

- Ensamblar un bloque con 5 secciones etiquetadas (sección 5.2 del documento de proyecto):
  1. **Metadatos**: hostname, timestamp del incidente, tipo de incidente detectado
  2. **Logs**: journalctl de la ventana temporal, filtrado por prioridad
  3. **Snapshot**: servicios fallidos (`systemctl`), disco (`df`), memoria (`free`), puertos (`ss`), carga (`uptime`)
  4. **Cambios recientes**: paquetes instalados/actualizados en 48h, configs modificadas en `/etc`
  5. **Historial**: incidentes anteriores de esta máquina (si hay informes previos)
- Cada sección tiene un encabezado claro para que el modelo las identifique
- El formato de salida es texto plano estructurado

## Por qué importa

La calidad del diagnóstico depende directamente de la calidad de la evidencia. Un LLM con evidencia incompleta produce un informe incompleto; con evidencia desordenada, pierde correlaciones. Las 5 secciones le dan al modelo toda la información que un sysadmin consultaría manualmente — en un formato que puede procesar en segundos.

## Criterio de avance

El bloque de evidencia ensamblado contiene las 5 secciones, correctamente etiquetadas, con datos reales del servidor. El bloque completo pesa menos de 12k tokens.

---

### #182 — Truncado inteligente

**Label:** `fase-3`

## Qué es esta tarea

Si la evidencia ensamblada supera el presupuesto de ~10k tokens, cortar contenido de forma inteligente: primero los logs más antiguos de la ventana, manteniendo siempre la sección que contiene el error y los metadatos.

## Qué se debe hacer

- Estimar el tamaño en tokens del bloque de evidencia (1 token ≈ 4 caracteres como heurística)
- Si supera ~10k tokens, aplicar truncado en este orden de prioridad:
  1. Recortar logs más antiguos de la ventana (los de t-5min), manteniendo los cercanos al error
  2. Reducir el snapshot a las métricas anómalas solamente
  3. Nunca recortar metadatos ni la sección de error
- Añadir una nota `[TRUNCADO: se recortaron N líneas de logs antiguos]` donde se hizo el corte

## Por qué importa

Los modelos tienen límite de contexto y el costo de inferencia escala con tokens. gpt-oss-120b vía Cloudflare tiene un límite práctico. Además, evidencia demasiado larga diluye la señal — el modelo puede confundirse con información irrelevante. El truncado mantiene la calidad del diagnóstico dentro del presupuesto de tokens (sección 5.2 del documento de proyecto).

## Criterio de avance

Una evidencia de 15k tokens se trunca a ~10k tokens sin perder la sección de error ni los metadatos. La nota de truncado indica cuánto se recortó.

---

### #183 — Guardar evidencia cruda

**Label:** `fase-3`

## Qué es esta tarea

Guardar la evidencia completa sin sanitizar en un archivo local junto a cada informe. Es la versión "cruda" que el administrador puede inspeccionar para ver exactamente qué datos se recolectaron y qué se envió al modelo (después de sanitizar).

## Qué se debe hacer

- Después de ensamblar la evidencia y antes de sanitizar, guardar una copia en `/var/lib/doctorjk/informes/` con nombre `{timestamp}_{tipo}_evidencia.txt`
- El archivo contiene la evidencia completa con IPs reales, rutas reales, credenciales si aparecen
- No aplicar ningún enmascaramiento a esta copia
- El archivo queda en disco local, nunca se envía al LLM ni sale del servidor

## Por qué importa

El administrador necesita poder auditar qué datos tiene el agente: comparar la evidencia cruda contra la sanitizada para verificar que la sanitización funciona, o usar los datos reales para su propia investigación. Es transparencia operativa, clave para la confianza del cliente que desconfía de cajas negras (sección 23 del documento de proyecto).

## Criterio de avance

Junto a cada informe generado, existe un archivo `_evidencia.txt` con los datos sin sanitizar. El archivo contiene IPs y rutas reales. Verificar que NO se envía al LLM.

---

### #184 — Módulo sanitizador

**Label:** `fase-3`

## Qué es esta tarea

Crear el módulo `sanitizador.py` que se interpone entre el recolector y el cliente LLM para enmascarar datos sensibles antes de que la evidencia salga del servidor. Es la pieza central de la protección de privacidad del producto.

## Qué se debe hacer

- Crear `doctorjk/sanitizador.py` con las siguientes reglas de enmascaramiento (sección 5.3 del documento de proyecto):
  | Patrón | Reemplazo |
  |--------|-----------|
  | Direcciones IP | `[IP_1]`, `[IP_2]` (consistente: la misma IP siempre es el mismo placeholder) |
  | Variables con PASSWORD, SECRET, KEY, TOKEN | `[REDACTADO]` |
  | Tokens Bearer / JWT | `[TOKEN_REDACTADO]` |
  | Rutas `/home/usuario/...` | `/home/[USUARIO]/...` |
  | Claves SSH | `[REDACTADO]` |
- Usar expresiones regulares del módulo `re` (sin dependencias externas)
- Mantener consistencia dentro de un mismo informe: la misma IP siempre mapea al mismo placeholder

## Por qué importa

Los logs contienen IPs internas, rutas con nombres de usuario y a veces credenciales. Sin sanitización, esos datos viajan por internet hasta Cloudflare. El buyer persona (Mateo, sección 2.1) pregunta explícitamente: "¿Esto manda mis logs a algún lado?" — el sanitizador es la respuesta.

## Criterio de avance

Ninguna IP, credencial, token ni ruta con nombre de usuario aparece en la evidencia enviada al LLM. La consistencia del reemplazo dentro del mismo informe permite al modelo correlacionar eventos ("`[IP_1]` fue rechazada tres veces").

---

### #185 — Pruebas del sanitizador

**Label:** `fase-3`

## Qué es esta tarea

Escribir pruebas para el sanitizador que verifiquen que funciona correctamente, incluyendo casos límite, y documentar honestamente qué NO cubre.

## Qué se debe hacer

- Escribir tests con pytest que cubran:
  - IPs en distintos formatos (IPv4 con puerto, en URLs, en logs de nginx)
  - Consistencia: la misma IP produce el mismo placeholder en todo el informe
  - Variables con credenciales en distintos formatos (`PASSWORD=...`, `export SECRET_KEY=...`)
  - Tokens JWT y Bearer en headers
  - Rutas `/home/` con distintos nombres de usuario
  - Claves SSH (formato OpenSSH)
- Probar casos límite: IPs dentro de URLs, credenciales multilínea, formatos inesperados
- Crear un documento `docs/sanitizador_limitaciones.md` con lo que NO cubre (ej: datos en formato binario, credenciales sin keyword, etc.)

## Por qué importa

La sanitización por patrones no es exhaustiva — el documento de proyecto lo dice explícitamente (sección 5.3): "Un dato sensible con formato inesperado puede escaparse." Las pruebas verifican los casos cubiertos, y la documentación de limitaciones es transparencia honesta con el equipo y el cliente.

## Criterio de avance

Tests pasan al 100% para los patrones definidos. La misma IP siempre produce el mismo placeholder. Documento de limitaciones escrito con al menos 3 escenarios que el sanitizador NO cubre.

---

## Fase 4 — Cliente LLM

### #186 — Cliente OpenAI-compatible

**Label:** `fase-4`

## Qué es esta tarea

Implementar el cliente HTTP que envía la evidencia sanitizada al proveedor de LLM usando el formato OpenAI-compatible. Es la pieza que conecta la recolección con el diagnóstico — un POST con la evidencia, un response con el informe.

## Qué se debe hacer

- Crear `doctorjk/llm.py`
- Implementar POST a `/v1/chat/completions` con:
  - Headers de autenticación (`Authorization: Bearer ...`)
  - Body con `model`, `messages` (system + user)
  - Timeout de 30 segundos
- Leer base URL, modelo y API key desde variables de entorno
- Parsear la respuesta y extraer el contenido del mensaje
- Usar `requests` o `httpx` como única dependencia externa

## Por qué importa

El diseño OpenAI-compatible es deliberado (sección 5.5 del documento de proyecto): permite cambiar de proveedor con solo cambiar 3 variables de entorno. Cloudflare, DeepSeek y la mayoría de proveedores hablan este formato. Un cliente bien diseñado aquí hace que el agente sea agnóstico del modelo.

## Criterio de avance

El cliente envía evidencia al endpoint de Cloudflare Workers AI y recibe un diagnóstico válido de gpt-oss-120b. Cambiar las 3 variables de entorno a DeepSeek produce el mismo resultado sin cambiar código.

---

### #187 — Manejo de errores

**Label:** `fase-4`

## Qué es esta tarea

Implementar el manejo de los tres errores principales del cliente LLM: timeouts, rate limits y respuestas vacías o malformadas.

## Qué se debe hacer

- **Timeout**: si la respuesta tarda más de 30 segundos, abortar la petición
- **Rate limit**: detectar respuesta HTTP 429, esperar el tiempo indicado en `Retry-After` o aplicar backoff
- **Respuesta vacía/malformada**: si el body no contiene el campo esperado (`choices[0].message.content`), tratar como error recuperable
- En todos los casos, registrar el error en log con detalles suficientes para diagnosticar

## Por qué importa

El agente corre 24/7 sin supervisión (sección 4 del documento de proyecto). Una petición que se queda colgada, un rate limit no manejado o un JSON inesperado no pueden crashear el proceso. El manejo de errores es lo que separa un script de prueba de un servicio de producción.

## Criterio de avance

El cliente sobrevive a un timeout (no se queda colgado), a un rate limit (espera y reintenta), y a una respuesta vacía (registra y pasa al fallback). Probado con mocks o provocando cada escenario.

---

### #188 — Reintentos con backoff

**Label:** `fase-4`

## Qué es esta tarea

Implementar reintentos con backoff exponencial para las peticiones al LLM que fallan de forma transitoria.

## Qué se debe hacer

- Reintentar en caso de: timeout, error 5xx, error de conexión, rate limit (429)
- Backoff exponencial: 1s → 2s → 4s entre intentos
- Máximo 3 intentos totales
- Si los 3 intentos fallan, pasar al fallback sin LLM (tarea #190)
- Registrar cada reintento en log con el número de intento y la razón

## Por qué importa

Los proveedores de LLM tienen fallos transitorios: picos de carga, mantenimiento breve, latencia variable. Un solo intento fallido a las 3am no debería dejar al agente sin diagnóstico. El backoff exponencial es el patrón estándar para manejar esto sin saturar al proveedor (sección del roadmap, Fase 4).

## Criterio de avance

Una petición que falla 2 veces y funciona a la tercera produce un informe normal. Los tiempos entre reintentos crecen exponencialmente (1s, 2s, 4s). Si las 3 fallan, se activa el fallback.

---

### #189 — Modo caché

**Label:** `fase-4`

## Qué es esta tarea

Implementar un modo caché para desarrollo que reutiliza respuestas anteriores del LLM en lugar de hacer peticiones reales. Evita gastar tokens y tiempo de espera durante la iteración del código.

## Qué se debe hacer

- Añadir un flag de configuración `DOCTORJK_CACHE=true` (variable de entorno o TOML)
- Cuando está activo, guardar cada respuesta del LLM en disco (ej: hash de la evidencia → respuesta)
- En peticiones posteriores con la misma evidencia, devolver la respuesta cacheada
- Nunca activar en producción — el flag debe ser explícito y documentado como solo-desarrollo
- Registrar en log cuando se usa una respuesta cacheada vs. una real

## Por qué importa

Durante el desarrollo de las fases 5 (prompt) y 8 (pruebas), se ejecutan decenas de pruebas con la misma evidencia. Sin caché, cada iteración del prompt cuesta tokens y 10–15 segundos de espera. Con caché, el ciclo de desarrollo es instantáneo. gpt-oss-120b es gratis y consume pocas neuronas de Workers AI, pero sigue teniendo latencia — el caché acelera la iteración.

## Criterio de avance

Con `DOCTORJK_CACHE=true`, la segunda ejecución con la misma evidencia devuelve la respuesta instantáneamente sin hacer petición HTTP. Con el flag desactivado, siempre se hace la petición real.

---

### #190 — Fallback sin LLM

**Label:** `fase-4`

## Qué es esta tarea

Si el modelo no responde después de agotar los reintentos, generar un informe mínimo con la evidencia cruda etiquetada — no el diagnóstico inteligente, pero sí algo útil que el administrador puede leer.

## Qué se debe hacer

- Detectar que los 3 reintentos fallaron
- Generar un informe con formato similar al normal pero con:
  - Título: "Informe de incidente — SIN DIAGNÓSTICO IA"
  - La evidencia cruda organizada por secciones (metadatos, logs, snapshot)
  - Una nota: "El modelo de IA no respondió. Se presenta la evidencia recolectada sin análisis."
- Guardar el informe en la misma ruta que los normales
- Registrar en log que se activó el fallback y por qué

## Por qué importa

El agente no puede quedarse en silencio ante un incidente solo porque el LLM no respondió. Un informe sin diagnóstico inteligente sigue siendo mejor que nada — el administrador tiene la evidencia recolectada y organizada, solo sin la interpretación del modelo. El riesgo de falla de red ya está documentado (sección 18 del documento de proyecto).

## Criterio de avance

Con el LLM inaccesible, el agente genera un informe con la evidencia cruda etiquetada. El informe se guarda en disco. El sistema no crashea ni se queda colgado.

---

## Fase 5 — Prompt

### #191 — Prompt estructurado

**Label:** `fase-5`

## Qué es esta tarea

Diseñar el prompt del diagnosticador: el texto que le dice al modelo quién es, qué reglas sigue, y en qué formato debe producir el informe. Es la pieza que transforma evidencia cruda en diagnóstico comprensible.

## Qué se debe hacer

- Crear `prompts/diagnosticador.md` siguiendo la estructura de la sección 12 del documento de proyecto:
  - **Rol**: diagnosticador experto de servidores Linux, escribe para personas no técnicas
  - **Reglas**: no inventar información, marcar confianza, no sugerir comandos destructivos, explicar cada concepto técnico
  - **Estructura de salida** — Bloque 1 (Diagnóstico): Resumen, Cronología, Causa raíz con confianza, Descartado
  - **Estructura de salida** — Bloque 2 (Guía): Confirmar, Resolver paso a paso, Verificar, Prevenir
- El prompt debe funcionar con datos sanitizados (`[IP_1]`, `[REDACTADO]`)
- Escribir en español, segunda persona

## Por qué importa

El prompt es el diferenciador entre un volcado de datos y un diagnóstico útil. El documento de proyecto dedica toda la sección 12 a su diseño porque la promesa central del producto es que "cualquier persona entienda qué pasó" (sección 2). Un buen prompt produce informes como el ejemplo de la sección 13.

## Criterio de avance

El prompt produce informes con las 8 secciones definidas (4 de diagnóstico + 4 de guía). El lenguaje es comprensible para personas no técnicas. El formato es consistente entre diferentes tipos de incidente.

---

### #192 — Iteración con escenarios

**Label:** `fase-5`

## Qué es esta tarea

Probar el prompt contra la evidencia guardada de cada escenario de prueba y ajustar la redacción iterativamente hasta que los informes sean precisos, comprensibles y consistentes.

## Qué se debe hacer

- Recolectar y guardar evidencia de al menos los 4 escenarios básicos: servicio caído, disco lleno, memoria agotada, puerto ocupado
- Ejecutar el prompt contra cada evidencia guardada
- Evaluar cada informe en:
  - ¿Identifica la causa raíz correctamente?
  - ¿Los pasos de solución resolverían el problema?
  - ¿El lenguaje se entiende sin experiencia en sysadmin?
  - ¿Marca correctamente los niveles de confianza?
- Ajustar redacción del prompt y re-ejecutar hasta que todos los escenarios produzcan informes aceptables
- Usar el modo caché (tarea #189) para iterar rápidamente

## Por qué importa

Un prompt que funciona para disco lleno puede fallar para cascada (múltiples causas correlacionadas). La iteración con escenarios reales es la única forma de validar que el prompt generaliza. Es la Fase 5 del roadmap — paralelizable desde la semana 3 con evidencia simulada.

## Criterio de avance

El prompt produce informes correctos para los 4 escenarios básicos y al menos 3 de los 5 realistas. Cada informe identifica la causa raíz y propone una solución viable.

---

### #193 — Validar comprensibilidad del lenguaje

**Label:** `fase-5`

## Qué es esta tarea

Hacer una revisión interna e iterativa del lenguaje de los informes generados: ¿se entienden sin experiencia en administración de sistemas? Es una validación del equipo, no la prueba formal con usuarios externos (esa es la tarea #215).

## Qué se debe hacer

- Leer los informes generados como si fueras alguien que sabe usar la terminal pero no es sysadmin
- Identificar términos técnicos sin explicación (ej: "OOM", "journalctl", "systemd unit")
- Verificar que cada concepto técnico tiene una frase explicativa entre paréntesis
- Verificar que los pasos de solución son seguibles sin conocimiento previo
- Ajustar el prompt para reducir jerga y mejorar claridad
- Documentar los cambios realizados y por qué

## Por qué importa

La comprensibilidad es la promesa central del producto (sección 2 del documento de proyecto): "que cualquier persona entienda qué pasó". La revisión interna es un filtro rápido antes de la prueba formal con usuarios reales (Fase 9). Si el equipo no entiende un informe, un usuario externo tampoco lo hará.

## Criterio de avance

Todos los informes generados usan lenguaje accesible. Cada término técnico tiene explicación entre paréntesis. Los pasos de solución son ejecutables por alguien con acceso a terminal y sin experiencia en sysadmin.

---

### #194 — Reducir alucinaciones

**Label:** `fase-5`

## Qué es esta tarea

Ajustar el prompt para que el modelo incluya secciones de "Descartado" (causas consideradas y por qué no encajan) y niveles de confianza (alta, media, baja) en cada hipótesis. Reduce la posibilidad de que el modelo afirme algo incorrecto con seguridad falsa.

## Qué se debe hacer

- Modificar el prompt para exigir:
  - Sección "**Causas descartadas**" con al menos 2 causas alternativas y la razón de descarte
  - Nivel de confianza (alta/media/baja) junto a cada hipótesis de causa raíz
  - Si la evidencia es insuficiente, decirlo explícitamente en vez de adivinar
- Verificar con los escenarios de prueba que:
  - El modelo no inventa causas sin evidencia
  - La cascada (escenario 7) produce confianza diferenciada entre causa raíz (alta) y síntomas derivados (media/baja)
  - Los escenarios negativos no producen diagnósticos cuando no hay problema

## Por qué importa

Un modelo de IA puede generar diagnósticos plausibles pero incorrectos con total seguridad ("alucinar"). Los niveles de confianza y la sección de descartados obligan al modelo a explicar su razonamiento — y al lector a juzgar la confiabilidad. Es la decisión de diseño 17.2 del documento de proyecto aplicada al prompt.

## Criterio de avance

Todos los informes incluyen la sección de causas descartadas y niveles de confianza. El modelo marca confianza baja cuando la evidencia es ambigua, y nunca afirma con confianza alta sin evidencia directa.

---

## Fase 6 — Persistencia y Servicio Systemd

### #195 — Escritura de informes

**Label:** `fase-6`

## Qué es esta tarea

Implementar la escritura de cada informe generado como archivo Markdown en disco, con nombre estandarizado que incluya timestamp y tipo de incidente.

## Qué se debe hacer

- Crear el directorio `/var/lib/doctorjk/informes/` (el instalador lo crea, pero el módulo debe verificar que existe)
- Guardar cada informe como `{timestamp}_{incident_type}.md` (ej: `20260812_234700_disco_lleno.md`)
- El contenido es el informe completo tal como lo genera el modelo
- Crear `doctorjk/informe.py` con la lógica de escritura
- Manejar permisos: el archivo debe ser legible por el usuario que consulte

## Por qué importa

Los informes en disco son el producto principal del Modo 1 (sección 4 del documento de proyecto). El administrador los lee para entender qué pasó. Sin persistencia en disco, el diagnóstico existe solo en la respuesta HTTP y se pierde. El formato Markdown permite leerlos en cualquier editor o navegador.

## Criterio de avance

Cada incidente detectado produce un archivo `.md` en `/var/lib/doctorjk/informes/` con nombre descriptivo. El archivo se puede leer con `cat` o cualquier visor de Markdown.

---

### #196 — Unit systemd

**Label:** `fase-6`

## Qué es esta tarea

Crear la unit de systemd que ejecuta Doctor J/K como un servicio permanente del sistema: arranca con el servidor, se reinicia si crashea, y sus logs van a journald.

## Qué se debe hacer

- Crear `instalador/doctorjk.service` con:
  ```ini
  [Unit]
  Description=Doctor J/K - Diagnosticador de servidores
  After=network.target

  [Service]
  Type=simple
  User=doctorjk
  ExecStart=/usr/bin/python3 /opt/doctorjk/main.py
  Restart=always
  RestartSec=5

  [Install]
  WantedBy=multi-user.target
  ```
- El servicio corre como usuario `doctorjk` (sin root para el monitor; root solo cuando se activa el remediador)
- Los logs del agente van a journald automáticamente
- `Restart=always` asegura que el agente se recupera de crashes

## Por qué importa

Doctor J/K es un agente que vive dentro del servidor (sección 2 del documento de proyecto). "Vive" significa que arranca solo, corre 24/7 y se recupera de fallos. Sin la unit de systemd, alguien tendría que ejecutar el script manualmente cada vez que el servidor reinicia — inaceptable para un producto que promete vigilancia autónoma.

## Criterio de avance

`systemctl start doctorjk` inicia el agente. `systemctl status doctorjk` muestra "active (running)". Si se mata el proceso, systemd lo reinicia automáticamente. Los logs aparecen en `journalctl -u doctorjk`.

---

### #197 — Script de instalación

**Label:** `fase-6`

## Qué es esta tarea

Crear el script `install.sh` que instala Doctor J/K completo en un servidor limpio: crea usuarios, directorios, instala dependencias, copia archivos y habilita el servicio. Meta dura: menos de 15 minutos de principio a fin.

## Qué se debe hacer

- Crear `instalador/install.sh` que:
  1. Crea el usuario `doctorjk` (sin login)
  2. Crea los directorios necesarios (`/opt/doctorjk/`, `/var/lib/doctorjk/informes/`)
  3. Instala dependencias del sistema (Python 3.11+, pip)
  4. Instala dependencias de Python (`requests` o `httpx`)
  5. Copia los archivos del agente a `/opt/doctorjk/`
  6. Copia la unit de systemd y la habilita
  7. Configura las credenciales del servicio: para el prototipo, lee las variables de entorno de un archivo `.env` (API key de Cloudflare del equipo). En producción, las credenciales las provee Beetle como parte del servicio (ver sección 23 del documento de proyecto)
  8. Arranca el servicio
- El script debe ser idempotente (ejecutarlo dos veces no rompe nada)
- Debe funcionar en Ubuntu Server 24.04 y Debian 12+

## Por qué importa

El buyer persona (Mateo, sección 2.1) abandona cualquier herramienta que tome más de 15 minutos de instalar. La meta de <15 minutos no es una aspiración — es criterio de avance de la Fase 6 (roadmap). El script de instalación es la puerta de entrada al producto.

## Criterio de avance

Sobre un VPS limpio con Ubuntu Server 24.04, ejecutar `install.sh` deja Doctor J/K corriendo como servicio en menos de 15 minutos cronometrados. Sin pasos manuales adicionales excepto proveer las credenciales.

---

### #198 — Rotación de informes

**Label:** `fase-6`

## Qué es esta tarea

Implementar la rotación automática de informes para evitar llenar el disco con diagnósticos acumulados a lo largo de meses. Es un mecanismo de higiene: guardar los últimos 30 informes y borrar los más antiguos.

## Qué se debe hacer

- Después de escribir un nuevo informe, verificar cuántos hay en `/var/lib/doctorjk/informes/`
- Si hay más de 30, borrar los más antiguos (por fecha del filename o del filesystem)
- Alternativa: borrar informes de más de 30 días
- Incluir la evidencia cruda (`_evidencia.txt`) en la rotación
- Registrar en log cuando se borran informes viejos

## Por qué importa

Doctor J/K corre 24/7. Sin rotación, un servidor con incidentes frecuentes acumula cientos de informes — irónicamente, pudiendo causar un incidente de disco lleno que el propio agente debería detectar. La rotación previene este escenario circular.

## Criterio de avance

Nunca hay más de 30 informes (o 30 días) en el directorio. Los informes más antiguos se borran automáticamente cuando se genera uno nuevo.

---

## Fase 7 — Remediador por Scripts (Modo 2)

### #199 — Scripts de corrección

**Label:** `fase-7`

## Qué es esta tarea

Escribir y probar los scripts bash de corrección para los tipos de incidente conocidos. Son la implementación del Modo 2: correcciones deterministas, predecibles y auditables para los problemas más comunes.

## Qué se debe hacer

- Crear 4 scripts probados en `scripts-fix/`:
  - `fix_disco.sh`: identifica archivos grandes en `/var/log` y `/tmp`, limpia los seguros, verifica con `df`
  - `fix_servicio.sh`: reinicia el servicio fallido, verifica con `systemctl status`
  - `fix_memoria.sh`: identifica procesos con mayor consumo, limpia caché si es seguro, verifica con `free`
  - `fix_puerto.sh`: identifica el proceso ocupando el puerto, lo detiene si es seguro, reinicia el servicio esperado
- Cada script debe:
  - Verificar la condición antes de actuar
  - Ejecutar solo acciones seguras y predefinidas
  - Registrar lo que hizo en stdout/stderr
  - Retornar código de salida correcto (0 = éxito, 1 = fallo)

## Por qué importa

El Modo 2 es corrección determinista (sección 4 del documento de proyecto): "siempre corre el mismo script probado para el mismo tipo de problema". Estos scripts son el primer nivel de auto-healing — predecible, auditable y seguro. Son el paso previo al Modo 3 (corrección por IA) y deben funcionar perfectamente para los escenarios conocidos.

## Criterio de avance

Un incidente de disco lleno se resuelve automáticamente en <2 minutos sin intervención humana (criterio de Fase 7 en el roadmap). Los 4 scripts están probados sobre el VPS con los 4 escenarios básicos.

---

### #200 — Clasificador de tipo

**Label:** `fase-7`

## Qué es esta tarea

Implementar la lógica que mapea el tipo de incidente detectado al script de corrección correcto. Es el enlace entre el detector y el remediador: cuando se detecta un incidente de tipo `disco_lleno`, ejecutar `fix_disco.sh`.

## Qué se debe hacer

- Crear un mapeo tipo → script:
  ```python
  SCRIPTS = {
      "disco_lleno": "scripts-fix/fix_disco.sh",
      "servicio_caido": "scripts-fix/fix_servicio.sh",
      "memoria_agotada": "scripts-fix/fix_memoria.sh",
      "puerto_ocupado": "scripts-fix/fix_puerto.sh",
  }
  ```
- Cuando el detector confirma un incidente, pasar el tipo al clasificador
- El clasificador retorna la ruta del script correspondiente
- Si no hay script para ese tipo, registrar en log y no ejecutar nada (solo informe)

## Por qué importa

Sin clasificador, el remediador no sabe qué script ejecutar. Y ejecutar el script equivocado para un tipo de incidente es peor que no ejecutar nada — podría agravar el problema. El mapeo explícito elimina ambigüedad.

## Criterio de avance

Cada tipo de incidente detectado se mapea correctamente a su script de corrección. Un tipo sin script registra el caso y no ejecuta corrección. No hay scripts huérfanos ni tipos sin clasificar.

---

### #201 — Logging de auditoría

**Label:** `fase-7`

## Qué es esta tarea

Registrar en log cada comando ejecutado por el remediador del Modo 2: qué corrió, cuándo, qué salió, y si tuvo éxito o falló. Es la trazabilidad completa de las acciones automáticas.

## Qué se debe hacer

- Para cada script de corrección ejecutado, registrar:
  - Timestamp de inicio y fin
  - Comando/script ejecutado
  - Código de salida
  - stdout y stderr completos
  - Resultado: éxito o fallo
- Los registros van a journald (via `logging`) y al informe generado
- Formato legible para auditoría posterior

## Por qué importa

Cuando un agente ejecuta acciones en un servidor, el administrador necesita saber exactamente qué hizo y qué resultó. La auditoría es un diferenciador del producto (sección 4 del documento de proyecto): "Cuando Doctor J/K corrige, deja un registro completo de qué hizo y por qué — auditable, reversible, transparente."

## Criterio de avance

Después de una corrección automática, `journalctl -u doctorjk` muestra el comando ejecutado, su resultado y el código de salida. La misma información aparece en el informe generado.

---

### #202 — Verificación post-corrección

**Label:** `fase-7`

## Qué es esta tarea

Después de ejecutar un script de corrección, ejecutar un comando de verificación para confirmar que el problema se resolvió. Si no se resolvió, reportar el fallo en vez de asumir éxito.

## Qué se debe hacer

- Para cada tipo de corrección, definir un comando de verificación:
  - Disco: `df -h` → verificar que el uso bajó del umbral
  - Servicio: `systemctl status <servicio>` → verificar "active (running)"
  - Memoria: `free -m` → verificar disponibilidad sobre umbral
  - Puerto: `ss -tlnp` → verificar que el puerto está escuchando
- Ejecutar la verificación después de la corrección
- Si la verificación falla:
  - Registrar el fallo en log y en el informe
  - Marcar el incidente como "corrección fallida" (no como resuelto)
  - No reintentar automáticamente (escalar al administrador)

## Por qué importa

Un script que corre sin error no garantiza que el problema se resolvió. El servicio puede no arrancar por otra razón, el disco puede llenarse de nuevo inmediatamente. La verificación post-corrección es lo que distingue "ejecuté algo" de "resolví el problema" (sección de Fase 7 en el roadmap).

## Criterio de avance

Después de cada corrección, se ejecuta una verificación. Si la verificación pasa, el incidente se marca como resuelto. Si falla, se marca como corrección fallida y se registra en el informe.

---

## Fase 8 — Escenarios de Prueba y Medición

### #203 — Scripts de provocación

**Label:** `fase-8`

## Qué es esta tarea

Escribir los scripts que provocan intencionalmente cada uno de los 9 escenarios de prueba: 4 básicos y 5 realistas. Son la herramienta principal de validación del agente.

## Qué se debe hacer

- Crear scripts en `demo/` para los 9 escenarios (sección 15 del documento de proyecto):
  - **Básicos**: 01_servicio_caido.sh (`systemctl stop postgresql`), 02_disco_lleno.sh (`fallocate -l 18G /tmp/relleno`), 03_memoria_agotada.sh (script que reserva RAM hasta OOM), 04_puerto_ocupado.sh (`nc -l 5432` antes de PostgreSQL)
  - **Realistas**: 05_disco_por_logs.sh (activar debug sin logrotate), 06_fuga_memoria.sh (leak gradual), 07_cascada.sh (disco → Postgres → app → Nginx), 08_config_rota.sh (modificar `pg_hba.conf`), 09_puerto_secuestrado.sh (otro proceso toma el 5432)
- Crear scripts para los 5 **casos negativos** en `demo/negativos/`: N1_apt_upgrade, N2_reinicio_programado, N3_pico_trafico, N4_rotacion_logs, N5_backup
- Todos deben correr con tráfico de fondo (condición de la sección 15.4)

## Por qué importa

Sin scripts de provocación estandarizados, cada prueba es manual y no reproducible. Los 42 corridas de la Fase 8 (27 positivas + 15 negativas) requieren provocaciones idénticas para que los resultados sean comparables. Los 5 realistas prueban los casos donde el diagnóstico es difícil (cascada, fuga gradual, causa en config).

## Criterio de avance

Los 9 scripts de provocación y los 5 de casos negativos están escritos y cada uno reproduce su escenario de forma confiable. Se puede restaurar el VPS desde snapshot entre pruebas.

---

### #204 — Respuestas esperadas

**Label:** `fase-8`

## Qué es esta tarea

Para cada escenario, documentar antes de ejecutar la prueba cuál es el resultado esperado: qué síntoma debe observarse, cuál es la causa raíz correcta y cuáles son los pasos de solución correctos. Es la referencia contra la que se evalúa el diagnóstico del agente.

## Qué se debe hacer

- Crear un archivo por escenario en `pruebas/esperados/`:
  - Síntoma observable (lo que el monitor/trigger debe detectar)
  - Causa raíz correcta (lo que el modelo debe identificar)
  - Pasos de solución correctos (lo que la guía debe recomendar)
  - Señales que NO deben aparecer (para evaluar falsos positivos/negativos)
- Documentar ANTES de ejecutar las pruebas — es la hipótesis, no el resultado

## Por qué importa

Sin respuestas esperadas definidas antes de las pruebas, la evaluación es subjetiva ("¿este informe se ve bien?"). Con respuestas esperadas, la evaluación es objetiva: el agente identificó o no la causa raíz, los pasos resuelven o no el problema. Es la base para calcular las métricas de la sección 16 del documento de proyecto.

## Criterio de avance

Los 9 escenarios y 5 casos negativos tienen respuestas esperadas documentadas antes de la primera ejecución. Cada documento define: síntoma, causa raíz, solución y criterio de evaluación.

---

### #205 — 3 corridas por escenario

**Label:** `fase-8`

## Qué es esta tarea

Ejecutar cada escenario 3 veces para medir la consistencia del agente. Son 9 × 3 = 27 ejecuciones de escenarios positivos + 5 × 3 = 15 de casos negativos = 42 corridas totales.

## Qué se debe hacer

- Para cada escenario:
  1. Restaurar el VPS desde el snapshot
  2. Ejecutar el script de provocación (con tráfico de fondo)
  3. Esperar a que el agente detecte, diagnostique y (si aplica) corrija
  4. Guardar el informe generado en `pruebas/resultados/`
  5. Evaluar contra las respuestas esperadas
  6. Repetir 3 veces
- Para los 5 casos negativos, verificar que el agente NO dispara
- Nombrar resultados con escenario + número de corrida (ej: `07_cascada_run2.md`)
- Registrar cualquier anomalía o variación entre corridas

## Por qué importa

Un agente que acierta 1 de 3 veces no es confiable. Las 3 corridas por escenario miden la consistencia — ¿el agente produce el mismo diagnóstico correcto cada vez, o depende del timing? Las métricas del proyecto (sección 16: >90% detección, >80% causa raíz) se calculan sobre estas 42 corridas.

## Criterio de avance

42 corridas completadas. Cada corrida tiene su informe guardado y evaluado contra la respuesta esperada. Las métricas calculadas sobre las 42 corridas están dentro de las metas definidas.

---

### #206 — Tabulación de resultados

**Label:** `fase-8`

## Qué es esta tarea

Construir la tabla de resultados: una matriz de escenario × métrica con el porcentaje de éxito en cada una. Es el resumen cuantitativo del rendimiento del agente.

## Qué se debe hacer

- Crear una tabla con los 9 escenarios (filas) × 7 métricas (columnas):
  | Métrica | Meta |
  |---------|------|
  | Tasa de detección | >90% |
  | Precisión de causa raíz | >80% |
  | Tasa de falsos positivos | <10% |
  | Tiempo a informe | <120s |
  | Utilidad de la guía | >70% |
  | Comprensibilidad | >80% |
  | Corrección automática | >85% |
- Calcular el porcentaje de éxito de cada métrica sobre las 3 corridas
- Calcular promedios generales
- Identificar escenarios problemáticos (los que fallan más de una métrica)
- Guardar en `pruebas/resultados/matriz_resultados.md`

## Por qué importa

Sin tabulación, los resultados son 42 informes sueltos que nadie puede interpretar rápidamente. La matriz permite ver de un vistazo dónde el agente falla y dónde excede la meta. Es también el material que va en la presentación final (tarea #220) y la base para decidir si el prototipo cumple sus objetivos (sección 16 del documento de proyecto).

## Criterio de avance

Matriz completa con todas las métricas calculadas. Cada celda tiene el % de éxito sobre las 3 corridas. Los promedios generales cumplen con las metas de la sección 16.

---

## Fase 9 — Remediador Automático (Modo 3)

### #207 — Generador de plan de corrección

**Label:** `fase-9`

## Qué es esta tarea

Implementar la capacidad del modelo para generar un plan de corrección estructurado: por cada paso, un comando exacto, el resultado esperado, la condición para continuar y la condición para abortar. Es el cerebro del Modo 3.

## Qué se debe hacer

- Diseñar el formato de salida del plan:
  ```json
  {
    "pasos": [
      {
        "comando": "sudo systemctl restart postgresql",
        "resultado_esperado": "El servicio arranca sin errores",
        "condicion_continuar": "systemctl status postgresql muestra active",
        "condicion_abortar": "El servicio no arranca o muestra error nuevo"
      }
    ]
  }
  ```
- Modificar el prompt para que el modelo genere este formato cuando se solicita corrección
- Parsear la respuesta y validar que tiene la estructura esperada
- Si la respuesta no tiene el formato correcto, tratar como error (no ejecutar nada)

## Por qué importa

El Modo 3 es el diferenciador comercial central del producto (sección 14.1 del documento de proyecto). A diferencia del Modo 2 (scripts fijos), el Modo 3 puede corregir incidentes que no tienen script preescrito. Pero esa flexibilidad requiere estructura: el plan explícito con condiciones de aborto es lo que permite ejecutar con las salvaguardas obligatorias.

Si al cierre del proyecto se adopta la Opción B (dupla planificador/ejecutor, sección 14.6 del documento de proyecto), este generador corre sobre **Kimi K2.6** como planificador/analista.

## Criterio de avance

El modelo genera planes de corrección con el formato estructurado para al menos los 4 escenarios básicos. Cada paso incluye comando, resultado esperado, condición para continuar y condición para abortar.

---

### #208 — [SALVAGUARDA] Lista blanca de comandos

**Label:** `fase-9`

## Qué es esta tarea

Implementar la lista blanca de comandos: solo se ejecutan patrones validados, nunca comandos genéricos generados libremente por el modelo. Es la primera salvaguarda innegociable del Modo 3.

## Qué se debe hacer

- Definir una lista de patrones permitidos (regex o prefijos exactos):
  - `systemctl restart <servicio>`, `systemctl start <servicio>`
  - `rm /var/log/<ruta>`, `rm /tmp/<ruta>` (solo directorios específicos)
  - `truncate -s 0 /var/log/<ruta>`
  - `apt-get install -y <paquete>`
  - `sync; echo 3 > /proc/sys/vm/drop_caches`
- Rechazar cualquier comando que no encaje en un patrón de la lista blanca
- Registrar comandos rechazados en el log de auditoría
- La lista blanca debe ser configurable (archivo) pero conservadora por defecto
- **Nunca**: `rm -rf`, `dd`, `mkfs`, `chmod 777`, comandos con `|`, redirecciones a archivos del sistema

## Por qué importa

Es la salvaguarda que previene el peor escenario: un modelo que alucina un comando destructivo y el agente lo ejecuta. La lista blanca garantiza que, sin importar lo que el modelo genere, solo se ejecutan acciones conocidas y seguras (sección 14.5 del documento de proyecto). Es innegociable — nunca se recorta aunque haya atraso.

## Criterio de avance

Un comando `rm -rf /` generado por el modelo es rechazado y registrado. Solo los comandos que encajan en patrones de la lista blanca se ejecutan. La lista blanca está documentada públicamente (para transparencia operativa).

---

### #209 — [SALVAGUARDA] Modo dry-run

**Label:** `fase-9`

## Qué es esta tarea

Implementar el modo `--dry-run` que muestra exactamente qué haría el remediador sin ejecutar ningún comando. Obligatorio durante desarrollo y demo. Es la segunda salvaguarda innegociable.

## Qué se debe hacer

- Añadir flag `--dry-run` (o configuración en TOML)
- Cuando está activo, el remediador:
  - Genera el plan de corrección normalmente
  - Valida cada comando contra la lista blanca
  - Muestra en consola/informe qué haría: "EJECUTARÍA: sudo systemctl restart postgresql"
  - NO ejecuta ningún comando
- El informe generado en dry-run marca claramente: "[DRY-RUN] Ningún comando fue ejecutado"
- Activado por defecto durante desarrollo

## Por qué importa

Durante el desarrollo, las pruebas y la demo, no se quiere que el agente modifique el servidor — se quiere ver qué haría. El dry-run permite validar la lógica del Modo 3 sin riesgo. En la demo final, es la forma segura de mostrar el Modo 3 sin sorpresas (sección 14.5 del documento de proyecto). Es innegociable.

## Criterio de avance

Con `--dry-run`, el agente genera un plan completo y muestra qué ejecutaría, pero no modifica nada en el servidor. Sin el flag, ejecuta normalmente. Verificado comparando el estado del servidor antes y después.

---

### #210 — [SALVAGUARDA] Flag explícito auto-fix

**Label:** `fase-9`

## Qué es esta tarea

Implementar el flag explícito `--auto-fix` sin el cual el remediador automático no se activa. Por defecto, Doctor J/K solo diagnostica (Modo 1). Es la tercera salvaguarda innegociable.

## Qué se debe hacer

- El remediador del Modo 3 solo se activa si:
  - Se pasa `--auto-fix` como argumento de línea de comandos, O
  - Se configura `auto_fix = true` en `config.toml`
- Sin el flag, el agente opera en Modo 1 (solo diagnóstico + informe)
- El flag debe ser explícito e intencional — no hay "activar por accidente"
- Registrar en log cuándo el flag está activo y cuándo no

## Por qué importa

El buyer persona (Mateo, sección 2.1) necesita confiar en el agente antes de darle permiso de ejecutar comandos. El Modo 1 por defecto es la puerta de entrada: instala, observa que funciona, lee los informes, y solo después activa el auto-fix. Si el Modo 3 estuviera activo por defecto, un error en la primera ejecución destruiría la confianza permanentemente (sección 14.5 del documento de proyecto).

## Criterio de avance

Una instalación nueva de Doctor J/K solo genera informes — no ejecuta correcciones. Solo con `--auto-fix` o `auto_fix = true` el Modo 3 se activa. Verificado con instalación limpia.

---

### #211 — Ejecutor paso a paso con validación

**Label:** `fase-9`

## Qué es esta tarea

Implementar el ejecutor que toma el plan de corrección generado por el modelo y lo ejecuta paso a paso, capturando el resultado de cada paso y validándolo contra la condición esperada antes de continuar con el siguiente.

## Qué se debe hacer

- Recibir el plan estructurado del generador (tarea #207)
- Para cada paso del plan:
  1. Validar el comando contra la lista blanca (tarea #208)
  2. Ejecutar el comando
  3. Capturar stdout, stderr y código de salida
  4. Comparar el resultado contra la condición de continuación
  5. Si cumple, avanzar al siguiente paso
  6. Si no cumple, evaluar la condición de aborto → abortar si aplica
- El tiempo máximo por paso debe ser configurable (ej: 30 segundos)

## Por qué importa

A diferencia de los scripts del Modo 2 (que ejecutan una secuencia fija), el Modo 3 ejecuta un plan generado por IA. La validación paso a paso es lo que impide que un plan parcialmente incorrecto haga daño: si el paso 2 falla, el paso 3 no se ejecuta. Es la implementación práctica del principio "ejecuta con validación" (sección 14.1 del documento de proyecto).

Si al cierre del proyecto se adopta la Opción B (dupla planificador/ejecutor, sección 14.6 del documento de proyecto), este ejecutor corre sobre **Qwen3-30B-A3B**.

## Criterio de avance

Un plan de 4 pasos se ejecuta secuencialmente. Si el paso 2 falla la validación, los pasos 3 y 4 no se ejecutan. Cada resultado intermedio queda registrado.

---

### #212 — [SALVAGUARDA] Aborto automático y escalamiento

**Label:** `fase-9`

## Qué es esta tarea

Implementar el mecanismo de aborto automático: si cualquier paso del plan de corrección produce un resultado inesperado, el remediador se detiene inmediatamente, notifica, deja el informe y no sigue. Es la cuarta salvaguarda innegociable.

## Qué se debe hacer

- Detectar resultado inesperado: código de salida != 0, stdout no coincide con lo esperado, o condición de aborto del plan se cumple
- Al abortar:
  1. Detener la ejecución inmediatamente (no intentar los pasos restantes)
  2. Registrar en el informe: qué paso falló, qué resultado se obtuvo vs. qué se esperaba
  3. Marcar el incidente como "corrección abortada — escalar a administrador"
  4. Dejar el informe completo en disco (con lo que sí se ejecutó y lo que no)
- Nunca reintentar automáticamente después de un aborto
- El estado del servidor debe quedar documentado en el informe para que el administrador sepa desde dónde continuar

## Por qué importa

Es la salvaguarda que impide que el Modo 3 haga daño progresivo. Un modelo que se equivoca en el paso 2 podría empeorar el problema en los pasos 3, 4 y 5 si no se detiene. El aborto automático limita el daño al primer error (sección 14.5 del documento de proyecto). Es innegociable.

## Criterio de avance

Un plan cuyo paso 2 falla: el paso 3 no se ejecuta, el informe documenta qué falló y qué quedó pendiente, y el incidente se marca como "escalar". No hay ejecución parcial silenciosa.

---

### #213 — [SALVAGUARDA] Logging de auditoría del Modo 3

**Label:** `fase-9`

## Qué es esta tarea

Implementar el logging de auditoría completo del Modo 3: cada comando ejecutado, su resultado y la decisión del modelo quedan registrados en el informe final y en journald. Es la quinta salvaguarda innegociable.

## Qué se debe hacer

- Para cada paso ejecutado por el Modo 3, registrar:
  - Timestamp de ejecución
  - Comando ejecutado (textual)
  - Resultado: stdout, stderr, código de salida
  - Decisión del modelo: continuar / abortar / reintentar
  - Justificación de la decisión (del plan generado)
- Los registros van a dos destinos:
  1. **journald** (via logging) — consultable con `journalctl -u doctorjk`
  2. **Informe final** (.md) — sección de auditoría del Modo 3 al final del informe
- El registro debe ser suficiente para reconstruir exactamente qué pasó

## Por qué importa

El administrador que ve "Doctor J/K resolvió un incidente a las 3am" necesita poder verificar exactamente qué hizo. La auditoría completa es lo que hace que el Modo 3 sea transparente en vez de opaco — un diferenciador frente a "auto-healing ciego" (sección 4 del documento de proyecto). Es innegociable.

## Criterio de avance

Después de una corrección del Modo 3, el informe contiene una sección de auditoría con cada comando, su resultado y la decisión. La misma información es consultable en `journalctl -u doctorjk`. Un auditor externo puede reconstruir la secuencia completa.

---

### #214 — Medición de corrección automática

**Label:** `fase-9`

## Qué es esta tarea

Medir la tasa de corrección automática exitosa del Modo 3 como métrica obligatoria (ya no condicional como en la v3.0). La meta es >85% de remediaciones exitosas.

## Qué se debe hacer

- Ejecutar los escenarios de prueba de la Fase 8 con el Modo 3 activo
- Para cada escenario, registrar:
  - ¿El agente generó un plan de corrección?
  - ¿El plan se ejecutó completamente?
  - ¿La verificación post-corrección confirmó que el problema se resolvió?
- Calcular el porcentaje: remediaciones exitosas / incidentes donde se intentó corrección
- Agregar la columna "Corrección automática" a la matriz de resultados (tarea #206)
- Si la métrica está por debajo del 85%, iterar el prompt y la lista blanca

## Por qué importa

En la v3.0, esta métrica era condicional ("si sobra tiempo"). En la v4.0, el Modo 3 es alcance obligatorio y la métrica de >85% es un criterio de avance de la Fase 9 (roadmap). Es lo que valida que el diferenciador comercial del producto funciona en la práctica.

## Criterio de avance

Tasa de corrección automática >85% medida sobre los escenarios de prueba. La métrica aparece en la matriz de resultados junto a las demás métricas de la sección 16 del documento de proyecto.

---

### #215 — Prueba de comprensibilidad con usuarios

**Label:** `fase-9`

## Qué es esta tarea

Validar con personas reales, no técnicas, que los informes generados por Doctor J/K realmente se entienden — la prueba definitiva de que el producto cumple su propuesta de valor central.

## Qué se debe hacer

- Seleccionar 5 informes ya generados durante las pruebas de Fase 8 (idealmente variados: un básico, uno realista, uno de cascada)
- Mostrárselos a 3–5 personas que NO sean administradores de sistemas
- Para cada persona, registrar:
  - ¿Entendió qué pasó, en sus propias palabras?
  - ¿Podría seguir los pasos de la guía de solución sin ayuda adicional?
  - Cualquier término o parte confusa que señalen
- Guardar la retroalimentación en `pruebas/comprensibilidad/`

## Por qué importa

Esta es la validación de la promesa central del producto (documento de proyecto, sección 2): que cualquier persona, no solo un experto, pueda entender el diagnóstico. Es distinta de la revisión técnica interna que ya se hizo en Fase 5 — aquí el juez es alguien externo al equipo.

## Criterio de avance

Comprensibilidad >80%: al menos 4 de cada 5 personas entienden qué pasó y podrían seguir los pasos, según el criterio del roadmap y la sección 16 del documento de proyecto.

---

## Fase 10 — Documentación y Entrega

### #216 — Documentación de arquitectura

**Label:** `fase-10`

## Qué es esta tarea

Crear la documentación de arquitectura: un documento que explique los componentes del sistema, cómo interactúan, las decisiones de diseño tomadas y por qué se tomaron. Dirigido a desarrolladores que necesiten entender o mantener el sistema.

## Qué se debe hacer

- Crear `docs/arquitectura.md` con:
  - Diagrama de componentes (Monitor, Trigger, Detector, Recolector, Sanitizador, Cliente LLM, Informe, Remediador) — puede ser texto o ASCII
  - Flujo de datos: de la detección al informe, paso a paso
  - Decisiones de diseño con justificación (basadas en la sección 17 del documento de proyecto)
  - Justificación de cada componente y por qué existe como pieza separada
  - Interfaces entre componentes (qué recibe y qué produce cada uno)
- El documento debe ser comprensible sin acceso al código fuente

## Por qué importa

Sin documentación de arquitectura, cualquier persona nueva en el proyecto (o el propio equipo en 6 meses) tendría que leer todo el código para entender cómo encajan las piezas. Para un producto cerrado, la documentación de arquitectura es especialmente importante porque no hay código fuente público que sirva de referencia (sección 23 del documento de proyecto).

## Criterio de avance

El documento explica todos los componentes, su interacción y las decisiones de diseño. Un desarrollador puede leerlo y entender la estructura del sistema sin ver el código.

---

### #217 — README completo

**Label:** `fase-10`

## Qué es esta tarea

Escribir el README completo del producto: instalación, configuración, uso y troubleshooting. Incluye la lista blanca de comandos documentada públicamente como transparencia operativa.

## Qué se debe hacer

- Escribir un README con las secciones:
  - **Qué es Doctor J/K**: descripción en una frase + los 3 modos de operación
  - **Instalación**: prerrequisitos, ejecución de `install.sh`, verificación
  - **Configuración**: `config.toml` con todos los parámetros y sus valores por defecto
  - **Uso**: cómo consultar informes, cómo activar Modo 2 y Modo 3, flags disponibles
  - **Lista blanca de comandos**: documentación pública de qué comandos puede ejecutar el Modo 3
  - **Troubleshooting**: problemas comunes y cómo resolverlos
- El README debe ser suficiente para que alguien externo instale y use el producto

## Por qué importa

El criterio de avance de la Fase 10 dice: "Alguien externo puede leer el README, instalar en <15 min y entender qué hace el agente sin ver el código." Para un producto cerrado, el README es la única interfaz entre el producto y el usuario — si no está bien escrito, el producto no se adopta.

## Criterio de avance

Una persona que no ha visto el proyecto antes puede leer el README, instalar Doctor J/K en un VPS limpio en <15 minutos, y entender los 3 modos de operación y cómo consultar informes.

---

### #218 — Empaquetado para distribución

**Label:** `fase-10`

## Qué es esta tarea

Empaquetar Doctor J/K para distribución como producto cerrado: paquete instalable o imagen Docker. El producto se distribuye compilado, nunca como código fuente.

## Qué se debe hacer

- Elegir el formato de distribución:
  - **Opción A**: paquete `.deb` para Ubuntu/Debian (instalable con `dpkg -i`)
  - **Opción B**: imagen Docker (distribución universal)
  - **Opción C**: ambos (ideal, si hay tiempo)
- Empaquetar todo el agente: código compilado/empaquetado, scripts de corrección, prompts, unit de systemd, script de instalación
- No incluir el código fuente Python legible — usar pyinstaller, nuitka o distribución como wheel cerrado
- Verificar que el paquete se instala limpiamente en un VPS nuevo
- Incluir licencia propietaria en el paquete

## Por qué importa

Doctor J/K es código cerrado (sección 23 del documento de proyecto). Distribuir como `.py` sueltos permite al cliente ver, copiar y redistribuir el código. El empaquetado es la implementación técnica de la decisión de producto de código cerrado. Sin embargo, es recortable si hay atraso (es el segundo en la lista de recorte del roadmap).

## Criterio de avance

El paquete o imagen Docker se instala en un VPS limpio sin necesidad de clonar el repositorio. El código fuente no es legible dentro del paquete instalado.

---

### #219 — Preparación de demo

**Label:** `fase-10`

## Qué es esta tarea

Preparar todo lo necesario para la demo final: scripts de demostración que provocan incidentes en vivo e informes pregenerados de respaldo por si falla la red durante la presentación.

## Qué se debe hacer

- Preparar 2–3 scripts de demo que muestren el flujo completo:
  1. Provocar un incidente (ej: parar un servicio)
  2. El agente detecta, diagnostica y genera el informe en vivo
  3. Mostrar el informe generado
  4. (Opcional) Mostrar corrección automática en dry-run
- Pregenerar 3–5 informes de diferentes escenarios como respaldo
- Los informes pregenerados son el **único respaldo** si falla la red — ya no hay modo offline (se eliminó Ollama)
- Preparar un guión de demo con tiempos estimados para cada parte
- Probar el flujo completo al menos 2 veces antes de la presentación

## Por qué importa

La demo es el momento donde el producto se presenta ante evaluadores. Un demo que falla por problemas técnicos evitables (red caída, script mal probado) arruina la evaluación del trabajo de 10 semanas. Los informes pregenerados son el único plan B (sección 18, riesgo de red).

## Criterio de avance

La demo completa funciona de principio a fin en menos de 10 minutos. Si se desconecta la red, los informes pregenerados permiten continuar la presentación mostrando resultados reales.

---

### #220 — Presentación

**Label:** `fase-10`

## Qué es esta tarea

Preparar la presentación final del proyecto que cubre: el problema, el cliente objetivo, la solución, los resultados de pruebas y el modelo de producto.

## Qué se debe hacer

- Crear una presentación (slides o formato equivalente) con:
  1. **El problema**: la brecha entre alerta y acción, el costo del tiempo muerto (sección 3)
  2. **El cliente**: PyME tecnológica sin equipo de infra dedicado, buyer persona Mateo (sección 2)
  3. **La solución**: los 3 modos, el pipeline completo, la sanitización (sección 4)
  4. **Resultados de pruebas**: la matriz de métricas de la Fase 8, la prueba de comprensibilidad (sección 16)
  5. **Modelo de producto**: código cerrado, acceso al LLM incluido, pricing (sección 23)
  6. **Demo**: en vivo o informes pregenerados
  7. **Roadmap futuro**: expansión a medianas empresas, panel web, correlación multi-servidor
- Máximo 15–20 slides
- Incluir al menos un informe real como ejemplo

## Por qué importa

La presentación es la evaluación final del proyecto universitario. Debe demostrar no solo que el agente funciona técnicamente, sino que hay un producto viable con un cliente definido, un modelo de negocio y métricas de validación. Los 10 semanas de trabajo se justifican aquí.

## Criterio de avance

Presentación completa con las 7 secciones, máximo 20 slides, ensayada al menos una vez. La demo funciona o tiene respaldo con informes pregenerados.

---

### #221 — [OPT] Backend + panel web

**Label:** `fase-10`

## Qué es esta tarea

[OPCIONAL] Implementar un backend con Cloudflare Workers + D1 que recibe informes de múltiples servidores y los almacena en un historial consultable con un panel web mínimo. Es la primera pieza hacia la expansión a clientes con múltiples servidores.

## Qué se debe hacer

- Crear un Worker en Cloudflare que reciba informes via POST
- Almacenar en D1 (SQLite distribuido): hostname, timestamp, tipo, diagnóstico, resultado de corrección
- Panel web estático (HTML + fetch) que muestra:
  - Lista de servidores reportando
  - Historial de incidentes por servidor
  - Último estado conocido de cada servidor
- Autenticación mínima (API key por servidor)
- El agente envía el informe al backend después de escribirlo en disco local

## Por qué importa

El producto actual es independiente por máquina — cada agente vive en su servidor y no se comunica con los demás. Para el segmento de expansión (empresas medianas con 20–200 servidores), la vista centralizada es imprescindible. Este backend es el primer paso, pero es **el primero en recortarse** si hay atraso (lista de recorte del roadmap).

## Criterio de avance

Un agente en el VPS envía un informe al Worker. El informe aparece en el panel web con hostname, timestamp y diagnóstico. El historial persiste entre sesiones.

---
