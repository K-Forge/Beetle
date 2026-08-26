# Plan de ejecución del MVP de Doctor J/K

**Fecha de corte:** 2026-08-25  
**Base revisada:** `main` en `6166bf9`, PR #223, issues #166–#222 y documentos v4.0  
**Objetivo:** convertir el repositorio actual en un MVP v0.1 instalable, medido y
demostrable, sin agregar el backend web opcional.

Este documento es una guía de ejecución. No reemplaza el documento maestro, el
roadmap ni las tareas. Cuando haya una contradicción, se detiene la implementación,
se registra la diferencia y se corrige primero la fuente normativa correspondiente.

---

## 1. Definición verificable del MVP

El MVP v0.1 está terminado solo cuando una persona externa puede instalar Doctor J/K
en un Ubuntu Server 24.04 limpio en menos de 15 minutos y demostrar este flujo:

```text
monitor + trigger
      -> señales normalizadas
      -> detector por persistencia
      -> evidencia local cruda
      -> evidencia sanitizada
      -> diagnóstico LLM o fallback
      -> informe Markdown
      -> remediación opcional y auditada
```

El producto final incluye:

1. **Modo 1:** detecta, diagnostica y escribe un informe; es el modo por defecto.
2. **Modo 2:** ejecuta scripts deterministas para los cuatro incidentes básicos.
3. **Modo 3:** ejecuta planes generados por el modelo únicamente con lista blanca,
   `--dry-run`, `--auto-fix`, aborto automático y auditoría completa.
4. **Instalación:** usuario sin login, configuración preservada, secretos con modo
   `600`, servicio systemd y almacenamiento local de informes.
5. **Validación:** pruebas unitarias, integración local, pruebas en el VPS, protocolo
   de escenarios y métricas documentadas.

### 1.1 Criterios de salida

| Capacidad | Criterio obligatorio |
|---|---|
| Instalación | Menos de 15 minutos en un VPS limpio |
| Detección | Más de 90 % de incidentes provocados detectados |
| Causa raíz | Más de 80 % de informes con causa correcta |
| Falsos positivos | Menos de 10 % en los casos negativos |
| Informe | Menos de 120 segundos desde el fallo |
| Guía | Más de 70 % de guías resuelven el problema |
| Comprensibilidad | Más de 80 % de personas entiende el informe |
| Modo 3 | Más de 85 % de remediaciones exitosas |
| Seguridad | 100 % de pruebas de sanitización y lista blanca pasan |

### 1.2 Fuera del MVP

- Issue #221: backend, D1 y panel web.
- Correlación entre servidores, vista centralizada, RBAC y compliance.
- Soporte para distribuciones distintas de Ubuntu/Debian.
- Ollama o modelos ejecutados localmente.
- Ejecución libre de comandos que no estén en la lista blanca.
- Segunda VM de pruebas: la cuota real de OCI no lo permite.
- Tráfico de fondo permanente: cada corrida usa `hey -z 2m` como máximo.

El empaquetado propietario de #218 es el último gate recortable. Si no cabe en el
cronograma, se entrega v0.1 mediante el instalador, se registra la deuda y no se
afirma que la distribución cerrada está resuelta.

---

## 2. Estado validado del repositorio

### 2.1 Qué existe

| Área | Estado comprobado |
|---|---|
| Fase 0, issues #166–#170 | Cerrada; repo, VPS, snapshots, carga y Cloudflare preparados |
| Trigger #172 | Integrado en `main`; probado 61 minutos y ante caída real |
| Monitor #171 | Implementado en el PR #223, pero todavía no está en `main` |
| Punto de entrada #222 | Abierto; `doctorjk/main.py` no existe |
| Fases 2–10 | Especificadas, sin implementación del agente |
| Infraestructura | Workflows de despliegue y restauración presentes |
| Pruebas | Solo README y protocolos; no hay tests ejecutables ni fixtures |

### 2.2 Bloqueos y deuda inmediata

1. #171 está cerrado aunque el PR #223 sigue abierto y bloqueado. No debe
   considerarse integrado hasta que el código llegue a `main` y pase pruebas.
2. El PR #223 no incluye tests automatizados. El monitor fue validado manualmente,
   pero sus parsers necesitan fixtures para evitar regresiones.
3. `trigger.sh` llama provisionalmente a `doctorjk.monitor --once`; no existe un
   proceso dueño del estado del detector ni una entrada al pipeline.
4. El README raíz dice “sin código todavía”, lo cual ya es falso.
5. La línea de tiempo HTML tiene un estado estático desactualizado frente a GitHub.
6. No existen `config.py`, `config.toml.example`, `pyproject.toml`, instalador ni
   unidad systemd; tampoco se puede ejecutar una prueba local reproducible.
7. El enunciado de #208 mezcla una orden con `;` y redirección con una prohibición
   expresa de esos operadores. El MVP no debe implementar esa excepción insegura.

### 2.3 Decisión sobre #223

No hacer merge sin cambios. Antes deben cumplirse estas condiciones:

- agregar fixtures de `systemctl`, `df`, `free`, `ss` y `uptime`;
- probar éxito, salida malformada, comando ausente, timeout y exit code distinto de 0;
- reemplazar estructuras públicas `dict[str, Any]` por contratos tipados en el
  siguiente PR de normalización, sin mezclar esa refactorización con correcciones;
- validar que `--interval` sea mayor que cero;
- evitar construir muestras de nivel DEBUG cuando DEBUG está desactivado;
- acordar primero el contrato entre trigger y `main.py` descrito abajo.

---

## 3. Decisiones de arquitectura para cerrar antes de programar

Estas decisiones resuelven huecos reales de #222 y del documento maestro. Deben
quedar registradas en el issue y en la sección 8.4 del documento de proyecto.

### 3.1 Un solo dueño del estado

`doctorjk/main.py` será el único orquestador de larga vida. Mantendrá una sola
instancia del detector, porque los contadores de persistencia y la deduplicación no
pueden repartirse entre procesos efímeros.

El trigger no declara incidentes ni invoca al remediador. Su contrato será emitir un
evento local que despierte al orquestador. El orquestador toma una muestra inmediata,
la normaliza y la entrega al mismo detector que procesa el polling.

Implementación preferida para el MVP:

1. `doctorjk.service` ejecuta `main.py`, que crea y mantiene abierto
   `/run/doctorjk/trigger.fifo` con permisos restringidos.
2. `doctorjk-trigger.service` ejecuta `trigger.sh` como el mismo usuario de servicio.
3. Ante un warning relevante, el trigger escribe solo una señal fija en el FIFO; no
   duplica en el evento la línea potencialmente sensible del journal.
4. `main.py` usa `selectors` para esperar el FIFO hasta el siguiente tick de polling;
   al recibir una señal toma una muestra inmediata.
5. systemd reinicia y audita cada proceso por separado. Ambos entregan datos al mismo
   detector residente dentro de `main.py`.

**Trade-off:** se instalan dos unidades y un canal local. A cambio se respeta el uso
de `subprocess.run` para comandos, no se necesita `Popen`, no hay estado compartido en
disco y un fallo del trigger no derriba el monitor.

### 3.2 Contratos de datos

Crear `doctorjk/modelos.py` con `dataclass` inmutables y sin lógica de negocio:

| Contrato | Campos mínimos |
|---|---|
| `SystemSnapshot` | `captured_at`, servicios, discos, memoria, puertos, carga |
| `TriggerEvent` | `occurred_at` y fuente local; el mensaje se recupera del journal |
| `Signal` | `timestamp`, `signal_type`, `value`, `threshold`, `crossed`, `key` |
| `Incident` | `incident_id`, tipo, recurso, inicio, confirmación, estado |
| `Evidence` | metadatos, logs, snapshot, cambios, historial y texto crudo |
| `CorrectionStep` | argv exacto, resultado esperado, continuar y abortar |
| `CorrectionPlan` | identificador, incidente y pasos |
| `ExecutionResult` | timestamps, argv, exit code, stdout, stderr y decisión |

Los módulos reciben y devuelven estos contratos; no leen atributos internos de otro
componente. Los enums y nombres internos van en inglés. Los nombres de archivo,
comentarios, docstrings, logs y documentación se mantienen en español.

### 3.3 Configuración

`config.toml` es interfaz del cliente y conserva claves en español. `config.py` las
convierte una sola vez a un `AppConfig` tipado con atributos internos en inglés.

Claves mínimas:

```toml
intervalo_monitor_s = 30
ciclos_persistencia = 2
disco_pct = 90
memoria_disponible_mb = 512
puerto_timeout_s = 60
servicio_ciclos = 2
directorio_informes = "/var/lib/doctorjk/informes"
modo_remediacion = "diagnostico"
auto_fix = false
dry_run = true
timeout_comando_s = 30
```

`modo_remediacion` admite `diagnostico`, `scripts` o `automatico`. La ejecución
requiere un modo de remediación y opt-in efectivo: `--auto-fix` **o**
`auto_fix = true`, tal como fija #210. Sin opt-in no se ejecuta nada; una instalación
nueva usa `diagnostico`, `auto_fix = false` y `dry_run = true`.

### 3.4 Cliente HTTP

Usar `requests` como única dependencia externa de ejecución. Es suficiente para un
POST sincrónico y simplifica el instalador. Inyectar `Session`, reloj y función de
espera en tests; no hacer red en pruebas unitarias.

### 3.5 Ejecución segura

La lista blanca opera sobre `list[str]`, nunca sobre una cadena para `shell=True`.
Usar `shlex.split` solo al validar entrada del modelo y rechazar metacaracteres antes
de construir argv. La política por defecto permite únicamente:

- `systemctl start|restart <unidad-configurada>`;
- `truncate -s 0 <archivo-bajo-ruta-configurada>`;
- eliminación de un archivo regular bajo raíces configuradas, sin recursión;
- comandos de verificación de solo lectura explícitamente registrados.

No incluir en el MVP `apt-get install` arbitrario ni escritura a
`/proc/sys/vm/drop_caches`. El primero cambia la cadena de suministro y el segundo
requiere redirección/root; ambos amplían la superficie sin ser necesarios para los
cuatro escenarios básicos.

### 3.6 Privilegios

El servicio corre como `doctorjk`. La remediación usa una política sudoers generada
por el instalador con comandos y recursos exactos. Nunca se concede `sudo` genérico.
Cada script valida nuevamente sus argumentos y rutas aunque sudoers ya los limite.

---

## 4. Protocolo para el modelo ejecutor

Aplicar estas reglas en cada bloque de trabajo:

1. Leer `CONTEXTO-IA.md`, el README de la carpeta y el issue asignado.
2. Confirmar que los archivos base coinciden con `main`; no programar sobre un PR
   pendiente sin declarar esa dependencia.
3. Trabajar un solo bloque de este plan por PR.
4. Escribir primero tests del contrato y de los errores, luego la implementación.
5. No agregar dependencias sin aprobación explícita.
6. No tocar módulos posteriores salvo para consumir un contrato ya aprobado.
7. Ejecutar los comandos de verificación del bloque.
8. Revisar `git diff --check`, `git status --short` y que no haya secretos.
9. Usar un commit convencional en inglés y cerrar el issue solo tras merge y
   validación exigida por su criterio de avance.
10. Si un dato del VPS no está disponible localmente, marcar la prueba como pendiente;
    no inventar una salida ni un resultado.

Comandos base al final de cada PR:

```bash
python3 -m compileall doctorjk pruebas/unitarias
python3 -m pytest pruebas/unitarias -q
git diff --check
git status --short
```

Para Bash, agregar cuando exista la herramienta:

```bash
shellcheck doctorjk/trigger.sh instalador/*.sh scripts-fix/*.sh demo/*.sh
bash -n doctorjk/trigger.sh instalador/*.sh scripts-fix/*.sh demo/*.sh
```

---

## 5. Secuencia de implementación

Cada bloque produce un PR pequeño. No iniciar un bloque cuyo campo “Depende de” no
esté integrado en `main`.

### Gate A — Reparar la base y cerrar Fase 1

#### A1. Revisar e integrar el monitor (#171, PR #223)

**Depende de:** nada.  
**Archivos:** `doctorjk/__init__.py`, `doctorjk/monitor.py`, `doctorjk/trigger.sh`,
fixtures y `test_monitor.py`.

Pasos:

1. Extraer parsers puros que reciben texto; dejar `subprocess` en funciones de borde.
2. Agregar las pruebas enumeradas en 2.3 con salidas reales sanitizadas del VPS.
3. Validar intervalos y timeouts al entrar, no dentro del bucle.
4. Mantener el fix de `systemctl --no-legend --plain`.
5. No cerrar aún el cableado provisional del trigger; A3 lo reemplaza.

**Terminado cuando:** tests verdes, muestra real coherente, proceso estable por una
hora y PR integrado en `main`.

#### A2. Crear el esqueleto de paquete y calidad

**Depende de:** A1.  
**Archivos:** `pyproject.toml`, `pruebas/unitarias/conftest.py` y configuración de CI.

Pasos:

1. Declarar Python `>=3.11`, dependencia `requests` y extras de desarrollo con pytest.
2. Configurar pytest para descubrir únicamente `pruebas/unitarias`.
3. Crear un workflow que compile, pruebe y ejecute `bash -n` en cada PR.
4. No configurar publicación de paquetes todavía.

**Terminado cuando:** un clon limpio instala el entorno de desarrollo y CI reproduce
los mismos resultados locales.

#### A3. Resolver #222 y crear `main.py`

**Depende de:** A1–A2.  
**Archivos:** documento maestro §8.4, roadmap/tareas, `doctorjk/main.py`, trigger y tests.

Pasos:

1. Registrar #222 como tarea de cierre de Fase 1 y asignar responsable.
2. Documentar la decisión de “un solo dueño del estado”.
3. Implementar CLI con `--dry-run`, `--auto-fix`, `--once` y nivel de log.
4. Separar `parse_args()`, `build_app()` y `run()` para poder probar sin bucles.
5. Cambiar el trigger al contrato FIFO; no debe corregir, declarar incidentes ni
   repetir la línea cruda del journal en sus propios logs.
6. Abrir el FIFO como lectura/escritura no bloqueante para evitar EOF/bucle ocupado
   cuando el trigger cierre cada escritura.
7. Manejar SIGTERM y cerrar descriptores limpiamente bajo systemd.

**Pruebas obligatorias:** defaults seguros, flags incompatibles, FIFO ausente,
escritura de trigger, SIGTERM y `--once` sin remediación.

**Terminado cuando:** polling y trigger llegan al mismo callback inyectado, el FIFO
no entra en espera ocupada y #222 tiene trazabilidad documental.

#### A4. Normalizar señales (#173)

**Depende de:** A3.  
**Archivos:** `doctorjk/modelos.py`, monitor y `test_normalizacion.py`.

Pasos:

1. Convertir cada snapshot en señales independientes con clave estable por recurso.
2. Representar lectura ausente como error de adquisición, no como valor saludable.
3. Normalizar servicios, disco, memoria y puertos; la carga queda informativa hasta
   que exista un criterio de incidente aprobado.
4. Inyectar umbrales; no leer TOML desde la normalización.

**Terminado cuando:** la salida cumple el contrato de `Signal`, es determinista y las
cuatro señales básicas tienen casos cruzado/no cruzado.

### Gate B — Detector, la ruta crítica

#### B1. Cargar y validar configuración (#175 adelantada)

**Depende de:** A4.  
**Archivos:** `doctorjk/config.py`, `instalador/config.toml.example`, tests.

Pasos:

1. Leer TOML con `tomllib` y secretos solo desde variables de entorno.
2. Validar tipos, rangos, directorios y combinaciones de modo al iniciar.
3. Fallar con mensajes accionables ante clave ausente o desconocida.
4. No registrar tokens ni el contenido de `.env`.

**Terminado cuando:** configuración válida produce `AppConfig`; configuraciones
inválidas fallan antes de iniciar el monitor.

#### B2. Persistencia y máquina de estados (#174, #176)

**Depende de:** B1.  
**Archivos:** `doctorjk/detector.py`, `test_detector.py`.

Pasos:

1. Implementar `normal -> candidate -> incident -> resolved` por `Signal.key`.
2. Incrementar solo muestras consecutivas cruzadas; una lectura sana reinicia el
   candidato y N lecturas sanas resuelven un incidente.
3. Inyectar reloj para que puerto y duración no dependan de sleeps en tests.
4. Emitir eventos de transición; no llamar recolector ni escribir informes.

**Casos:** N-1 no dispara, N dispara una vez, intermitencia reinicia, recuperación,
dos recursos del mismo tipo y una lectura ausente.

#### B3. Deduplicación y decisiones (#177, #178)

**Depende de:** B2.  
**Archivos:** detector y sus tests.

Pasos:

1. Mantener un incidente activo por clave y no volver a emitirlo.
2. Permitir un incidente nuevo solo tras transición completa a resuelto.
3. Registrar señal, contador, estado anterior, nuevo estado y motivo en español.
4. No incluir valores sensibles ni evidencia extensa en el log de decisión.

**Gate de salida B:** cuatro positivos básicos detectados, negativos temporales no
detectados y una ejecución de 24 horas sin falsos positivos antes de declarar Fase 2.

### Gate C — Recolección y privacidad

#### C1. Ventana y comandos de evidencia (#179–#181)

**Depende de:** Gate B.  
**Archivos:** `doctorjk/recolector.py`, fixtures y tests.

Pasos:

1. Recibir un `Incident`; calcular desde −5 min hasta +1 min con timestamps aware.
2. Ejecutar `journalctl`, snapshots y lecturas de historial con argv, timeout y sin
   `shell=True`.
3. Filtrar journal en `warning` o superior; documentar la excepción ya medida para
   caídas systemd en `notice` y decidir si se consulta también la unidad afectada.
4. Limitar búsqueda de configs a rutas aprobadas; no leer contenido de secretos.
5. Ensamblar un `Evidence` con secciones y errores parciales explícitos.

**Terminado cuando:** evidencia parcial sigue siendo utilizable, tarda menos de 30 s
y no hay acoplamiento al detector interno.

#### C2. Truncado y evidencia cruda (#182–#183)

**Depende de:** C1.  
**Archivos:** recolector, `doctorjk/informe.py` o escritor local dedicado, tests.

Pasos:

1. Definir presupuesto por caracteres/tokens estimados y conservar metadatos,
   evento disparador y logs más recientes.
2. Marcar qué se truncó y cuántas líneas se omitieron.
3. Escribir evidencia cruda con creación atómica, modo `600` y nombre asociado al
   incidente; nunca incluirla en Git.
4. Probar disco lleno, permisos insuficientes y colisión de nombres.

#### C3. Sanitizador y pruebas de seguridad (#184–#185)

**Depende de:** C2.  
**Archivos:** `doctorjk/sanitizador.py`, `test_sanitizador.py` y
`docs/sanitizador_limitaciones.md`.

Pasos:

1. Aplicar reemplazo consistente de IPv4/IPv6, URLs con IP y puertos.
2. Redactar asignaciones de PASSWORD/SECRET/KEY/TOKEN, Bearer, JWT, claves SSH,
   rutas de home y rutas conocidas de credenciales.
3. Procesar una copia serializada; no modificar evidencia cruda.
4. Incluir tests adversariales y de no sobre-redacción.
5. Documentar tres o más formatos no cubiertos y el riesgo residual.

**Gate de salida C:** ninguna muestra sensible del corpus de prueba aparece en el
texto que se entregará al cliente LLM; todas las pruebas pasan al 100 %.

### Gate D — Diagnóstico y corte vertical de Modo 1

#### D1. Cliente LLM robusto (#186–#190)

**Depende de:** Gate C.  
**Archivos:** `doctorjk/llm.py`, tests y configuración.

Pasos:

1. Recibir únicamente evidencia ya sanitizada y un prompt; no aceptar `Evidence`
   cruda para hacer imposible saltarse la frontera.
2. Implementar POST OpenAI-compatible con timeout de 30 s.
3. Reintentar solo timeouts, 429, 5xx y respuestas vacías: 1, 2 y 4 segundos.
4. No reintentar 4xx de autenticación/configuración.
5. Validar esquema y contenido antes de devolver texto.
6. Implementar caché de desarrollo con hash de prompt+evidencia sanitizada, sin
   almacenar secretos y con opt-in explícito.
7. Generar fallback local con hechos disponibles cuando se agoten intentos.

**Pruebas:** Cloudflare y DeepSeek simulados, 200 válido, JSON roto, vacío, 401,
429, 500, timeout, secuencia de backoff y fallback.

#### D2. Prompt diagnosticador (#191–#194)

**Depende de:** C3; puede avanzar en paralelo con D1.  
**Archivos:** `prompts/diagnosticador.md`, versiones y evidencia simulada sanitizada.

Pasos:

1. Exigir diagnóstico, cronología, causa raíz con confianza, descartadas y guía.
2. Prohibir inventar datos o afirmar ejecución de comandos.
3. Indicar qué evidencia falta cuando la confianza sea baja.
4. Comparar salida sobre evidencia cruda de laboratorio y sanitizada; solo la
   sanitizada puede enviarse al proveedor durante el producto.
5. Versionar cada cambio evaluado.

#### D3. Informes y rotación (#195, #198)

**Depende de:** D1–D2.  
**Archivos:** `doctorjk/informe.py`, tests.

Pasos:

1. Escribir atómicamente `{timestamp}_{incident_type}.md` y evidencia asociada.
2. Sanitizar tipo y timestamp para impedir traversal.
3. Conservar los 30 informes más recientes junto con su evidencia; nunca separar
   un informe del archivo que lo respalda.
4. Registrar errores de escritura sin perder el diagnóstico en memoria/log.

#### D4. Integración vertical Modo 1

**Depende de:** D1–D3.  
**Archivos:** `main.py` y `test_pipeline.py`.

Pasos:

1. Cablear contratos, no implementaciones internas.
2. Añadir una prueba end-to-end local con subprocess y HTTP simulados.
3. Verificar explícitamente la secuencia cruda -> sanitización -> LLM.
4. Probar proveedor caído y escritura del fallback.

**Hito alfa:** Doctor J/K detecta uno de los cuatro escenarios, genera informe y no
modifica el servidor. Este corte reduce riesgo, pero todavía no es el MVP final.

### Gate E — Servicio e instalación

#### E1. Unidades systemd (#196)

**Depende de:** D4.  
**Archivos:** `instalador/doctorjk.service` y `doctorjk-trigger.service`.

Incluir `User=doctorjk`, `Group=doctorjk`, `Restart=always`, dependencias entre
unidades, directorio de trabajo, archivo de entorno, `RuntimeDirectory`, límites y
hardening compatible con lectura de journal. Validar ambas con
`systemd-analyze verify` y pruebas reales de reinicio independiente.

#### E2. Instalador idempotente (#197)

**Depende de:** E1.  
**Archivos:** `install.sh`, `desinstalar.sh`, plantilla TOML y `.env.example`.

Pasos:

1. Validar Ubuntu/Debian, Python 3.11 y systemd antes de cambiar nada.
2. Crear usuario sin login, `/opt/doctorjk`, `/etc/doctorjk` y almacenamiento.
3. Preservar configuración existente y asegurar secretos con modo `600`.
4. Instalar, habilitar, iniciar y comprobar estado del servicio.
5. Repetir instalación y demostrar que no duplica ni sobrescribe.
6. Desinstalar servicio y binarios conservando informes.

**Gate de salida E:** instalación cronometrada en VPS restaurado, menos de 15 minutos,
Modo 1 por defecto y servicio estable durante una hora.

### Gate F — Modo 2 determinista

#### F1. Scripts comunes y cuatro correcciones (#199)

**Depende de:** Gate E.  
**Archivos:** `scripts-fix/comun.sh` y cuatro `fix_*.sh`.

Cada script valida precondición, soporta `DOCTORJK_DRY_RUN=1`, actúa sobre recursos
predefinidos, verifica resultado, es idempotente y retorna código explícito. El script
de disco usa el tamaño real del VPS y nunca asume 18 GB.

#### F2. Clasificador (#200)

**Depende de:** F1.  
**Archivos:** `doctorjk/clasificador.py` y tests.

Implementar un mapeo exhaustivo de tipos documentados a rutas fijas. Tipo desconocido
retorna “sin remediación”; nunca elige por similitud ni concatena una ruta.

#### F3. Orquestación, auditoría y verificación (#201–#202)

**Depende de:** F2.  
**Archivos:** `doctorjk/remediador.py`, tests.

Ejecutar script con timeout, capturar stdout/stderr/código, verificar postcondición y
agregar auditoría al informe. Ante fallo, detener, marcar escalamiento y no intentar
otro script.

**Gate de salida F:** los cuatro scripts pasan dry-run e idempotencia; disco lleno se
resuelve y verifica en menos de dos minutos en el VPS.

### Gate G — Protocolo de escenarios antes de Modo 3

#### G1. Provocadores y negativos (#203)

**Depende de:** Gate F.  
**Archivos:** nueve escenarios, cinco negativos y tráfico de fondo.

Cada script incluye precondición, duración, restauración y causa esperada. Sustituir
`systemctl stop` por un fallo real cuando el objetivo sea caída inesperada. Ejecutar
solo en el VPS y tomar snapshot antes de escenarios destructivos.

#### G2. Oráculos previos (#204)

Crear nueve archivos con causa real, evidencias mínimas, afirmaciones prohibidas y
guía aceptable antes de ejecutar el primer escenario.

#### G3. Corrida piloto y matriz (#205–#206)

Ejecutar una corrida de cada positivo y negativo para corregir scripts y medición.
Luego ejecutar tres corridas por escenario, 42 en total, con prompt/versiones fijados.
Guardar resultados sin editar y calcular fórmulas desde conteos, no manualmente.

**Gate de salida G:** metas de detección, causa, falsos positivos, tiempo y guía
cumplidas antes de habilitar ejecución generada por LLM.

### Gate H — Modo 3 con cinco salvaguardas

#### H1. Plan estructurado (#207)

**Depende de:** Gate G.  
**Archivos:** `doctorjk/planificador.py`, `prompts/planificador.md`, tests.

Exigir JSON estricto que se convierta a `CorrectionPlan`. Rechazar campos extra,
pasos vacíos, comandos no parseables o planes sin condición de aborto. El texto del
modelo nunca se ejecuta directamente.

#### H2. Lista blanca (#208)

**Depende de:** H1.  
**Archivos:** `doctorjk/lista_blanca.py`, política de ejemplo y tests.

Validar ejecutable, subcomando, número de argumentos, servicio y ruta resuelta.
Rechazar `rm -rf /`, pipes, `;`, sustitución de comandos, redirecciones, globs,
traversal, symlinks fuera de raíz y paquetes arbitrarios. Registrar cada rechazo.

#### H3. Dry-run y doble opt-in (#209–#210)

**Depende de:** H2.  
**Archivos:** `main.py`, remediador, informe y tests.

Dry-run genera y valida todo el plan, escribe “ningún comando fue ejecutado” y no
invoca subprocess. La ejecución real requiere modo configurado y opt-in por
`--auto-fix` o `auto_fix = true`. Una instalación nueva siempre queda en diagnóstico.

#### H4. Ejecutor y aborto (#211–#212)

**Depende de:** H3.  
**Archivos:** `doctorjk/ejecutor.py`, tests.

Por paso: validar -> ejecutar -> capturar -> verificar -> continuar o abortar. Usar
argv, timeout y `check=False` para capturar fallos. Un resultado inesperado detiene
los pasos restantes, no reintenta y deja estado suficiente para escalar.

#### H5. Auditoría completa (#213)

**Depende de:** H4.  
**Archivos:** ejecutor, informe y tests.

Registrar timestamps, argv, salida sanitizada, código, decisión y justificación en
journald e informe. Redactar secretos antes de ambos destinos. Probar que el informe
permite reconstruir la secuencia exacta.

#### H6. Medición (#214)

Ejecutar Modo 3 primero en dry-run para todos los escenarios. Después habilitarlo en
un subconjunto seguro con snapshot disponible y ampliar solo si pasa. Registrar éxito
únicamente cuando la postcondición confirma recuperación. Meta: más de 85 %.

**Gate de salida H:** las cinco salvaguardas tienen tests negativos, ninguna puede
desactivarse por error de configuración y la métrica está respaldada por resultados.

### Gate I — Validación humana, entrega y demo

#### I1. Comprensibilidad (#215)

Seleccionar cinco informes reales y aplicar el mismo guion a 3–5 personas no
administradoras. Guardar respuestas literales sin datos personales, calcular la
métrica e iterar el prompt si no supera 80 %.

#### I2. Documentación operativa (#216–#217)

Crear arquitectura con contratos y flujo, actualizar README con instalación,
configuración, Modos 1–3, lista blanca y troubleshooting. Hacer una prueba de README
con alguien que no haya trabajado en el repositorio.

#### I3. Distribución (#218)

Elegir `.deb` para Ubuntu/Debian; Docker no es apropiado como primera opción porque
el agente necesita acceso local a systemd, journal y filesystem. Construir en ARM64,
incluir licencia propietaria y probar instalación sin clonar el repo. Si se recorta,
registrarlo como deuda explícita y entregar el instalador.

#### I4. Demo y presentación (#219–#220)

Preparar dos escenarios seguros, uno en Modo 1 y otro en Modo 3 dry-run. Generar 3–5
informes reales de respaldo, ensayar dos veces y mantener la demo bajo 10 minutos.

**MVP v0.1 terminado cuando:** todos los gates A–I están documentados como aprobados,
excepto #218 solo si fue recortado de forma explícita; #221 permanece fuera de alcance.

---

## 6. Previsión y paralelismo

Las cifras siguientes son rangos de esfuerzo, no fechas prometidas. Incluyen código,
tests y revisión, pero no esperas de aprobación, cuota del proveedor ni disponibilidad
de participantes externos.

| Gate | Esfuerzo secuencial | Puede avanzar en paralelo | Requiere VPS/personas |
|---|---:|---|---|
| A — Base | 3–5 días | A2 después de acordar contratos | Prueba de 1 hora |
| B — Detector | 5–8 días | Prompt inicial D2 | Prueba de 24 horas |
| C — Evidencia | 5–7 días | D2 con fixtures | Captura de fixtures |
| D — Modo 1 | 5–7 días | D1 y D2 | Llamadas reales al final |
| E — Instalación | 3–4 días | Documentación operativa | Restore e instalación limpia |
| F — Modo 2 | 5–7 días | Oráculos G2 | Cuatro incidentes |
| G — Medición | 5–8 días | Corrección de docs | 42 corridas |
| H — Modo 3 | 8–12 días | H5 prepara esquema tras H1 | Snapshots y corridas seguras |
| I — Cierre | 4–6 días | Docs, paquete y presentación | 3–5 participantes |

El total secuencial es de 43–64 días de ingeniería. Un equipo de tres puede reducirlo
si trabaja sobre contratos ya integrados, pero no debe paralelizar módulos que cambian
el mismo contrato. La estimación original de una semana para Gate H es de alto riesgo:
incluye cinco salvaguardas y medición destructiva. Para conservarla habría que reducir
#221, #218 o la cantidad de corridas aprobada; nunca una salvaguarda.

Orden de camino crítico:

```text
A -> B -> C -> D -> E -> F -> G -> H -> I
         \-> D2 puede iniciar con evidencia simulada
                    \-> G2 puede preparar oráculos antes de F completo
```

Un modelo puede ejecutar código y tests locales. Necesita intervención humana para
aprobar decisiones de producto, restaurar/operar el VPS, aportar credenciales, revisar
PR, calificar informes y realizar la prueba de comprensibilidad.

---

## 7. Orden recomendado de PR y commits

| Orden | Bloque | Commit esperado |
|---|---|---|
| 1 | A1 | `test(monitor): cover system command parsers and failures` |
| 2 | A2 | `chore(test): add package and CI test scaffold` |
| 3 | A3 | `feat(main): add the long-running agent entry point` |
| 4 | A4 | `feat(monitor): normalize system snapshots into signals` |
| 5 | B1 | `feat(config): load and validate TOML configuration` |
| 6 | B2 | `feat(detector): add persistent incident state machine` |
| 7 | B3 | `feat(detector): deduplicate incidents and log decisions` |
| 8 | C1 | `feat(recolector): collect bounded incident evidence` |
| 9 | C2 | `feat(recolector): truncate and persist raw evidence` |
| 10 | C3 | `feat(sanitizador): redact sensitive evidence consistently` |
| 11 | D1 | `feat(llm): add resilient OpenAI-compatible client` |
| 12 | D2 | `feat(prompts): add structured diagnostic prompt` |
| 13 | D3 | `feat(informe): write and rotate incident reports` |
| 14 | D4 | `feat(main): connect the diagnostic pipeline` |
| 15 | E1–E2 | Dos PR: systemd y luego instalador |
| 16 | F1–F3 | Tres PR: scripts, clasificador y orquestación |
| 17 | G1–G3 | Tres PR: escenarios, oráculos y resultados |
| 18 | H1–H6 | Un PR por salvaguarda/capacidad; nunca agrupar las cinco |
| 19 | I1–I4 | PR separados de validación, docs, distribución y demo |

---

## 8. Matriz de riesgos y controles

| Riesgo | Señal temprana | Control | Gate |
|---|---|---|---|
| Pipeline sin dueño | procesos efímeros pierden contadores | un solo `main.py` | A3 |
| Falso positivo | candidato por pico de 20 s | N ciclos + negativos | B/G |
| Evidencia sensible sale | IP/token en payload simulado | frontera de tipo + tests 100 % | C3/D1 |
| LLM no responde | timeout/429/5xx | backoff y fallback | D1 |
| Disco se llena con informes | más de 30 pares | rotación atómica por pares | D3 |
| Script actúa mal | tipo desconocido | mapeo cerrado y verificación | F |
| Plan destructivo | metacaracteres o ruta libre | argv estructurado y allowlist | H2 |
| Ejecución parcial | paso 2 falla | aborto sin reintento | H4 |
| Auditoría filtra secretos | stdout contiene token | sanitización antes de log/informe | H5 |
| Prueba destruye VPS | escenario sin limpieza | snapshot y runbook | G/H |
| Métrica sesgada | esperado escrito después | oráculo previo versionado | G2 |
| Cronograma se atrasa | Gate B o H excede tiempo | recortar #221 y luego #218 | Todos |

---

## 9. Checklist de liberación v0.1

- [ ] `main` contiene el monitor de #171; #223 ya no está pendiente.
- [ ] #222 está cerrado con documento maestro y tareas corregidos.
- [ ] Tests y CI pasan en Python 3.11 sobre un clon limpio.
- [ ] El servicio inicia, reinicia y se detiene sin procesos huérfanos.
- [ ] La instalación nueva queda en Modo 1.
- [ ] La evidencia enviada fue sanitizada; la cruda queda local con modo `600`.
- [ ] Cloudflare y DeepSeek cambian solo mediante configuración.
- [ ] El fallback produce informe cuando el proveedor configurado falla.
- [ ] Los cuatro escenarios básicos y cinco negativos cumplen el detector.
- [ ] Los scripts de Modo 2 son idempotentes y verifican su resultado.
- [ ] Las cinco salvaguardas del Modo 3 tienen tests positivos y negativos.
- [ ] Las 42 corridas y sus oráculos están versionados o el recorte está aprobado.
- [ ] Todas las métricas se calculan desde evidencia, no se declaran de memoria.
- [ ] La prueba de comprensibilidad supera 80 %.
- [ ] Un tercero instala siguiendo únicamente el README en menos de 15 minutos.
- [ ] La demo completa dura menos de 10 minutos y tiene informes de respaldo.
- [ ] No hay `.env`, tokens, IPs reales, rutas de usuario ni evidencia cruda en Git.
- [ ] #221 no entró accidentalmente al alcance.

---

## 10. Primera acción concreta

No comenzar #173 todavía. La primera acción es convertir el PR #223 en una base
integrable: agregar pruebas del monitor, corregir sus bordes, definir el contrato de
eventos del trigger y resolver #222. Solo después existe un proceso estable sobre el
que tenga sentido construir persistencia, recolección y remediación.
