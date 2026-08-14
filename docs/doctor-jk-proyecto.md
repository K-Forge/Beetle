# Doctor J/K — Beetle

**Diagnosticador experto de servidores con inteligencia artificial**

Documento de proyecto — versión 4.0

---

## Índice

1. [Ikigai del proyecto](#1-ikigai-del-proyecto)
2. [Qué es Doctor J/K](#2-qué-es-doctor-jk)
   - [2.1 Buyer persona](#21-buyer-persona)
   - [2.2 Qué justifica cada decisión de arquitectura](#22-qué-justifica-cada-decisión-de-arquitectura)
3. [El problema que resuelve](#3-el-problema-que-resuelve)
4. [La solución](#4-la-solución)
5. [Cómo funciona (desarrollo de la idea)](#5-cómo-funciona-desarrollo-de-la-idea)
   - [5.3 Sanitización de datos sensibles](#53-sanitización-de-datos-sensibles)
6. [Arquitectura](#6-arquitectura)
7. [Stack técnico](#7-stack-técnico)
8. [Qué necesitas antes de empezar](#8-qué-necesitas-antes-de-empezar)
9. [Dónde vive cada cosa](#9-dónde-vive-cada-cosa)
10. [Costos](#10-costos)
11. [Paso a paso de implementación](#11-paso-a-paso-de-implementación)
12. [Diseño del prompt](#12-diseño-del-prompt)
13. [Ejemplo de informe generado](#13-ejemplo-de-informe-generado)
14. [Remediador Automático](#14-remediador-automático)
15. [Escenarios de prueba](#15-escenarios-de-prueba)
16. [Cómo se mide el éxito](#16-cómo-se-mide-el-éxito)
17. [Decisiones de diseño y su justificación](#17-decisiones-de-diseño-y-su-justificación)
18. [Riesgos](#18-riesgos)
19. [Alcance del prototipo](#19-alcance-del-prototipo)
20. [Cronograma](#20-cronograma)
21. [Comparativa de modelos de IA](#21-comparativa-de-modelos-de-ia)
22. [Preguntas frecuentes sobre el proyecto](#22-preguntas-frecuentes-sobre-el-proyecto)
23. [Modelo de producto y distribución](#23-modelo-de-producto-y-distribución)

---

## 1. Ikigai del proyecto

El ikigai es el punto donde se cruzan cuatro preguntas: qué te apasiona, en qué eres bueno, qué necesita el mundo y por qué te pagarían. Doctor J/K nace justo en esa intersección.

### Lo que nos apasiona

Entender por qué se rompen las cosas. Cada incidente de servidor es un rompecabezas con pistas reales — logs, estados, cronologías — esperando a que alguien las conecte. Ese proceso de investigación forense es lo que nos mueve.

### En lo que somos buenos

Somos ingenieros de sistemas. Sabemos leer logs, diagnosticar servicios, navegar la terminal y diseñar la detección. La combinación de conocimiento en infraestructura con la capacidad de integrar un LLM como herramienta de redacción es exactamente donde nuestras habilidades encajan.

### Lo que el mundo necesita

Cuando un servidor falla a las 3 de la mañana, el tiempo que tarda un ingeniero en despertarse, conectarse, entender qué pasó y resolverlo es tiempo de servicio caído. Cada minuto de caída cuesta dinero, reputación y confianza. Las herramientas de monitoreo actuales encienden alarmas y muestran gráficas, pero asumen que quien las recibe ya sabe interpretarlas y ya sabe qué hacer. Doctor J/K cierra esa brecha: reduce el tiempo de diagnóstico de 45 minutos a 90 segundos y, en su modo avanzado, ejecuta la corrección sin intervención humana.

### Por lo que el mundo pagaría

Un ingeniero de sistemas senior cobra entre $40 y $150 por hora por diagnosticar un incidente. Doctor J/K entrega el equivalente funcional de esa consulta — diagnóstico con causa raíz, explicación y pasos de remediación — por centavos de dólar o gratis. Para empresas, la propuesta es más directa: mejorar o mantener los nines de disponibilidad del servicio reduciendo el MTTR (Mean Time To Recovery) sin agregar headcount.

### El cruce

```
                    PASIÓN
            investigación forense
            de incidentes de servidor
                     │
         ┌───────────┼───────────┐
         │           │           │
    HABILIDAD ─── DOCTOR J/K ─── NECESIDAD
   ingeniería de     │         reducir MTTR, mejorar
   sistemas + LLM   │         disponibilidad, aligerar
         │           │         carga de ingenieros
         └───────────┼───────────┘
                     │
                  MERCADO
           diagnóstico + corrección
           automática 24/7
```

---

## 2. Qué es Doctor J/K

Doctor J/K es un **agente que vive dentro de un servidor, detecta cuando algo se rompe, explica qué pasó en lenguaje claro, y opcionalmente lo arregla solo**.

Es un producto de la empresa **Beetle**.

No es un monitor — es un diagnosticador experto con capacidad de corrección. La diferencia: un monitor enciende una alarma y espera a que alguien reaccione. Doctor J/K investiga, explica, guía y (en su modo avanzado) resuelve.

### Para quién es

**Cliente objetivo: PyME tecnológica sin equipo de infraestructura dedicado.**

Perfil:

- Empresa de 5–50 empleados, 1–5 años de operación
- Equipo de infraestructura de 1–3 personas (a veces cero dedicadas — el CTO o fundador técnico es quien apaga los incendios)
- 3–10 servidores Linux (Ubuntu/Debian), típicamente VPS de terceros: DigitalOcean, Hetzner, Linode, o instancias en AWS/Azure/GCP. "Servidor" significa cualquier instancia Linux que requiera vigilancia, sea física o virtual
- Verticales: SaaS, edtech, e-commerce propio
- Mercados: LATAM, Europa del Sur, Sudeste Asiático — donde herramientas enterprise como Datadog ($2,000+/mes) son desproporcionadas frente al presupuesto local
- Sin rotación formal de guardia: "el que esté despierto responde"
- Monitoreo existente parcial (Grafana a medias, alertas sin terminar de configurar)
- Presupuesto de herramientas de infraestructura: $0–200/mes

Decisor de compra: CTO, fundador técnico o el único administrador de sistemas. 28–45 años, formación en ingeniería de sistemas o autodidacta equivalente. Decide en un día: lo prueba él mismo, y si funciona lo instala esa semana. Sin procurement.

Este cliente quiere:

- **Reducir el tiempo de respuesta ante incidentes** — de 45 minutos a menos de 2 minutos
- **Entender qué pasó sin ser experto en infraestructura** — el informe explica en lenguaje accesible
- **Aligerar la carga de los equipos de ingeniería** — el ingeniero recibe el diagnóstico hecho y puede aplicar la solución en minutos en vez de investigar desde cero
- **Mantener o mejorar la disponibilidad del servicio** — la diferencia entre 99.9% y 99.99% es la diferencia entre 8.7 horas de caída al año y 52 minutos
- **Reducir costos operativos** — un incidente resuelto automáticamente a las 3am cuesta centavos en tokens de IA; un ingeniero despertado cuesta $40–150/hora

Un segmento queda deliberadamente fuera de alcance: empresas medianas (50–500 empleados, 20–200 servidores, equipos de 5–20 ingenieros con rotación formal de guardia). Ese cliente requiere vista centralizada, historial consultable, control de acceso y evidencia de compliance — todo fuera del alcance actual. Se menciona como dirección de expansión futura, no como cliente presente.

### Qué NO es

- No es un reemplazo del monitoreo (Datadog, Grafana). Los complementa — ellos miden, Doctor J/K diagnostica y resuelve.
- No es un sistema de auto-healing opaco. Cuando Doctor J/K corrige, deja un registro completo de qué hizo y por qué — auditable, reversible, transparente.
- No es un chatbot. Es un agente autónomo que actúa cuando se dispara un error, sin que nadie tenga que escribirle.

### 2.1 Buyer persona

> Mateo, 32 años, CTO y fundador técnico de una startup SaaS de 15 personas en Bogotá. Tres años de operación, equipo 100% remoto. Es también, de facto, el único que sabe leer un log de PostgreSQL cuando algo se cae.
>
> Corre todo sobre VPS Linux porque AWS le sale caro. Tiene Grafana instalado a medias — nunca terminó de configurar las alertas importantes. Cuando algo se rompe a las 3am, es él quien se despierta. No hay PagerDuty, no hay rotación.
>
> **Qué quiere:** dormir tranquilo sin ignorar producción. No busca otra herramienta de observabilidad — ya tiene Grafana a medias y no quiere reemplazarla. Busca algo que le diga *qué hacer* cuando la alarma suena, no otra alarma más.
>
> **Sus objeciones:**
> - "¿Esto manda mis logs a algún lado?" — necesita saber exactamente qué sale de su servidor
> - "No tengo tiempo de configurar nada complicado" — si la instalación pasa de 15 minutos, lo abandona
> - "¿Y si el modelo se equivoca y me manda a borrar algo?" — por eso el Modo 1 es la puerta de entrada obligatoria
>
> **Cómo decide:** lo prueba él mismo en un servidor de pruebas. Si funciona, va a producción esa semana. Sin comité, sin procurement.

### 2.2 Qué justifica cada decisión de arquitectura

| Decisión | Por qué, dado este cliente |
|---|---|
| Agente instalado localmente, no servicio remoto | Con 3–10 servidores no hace falta orquestación central |
| Informes en `.md` en disco, sin base de datos | Mateo lee el informe y actúa; no necesita historial consultable |
| Instalación en menos de 15 minutos | Su restricción real es tiempo, no dinero |
| Kimi K2.6 vía Cloudflare | Costo de inferencia cercano a cero, asumido por Beetle |
| Modo 1 (solo diagnostica) por defecto | Necesita confiar antes de permitir que el agente actúe |
| Sanitización antes del envío | Sus logs contienen IPs internas, rutas y a veces credenciales |

---

## 3. El problema que resuelve

### 3.1 La brecha entre alerta y acción

Cuando falla un servidor, la información necesaria para entender el fallo **ya existe**. Está en los logs, en el estado del sistema, en el historial de cambios. El problema no es la ausencia de datos: es que están dispersos en cinco lugares distintos y en un formato que requiere experiencia para correlacionar.

Un incidente típico obliga a consultar:

- `journalctl` para los mensajes del sistema
- `systemctl status` para el estado de los servicios
- `df` y `du` para el disco
- `free` y `dmesg` para la memoria
- `/var/log/apt/history.log` para cambios recientes
- Logs propios de cada aplicación

Correlacionar todo eso mentalmente, identificar la causa raíz y decidir la secuencia correcta de remediación es exactamente lo que hace un administrador de sistemas experimentado. Es también lo que tarda 30–60 minutos cada vez.

### 3.2 La brecha entre diagnóstico y corrección

Las herramientas actuales viven en uno de dos extremos:

| Extremo | Ejemplo | Problema |
|---|---|---|
| Solo alerta | Datadog, Grafana, Zabbix | Te dice *qué* está mal, asume que sabes *qué hacer* |
| Auto-remediación ciega | Scripts de auto-healing | Arregla sin explicar, peligroso si se equivoca, no auditable |

Doctor J/K ocupa el punto medio: explica qué pasó, propone la solución paso a paso, y opcionalmente la ejecuta — dejando registro completo de cada acción.

### 3.3 El costo del tiempo muerto

Para una empresa con un SLA de 99.9%, el presupuesto de caída es de 8.7 horas al año. Cada incidente que tarda 45 minutos en resolverse consume el 8.6% de ese presupuesto. Si Doctor J/K reduce ese tiempo a 2 minutos (en modo automático), el mismo incidente consume el 0.4% — una mejora de 20x en consumo de presupuesto de disponibilidad.

---

## 4. La solución

Doctor J/K opera en tres modos, cada uno construido encima del anterior:

### Modo 1 — Diagnosticador (el núcleo)

El agente vigila el servidor en silencio. Cuando algo se rompe, junta toda la evidencia, se la manda a un modelo de IA (Kimi K2.6, vía internet), y genera un informe con dos partes:

- **Diagnóstico:** qué pasó, por qué, en qué orden, escrito para que lo entienda cualquier persona
- **Guía:** los comandos exactos para resolverlo, numerados, con explicación de qué hace cada uno y qué esperar

La persona lee el informe y decide si sigue los pasos.

### Modo 2 — Remediador por scripts (corrección determinista)

Además del informe, el agente identifica el *tipo* de incidente y ejecuta un script de corrección que el equipo escribió y probó de antemano. No improvisa — siempre corre el mismo script probado para el mismo tipo de problema. Es predecible, auditable, y seguro. Cubre los tipos conocidos de incidente.

### Modo 3 — Remediador Automático

El modelo no solo diagnostica sino que genera un plan de corrección específico para ese incidente particular, y el agente lo ejecuta paso a paso con validación. Más flexible que el Modo 2 (cubre incidentes que no tienen script preescrito) pero requiere más salvaguardas. Es diferenciador comercial central del producto, no una fase experimental — su alcance obligatorio y sus salvaguardas se detallan en la sección 14.

```
Vigilancia  →  Detección  →  Recolección  →  Diagnóstico  →  Corrección
   (vigila)     (detecta)     (investiga)     (explica)       (resuelve)
     │              │              │              │               │
   siempre        siempre        siempre        siempre      Modo 2 o 3
```

---

## 5. Cómo funciona (desarrollo de la idea)

### 5.1 Detección: cómo sabe que algo se rompió

Dos mecanismos complementarios:

**Polling (cada 30 segundos):** el agente revisa el estado del sistema y busca transiciones sostenidas:

| Señal | Condición de incidente |
|---|---|
| Servicio systemd | Pasa a `failed` y sigue así tras N ciclos |
| Disco | Cruza umbral y no baja en N ciclos |
| Memoria | Disponible bajo umbral de forma sostenida, u OOM en `dmesg` |
| Proceso | Reinicios en bucle (más de X en Y minutos) |
| Puerto | Puerto esperado deja de escuchar |

**Trigger por bash (tiempo real):** un script escucha logs en vivo (`journalctl -f` filtrado por prioridad de error) y dispara el agente en cuanto aparece una línea de error relevante. Más rápido que el polling para errores puntuales.

El requisito de persistencia (N ciclos en polling) descarta picos normales: un `apt upgrade` satura memoria por 20 segundos y eso no es un incidente. El trigger por bash complementa con inmediatez donde el error es una línea puntual, no un cambio de estado.

### 5.2 La ventana de evidencia

Al disparar un incidente, el agente recorta una ventana temporal alrededor del evento (−5 min a +1 min) y recolecta:

```
1. Metadatos       — timestamp, hostname, tipo de incidente
2. Logs            — journalctl de la ventana, filtrado por prioridad
3. Snapshot        — servicios fallidos, disco, memoria, puertos, carga
4. Cambios         — paquetes y configs modificados en 48h
5. Historial       — incidentes anteriores de esta máquina
```

El punto 5 permite que el sistema detecte patrones: si la máquina ya tuvo tres incidentes de disco, el modelo lo sabe.

### 5.3 Sanitización de datos sensibles

Antes de que la evidencia salga del servidor, pasa por `sanitizador.py`: un módulo que corre entre el recolector y el cliente LLM y enmascara datos sensibles mediante expresiones regulares.

**Qué enmascara:**

| Patrón detectado | Reemplazo |
|---|---|
| Direcciones IP | `[IP_1]`, `[IP_2]` (consistente dentro del mismo informe) |
| Variables con PASSWORD, SECRET, KEY, TOKEN en el nombre | `[REDACTADO]` |
| Tokens tipo Bearer / JWT | `[TOKEN_REDACTADO]` |
| Rutas con nombre de usuario (`/home/usuario/...`) | `/home/[USUARIO]/...` |
| Claves SSH y rutas a archivos de credenciales | `[REDACTADO]` |

**Por qué el diagnóstico no se degrada:** el modelo puede razonar igual sobre `[IP_1]` que sobre la IP real — lo que importa para el diagnóstico es la relación entre eventos, no el valor literal. La consistencia del reemplazo dentro de un mismo informe preserva la capacidad de correlacionar ("las conexiones desde `[IP_1]` fueron rechazadas repetidamente").

**Limitación honesta:** la sanitización por patrones no es exhaustiva. Un dato sensible con formato inesperado puede escaparse. Cubre los casos comunes y verificables, no garantiza cobertura total.

La evidencia cruda (sin sanitizar) queda guardada localmente junto al informe, para que quien opere el servidor pueda inspeccionar exactamente qué se generó y qué versión sanitizada salió.

### 5.4 La fase de diagnóstico

La evidencia se envía a Kimi K2.6 (vía Cloudflare Workers AI, gratis) con un prompt estructurado. Kimi lee la evidencia y genera el informe con diagnóstico + guía de solución. El modelo **no toca el servidor** — solo recibe texto y devuelve texto.

### 5.5 Cómo se comunica el agente con Kimi

No se descarga el modelo. No se instala. No corre en tu infraestructura. Es una petición HTTP:

```python
respuesta = requests.post(
    "https://api.cloudflare.com/client/v4/accounts/{ID}/ai/v1/chat/completions",
    headers={"Authorization": "Bearer TU-TOKEN"},
    json={
        "model": "@cf/moonshotai/kimi-k2.6",
        "messages": [
            {"role": "system", "content": PROMPT_DIAGNOSTICADOR},
            {"role": "user", "content": evidencia_recolectada}
        ]
    }
)
```

La petición sale de tu servidor, viaja por internet hasta los servidores de Cloudflare donde Kimi ya está corriendo en sus GPUs, y vuelve con el diagnóstico redactado. Tarda ~10–15 segundos.

El cliente está diseñado con el formato OpenAI-compatible, así que cambiar de proveedor es cambiar tres variables de entorno:

```bash
DOCTORJK_LLM_BASE_URL=https://api.cloudflare.com/client/v4/accounts/{ID}/ai/v1
DOCTORJK_LLM_MODEL=@cf/moonshotai/kimi-k2.6
DOCTORJK_LLM_API_KEY=...
```

---

## 6. Arquitectura

### 6.1 Componentes

```
┌─────────────────────────────────────────────────────┐
│  SERVIDOR VIGILADO                                  │
│                                                     │
│  ┌───────────────────────────────────────────┐      │
│  │  Agente Doctor J/K (systemd service)      │      │
│  │                                           │      │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐ │      │
│  │  │ Monitor  │→ │ Detector │→ │Recolector│ │      │
│  │  │+ trigger │  └──────────┘  └────┬─────┘ │      │
│  │  │  bash    │                     │       │      │
│  │  └──────────┘               ┌─────▼─────┐ │      │
│  │                             │Sanitizador│ │      │
│  │                             └─────┬─────┘ │      │
│  │                             ┌─────▼─────┐ │      │
│  │                             │  Cliente  │ │      │
│  │                             │    LLM    │ │      │
│  │                             └─────┬─────┘ │      │
│  │                                   │       │      │
│  │                       ┌───────────┴───┐   │      │
│  │                       ▼               ▼   │      │
│  │              ┌─────────────┐  ┌─────────┐ │      │
│  │              │  Informe    │  │Remediador│ │      │
│  │              │  (.md)      │  │(opt.)    │ │      │
│  │              └─────────────┘  └─────────┘ │      │
│  └───────────────────────────────────────────┘      │
└─────────────────────┬───────────────────────────────┘
                      │ HTTPS
          ┌───────────┴───────────┐
          ▼                       ▼
  ┌───────────────┐      ┌────────────────┐
  │  Proveedor    │      │  Backend       │
  │  de LLM       │      │  (opcional)    │
  │               │      │  historial +   │
  │  Cloudflare / │      │  panel web     │
  │  DeepSeek     │      │                │
  └───────────────┘      └────────────────┘
```

### 6.2 Flujo temporal de un incidente

| t | Evento |
|---|---|
| 00:00 | Un servicio pasa a `failed` |
| 00:30 | Monitor detecta el cambio, marca candidato |
| 01:00 | Sigue en `failed` — el detector confirma incidente |
| 01:01 | Recolector ejecuta comandos, arma evidencia (~10k tokens) |
| 01:02 | Sanitizador enmascara IPs, credenciales y rutas antes del envío |
| 01:03 | Cliente LLM hace POST al proveedor |
| 01:12 | Respuesta recibida (~2.5k tokens de diagnóstico + guía) |
| 01:13 | Informe escrito en disco |
| 01:14 | Remediador ejecuta corrección (si está habilitado) |
| 01:45 | Verificación post-corrección completada |

Del fallo al informe: menos de 90 segundos. Del fallo a la corrección verificada: menos de 2 minutos.

---

## 7. Stack técnico

### 7.1 Agente

| Componente | Elección | Justificación |
|---|---|---|
| Lenguaje | Python 3.11+ | Disponible por defecto en Ubuntu/Debian; librerías estándar suficientes |
| Ejecución | systemd service + timer | Nativo, sin dependencias, reinicio automático |
| Trigger | bash + `journalctl -f` | Detección en tiempo real de errores en logs |
| HTTP | `requests` o `httpx` | Única dependencia externa real |
| Configuración | Archivo TOML + variables de entorno | Secretos fuera del archivo de config |
| Logs propios | `logging` a journald | El agente se audita con las mismas herramientas que vigila |
| Sanitización | Expresiones regulares (`re`) | Sin dependencias externas para enmascarar datos sensibles |

### 7.2 Recolección de datos

Todo con herramientas del sistema, sin dependencias:

| Dato | Comando |
|---|---|
| Estado de servicios | `systemctl list-units --failed --no-pager` |
| Logs de la ventana | `journalctl --since ... --until ... -p warning` |
| Disco | `df -h --output=source,pcent,target` |
| Memoria | `free -m` + `dmesg -T \| grep -i oom` |
| Puertos | `ss -tlnp` |
| Carga | `uptime`, `top -bn1 \| head -20` |
| Paquetes | `/var/log/apt/history.log` |
| Configs modificadas | `find /etc -mtime -2 -type f` |

### 7.3 Inferencia (el modelo de IA)

**Aclaración fundamental:** no se descarga, no se instala, no corre en tu infraestructura. Se consume como servicio — una petición HTTP que va por internet.

| Proveedor | Modelo | Endpoint | Costo |
|---|---|---|---|
| Cloudflare Workers AI | Kimi K2.6 | `/accounts/{id}/ai/v1/chat/completions` | Gratis |
| DeepSeek | V4 Flash | `api.deepseek.com/v1` | ~$1.16 por 6 meses |

Los dos hablan formato OpenAI-compatible. Cambiar de proveedor = cambiar 3 variables de entorno.

### 7.4 Backend opcional

| Componente | Elección | Alternativa |
|---|---|---|
| API | Cloudflare Worker | Flask/FastAPI en VPS |
| Almacenamiento | Cloudflare D1 (SQLite) | SQLite local |
| Panel | HTML estático + fetch | — |

### 7.5 Entorno de pruebas

| Componente | Elección |
|---|---|
| Infraestructura | VPS Oracle Always Free (ARM Ampere A1, hasta 4 OCPU / 24 GB RAM / 200 GB disco) |
| SO | Ubuntu Server 24.04 LTS (ARM64) |
| Carga realista | Nginx + Postgres + app + cron |
| Generador de tráfico | `hey` o `wrk` |
| Restauración | Snapshots de Oracle (boot volume backups) |

---

## 8. Qué necesitas antes de empezar

### 8.1 Cuentas (gratis, 15 minutos total)

| Servicio | Para qué | Costo |
|---|---|---|
| **GitHub** | Código fuente del proyecto | $0 |
| **Cloudflare** | Token para consumir Kimi K2.6 vía Workers AI | $0 |
| **Oracle Cloud** | VPS de desarrollo y pruebas con IP pública (propiedad de Brian) | $0 |
| **DeepSeek** (opcional) | Token de respaldo, recarga mínima | ~$1 |

### 8.2 Setup de Cloudflare (una sola vez, 10 minutos)

1. Registrarse en dash.cloudflare.com
2. Ir a AI → Workers AI → aceptar términos
3. Ir a My Profile → API Tokens → crear token con permiso "Workers AI read/write"
4. Copiar Account ID (aparece en la página de Workers AI)
5. Guardar ambos en un archivo `.env`

### 8.3 Entorno de desarrollo

**Entorno de desarrollo (VPS compartido):**

- VPS Oracle Always Free (ARM Ampere A1) — propiedad de Brian
- Ubuntu Server 24.04 LTS (ARM64)
- Acceso SSH para todos los miembros del equipo que necesiten operar en el servidor
- Snapshot de la instancia limpia antes de instalar carga (para restaurar después de pruebas destructivas)

**VPS preparado con carga realista:**

- Nginx sirviendo una app
- PostgreSQL con ~50.000 filas
- Un cron job corriendo cada minuto
- Tráfico de fondo con `hey` o `wrk`

Esto último importa: sin tráfico, los logs están vacíos y los incidentes aparecen obvios. El valor del detector está en encontrar señal entre ruido.

### 8.4 Estructura del repositorio

```
doctor-jk/
├── README.md
├── pyproject.toml
├── doctorjk/
│   ├── __init__.py
│   ├── monitor.py          # muestreo de señales
│   ├── trigger.sh           # detección en tiempo real por bash
│   ├── detector.py          # lógica de incidente
│   ├── recolector.py        # ensamblado de evidencia
│   ├── sanitizador.py       # enmascarado de datos sensibles
│   ├── llm.py               # cliente OpenAI-compatible
│   ├── informe.py           # escritura y rotación
│   ├── remediador.py        # ejecución de correcciones
│   └── config.py
├── prompts/
│   └── diagnosticador.md
├── scripts-fix/
│   ├── fix_disco.sh
│   ├── fix_servicio.sh
│   ├── fix_memoria.sh
│   └── fix_puerto.sh
├── instalador/
│   ├── install.sh
│   └── doctorjk.service
├── demo/
│   ├── 01_servicio_caido.sh
│   ├── 02_disco_lleno.sh
│   ├── ...
│   └── negativos/
├── pruebas/
│   ├── esperados/
│   ├── resultados/
│   └── comprensibilidad/
└── docs/
    └── arquitectura.md
```

---

## 9. Dónde vive cada cosa

| Pieza | Ubicación | Costo |
|---|---|---|
| Código fuente | GitHub (repositorio privado) | $0 |
| Desarrollo y pruebas destructivas | VPS Oracle Always Free (Brian) | $0 |
| Agente en operación | Instalado en el servidor vigilado | $0 |
| Modelo de IA (Kimi K2.6) | Servidores de Cloudflare — petición HTTP | $0 |
| Informes | Disco local del servidor vigilado | $0 |
| Backend + panel (opcional) | Cloudflare Workers, u Oracle Always Free | $0 |

**El agente se instala, no se hospeda.** Debe correr en la máquina que vigila porque necesita acceso local a `journalctl`, systemd y el sistema de archivos.

**El modelo no se instala, no se descarga.** Cloudflare lo tiene corriendo en sus propias GPUs. Doctor J/K solo manda texto y recibe texto.

---

## 10. Costos

### 10.1 Consumo por informe

| Componente | Tokens |
|---|---|
| Logs recortados (~200 líneas) | ~6.000 |
| Snapshot del sistema | ~2.500 |
| Cambios recientes | ~800 |
| Prompt estructurado | ~700 |
| **Entrada total** | **~10.000** |
| **Salida (diagnóstico + guía)** | **~2.500** |

### 10.2 Estimación para 6 meses (550 informes)

Estas cifras corresponden al desarrollo del prototipo. En producción, el costo de inferencia lo asume Beetle como parte del servicio (ver sección 23) — el cliente no gestiona tokens ni cuentas de proveedor de LLM.

| Proveedor | Precio in/out por 1M | Costo total |
|---|---|---|
| Cloudflare Workers AI (Kimi K2.6) | Gratis | **$0** |
| DeepSeek V4 Flash | $0.14 / $0.28 | **$1.16** |

### 10.3 Infraestructura

| Opción | Costo mensual |
|---|---|
| VPS Oracle Always Free (desarrollo + pruebas) | $0 |
| Hetzner CX22 (respaldo para demo si Oracle falla) | ~€4 |

### 10.4 Costo total del proyecto (6 meses)

**Entre $0 y €4/mes.** No requiere GPU, no requiere servidor dedicado, no requiere descargar ningún modelo.

### 10.5 Por qué no se corre Kimi en tu propia máquina

Kimi K2.6 es un modelo de ~1 billón de parámetros. Aunque los pesos son públicos, necesita ~1 TB de memoria de video (VRAM) — 8 a 16 GPUs de datacenter. Eso cuesta $23–46 por hora o ~$25.000 al mes. Consumirlo por API cuesta $0 (Cloudflare) o $1.16 (DeepSeek) por todo el proyecto. No es una cuestión de configuración — es una cuestión de física de memoria.

---

## 11. Paso a paso de implementación

### Fase 0 — Preparación (2 días)

1. Crear repositorio en GitHub con la estructura de carpetas
2. Configurar VPS Oracle Always Free: Ubuntu Server 24.04 ARM64, Ampere A1 (hasta 4 OCPU / 24 GB RAM / 200 GB), acceso SSH para el equipo
3. Tomar snapshot del VPS limpio (boot volume backup en Oracle)
4. Instalar carga realista: Nginx, Postgres con ~50.000 filas, una app, un cron
5. Crear cuenta Cloudflare, obtener account ID y token de Workers AI

### Fase 1 — Monitor + Trigger (3 días)

6. Script Python que cada 30s revisa servicios, disco, memoria, puertos
7. Script bash que escucha `journalctl -f` filtrado por errores
8. Normalizar salidas a un diccionario de señales

**Criterio de avance:** el script corre 1 hora sin errores y produce lecturas coherentes.

### Fase 2 — Detector (2 semanas) ← la parte crítica

9. Contadores de persistencia por señal
10. Umbrales configurables por TOML
11. Lógica de transición: normal → candidato → incidente → resuelto
12. Deduplicación: un incidente activo no vuelve a dispararse
13. Registro de decisiones

**Criterio de avance:** detecta los 4 escenarios básicos y no dispara durante 24h de operación normal con tráfico.

> Esta fase concentra el 80% del riesgo. No pasar a la siguiente hasta que esté sólida.

### Fase 3 — Recolector + Sanitización (5 días)

14. Recorte de ventana temporal en `journalctl`
15. Filtrado por prioridad para controlar el tamaño
16. Ensamblado del bloque de evidencia con secciones etiquetadas
17. Truncado inteligente si excede el presupuesto de tokens
18. Guardar la evidencia cruda junto al informe
19. Sanitización de datos sensibles antes de pasar la evidencia al cliente LLM (`sanitizador.py`)
20. Pruebas del sanitizador: verificar consistencia de reemplazos, casos límite, documentar limitaciones

### Fase 4 — Cliente LLM (2 días)

21. Cliente HTTP contra endpoint OpenAI-compatible
22. Manejo de errores: timeout, rate limit, respuesta malformada
23. Reintentos con backoff exponencial
24. Modo caché para desarrollo
25. Fallback: si el LLM falla, informe mínimo con evidencia cruda

### Fase 5 — Prompt (1 semana, en paralelo)

26. Prompt estructurado con diagnóstico + guía paso a paso
27. Iterar contra evidencia guardada de los escenarios
28. Validar comprensibilidad del lenguaje
29. Ajustar para reducir alucinaciones

### Fase 6 — Persistencia y servicio (3 días)

30. Escritura de informes en `/var/lib/doctorjk/informes/`
31. Unit de systemd con `Restart=always`
32. Script de instalación
33. Rotación de informes

### Fase 7 — Remediador por scripts (1 semana)

34. Scripts bash de corrección para los tipos de incidente conocidos
35. Clasificador de tipo de incidente
36. Logging de auditoría de qué se ejecutó
37. Verificación post-corrección

### Fase 8 — Escenarios realistas y medición (1 semana)

38. Scripts de provocación para cada escenario
39. Respuestas esperadas documentadas
40. 3 corridas por escenario
41. Tabulación de resultados

### Fase 9 — Remediador Automático (Modo 3) — Alcance obligatorio

42. Generador de plan de corrección estructurado
43. [SALVAGUARDA] Lista blanca de comandos permitidos
44. [SALVAGUARDA] Modo --dry-run
45. [SALVAGUARDA] Flag explícito --auto-fix
46. Ejecutor paso a paso con validación
47. [SALVAGUARDA] Aborto automático y escalamiento
48. [SALVAGUARDA] Logging de auditoría del Modo 3
49. Medición de corrección automática (meta: >85%)
50. Prueba de comprensibilidad con usuarios (5 informes a 3–5 personas no técnicas)

**Criterio de avance:** Corrección automática >85%, comprensibilidad >80%, y las 5 salvaguardas implementadas y verificadas.

### Fase 10 — Documentación y entrega (1 semana)

51. Documentación de arquitectura
52. README completo
53. Empaquetado para distribución
54. Preparación de demo
55. Presentación
56. Backend receptor de informes + panel web (opcional)

---

## 12. Diseño del prompt

### Rol

```
Eres un diagnosticador experto de servidores Linux. Tu trabajo es
analizar la evidencia de un incidente y producir un informe con dos
propósitos claros:

1. Que la persona ENTIENDA qué pasó — sin jerga innecesaria, sin
   asumir conocimiento previo. Si mencionas un concepto técnico,
   explícalo en una frase entre paréntesis.
2. Que la persona pueda RESOLVERLO — con pasos exactos, comandos
   copiables y verificación de cada paso.

Escribe como si estuvieras sentado al lado de alguien que sabe usar
la terminal pero no es administrador de sistemas.

Reglas estrictas:
- No inventes información que no esté en la evidencia.
- Si la evidencia es insuficiente, dilo explícitamente.
- Marca cada hipótesis con su nivel de confianza: alta, media, baja.
- No sugieras comandos destructivos (rm -rf, dd, mkfs).
- Cada comando incluye: el comando exacto, qué hace, qué esperar,
  y qué hacer si no funciona.
- Escribe en español, en segunda persona.
```

### Estructura del informe

**BLOQUE 1 — DIAGNÓSTICO (entender)**

| Sección | Contenido |
|---|---|
| Resumen | Una frase en lenguaje cotidiano |
| Cronología | Eventos en orden, con timestamps y explicación |
| Causa raíz | Hipótesis + nivel de confianza + evidencia |
| Descartado | Otras causas consideradas y por qué no encajan |

**BLOQUE 2 — GUÍA DE SOLUCIÓN (resolver)**

| Sección | Contenido |
|---|---|
| Confirmar | 1–2 comandos para verificar la causa |
| Resolver paso a paso | Pasos numerados: comando, explicación, resultado esperado, qué hacer si falla |
| Verificar | Comando para confirmar que se resolvió |
| Prevenir | Cambio de configuración con los comandos para implementarlo |

---

## 13. Ejemplo de informe generado

Escenario: cascada (disco lleno → Postgres muere → app da 500):

```markdown
# Informe de incidente — servidor app-prod-01
Fecha: 2026-08-04 23:47 | Confianza: ALTA

---

## DIAGNÓSTICO

### ¿Qué pasó?
Tu aplicación web dejó de funcionar porque la base de datos se
apagó. La base de datos se apagó porque el disco duro se llenó
por completo. El disco se llenó porque un programa estaba
guardando mensajes de depuración sin límite durante tres días.

En resumen: logs sin límite → disco lleno → base de datos muerta
→ aplicación caída.

### Cronología
- 21 ago, 08:15 — Se activó el modo debug en la aplicación
- 23 ago, ~20:00 — El archivo de logs llegó a 15 GB
- 23 ago, 23:41 — Disco al 100%
- 23 ago, 23:42 — PostgreSQL se apagó: "No space left on device"
- 23 ago, 23:42 — La aplicación empezó a dar errores 500
- 23 ago, 23:47 — Doctor J/K detectó el incidente

### Causa raíz (confianza: alta)
El archivo /var/log/miapp/debug.log creció hasta 15.2 GB porque
el modo debug estaba activado sin rotación de logs.

### Causas descartadas
- Ataque o tráfico excesivo: logs de Nginx normales
- Fallo de hardware: dmesg sin errores de I/O
- Actualización rota: sin cambios de paquetes en 48h

---

## GUÍA DE SOLUCIÓN

### Paso 1 — Confirmar que el disco está lleno
    df -h
Busca la línea /dev/sda1. Si dice 100%, confirmamos.

### Paso 2 — Liberar espacio
    sudo rm /var/log/miapp/debug.log
Borra el archivo de 15 GB (son mensajes de depuración, no datos).
Verificación: `df -h` debe mostrar espacio libre ahora.

### Paso 3 — Reiniciar la base de datos
    sudo systemctl restart postgresql
Verificación: `sudo systemctl status postgresql` → "active (running)"

### Paso 4 — Verificar la aplicación
Abre tu sitio en el navegador. Debe cargar normalmente.

### Paso 5 — Prevenir
5a. Desactivar debug: cambiar `debug = true` a `debug = false`
5b. Configurar logrotate para limitar los archivos a 500 MB
```

---

## 14. Remediador Automático

### 14.1 Qué es

Es el componente del alcance del producto donde Doctor J/K no solo diagnostica y propone, sino que **ejecuta la corrección** — siempre bajo las salvaguardas obligatorias de la sección 14.5. No es una fase experimental: es un diferenciador comercial central (ver sección 23). El objetivo de negocio es claro: que un incidente a las 3am se resuelva sin despertar a nadie, reduciendo el MTTR a menos de 2 minutos y manteniendo los nines de disponibilidad del servicio.

### 14.2 Por qué importa

| Situación | Sin Remediador | Con Remediador |
|---|---|---|
| Incidente a las 3am | Ingeniero se despierta, se conecta, investiga, resuelve (~45 min) | Doctor J/K detecta, diagnostica, corrige, verifica (~2 min) |
| Costo del incidente | $40–150/hora de ingeniero | Centavos en tokens de IA |
| Impacto en SLA | 45 min de caída = 8.6% del presupuesto de 99.9% | 2 min de caída = 0.4% |
| Desgaste del equipo | Alto — rotación de guardia, burnout | Bajo — solo escalan los casos que el agente no resuelve |

### 14.3 Dos opciones de implementación

#### Opción A — Modelo único (un solo modelo hace todo)

El mismo modelo que diagnostica genera los comandos de corrección y el agente los ejecuta.

```
Incidente detectado
    → evidencia al modelo (~10k tokens entrada)
    → modelo devuelve diagnóstico + plan de corrección (~4k salida)
    → agente valida cada comando contra lista blanca
    → ejecuta paso a paso, capturando resultado
    → manda resultado al modelo para verificación (~3k in, ~1k out)
    → modelo confirma si se resolvió o sugiere siguiente acción
```

**Consumo por incidente:** ~15k tokens entrada + ~5k salida (dos llamadas al modelo).

**Costos con modelo único (550 incidentes en 6 meses: 8.25M input + 2.75M output):**

| Modelo | Precio in/out | Costo 6 meses |
|---|---|---|
| Kimi K2.6 (Cloudflare) | Gratis | **$0** |
| DeepSeek V4 Flash | $0.14 / $0.28 | **$1.93** |
| Grok 4.5 | $2.00 / $6.00 | **$33.00** |
| Claude Sonnet 5 | $2.00 / $10.00 (intro) | **$44.00** |
| Kimi K3 | $3.00 / $15.00 | **$66.00** |

#### Opción B — Dupla de modelos (planificador + ejecutor)

Un modelo inteligente genera el plan, y un modelo barato lo ejecuta paso a paso. La lógica: planificar la corrección correcta requiere inteligencia (correlacionar causas, decidir la secuencia). Ejecutar el plan solo requiere seguir instrucciones literales ("corre este comando, lee el resultado, decide si sigues").

```
Incidente detectado
    │
    ▼
PLANIFICADOR (modelo inteligente, 1 llamada)
    Recibe: evidencia completa (~10.7k tokens)
    Devuelve: diagnóstico + plan estructurado (~4k tokens)
    El plan incluye por cada paso:
      - comando exacto
      - resultado esperado
      - condición para continuar
      - condición para abortar
    │
    ▼
EJECUTOR (modelo barato, ~6 llamadas)
    Recibe: el plan + resultado del paso actual (~2k tokens)
    Devuelve: decisión (seguir / reintentar / abortar) (~500 tokens)
```

**Consumo por incidente:**
- Planificador: 10.7k entrada + 4k salida × 1 llamada
- Ejecutor: 12k entrada + 3k salida (total, ~2k × 6 pasos)

**Sobre 550 incidentes:**
- Planificador: 5.9M input + 2.2M output
- Ejecutor: 6.6M input + 1.65M output

**Presupuesto alto — ~$52:**

| Rol | Modelo | Precio in/out | Costo 6 meses |
|---|---|---|---|
| Planificador | **Kimi K3** | $3.00 / $15.00 | $50.66 |
| Ejecutor | **Kimi K2.6** (Cloudflare) | Gratis | $0 |
| | | **Total** | **$50.66** |
| *Alternativa ejecutor* | *DeepSeek V4 Flash* | *$0.14 / $0.28* | *$1.39* |
| | | *Total alternativo* | *$52.05* |

El mejor planificador del mercado combinado con un ejecutor gratis o casi gratis.

**Presupuesto medio — ~$20:**

| Rol | Modelo | Precio in/out | Costo 6 meses |
|---|---|---|---|
| Planificador | **Grok 4.5** | $2.00 / $6.00 | $25.00 |
| Ejecutor | **Kimi K2.6** (Cloudflare) | Gratis | $0 |
| | | **Total** | **$25.00** |
| *Alternativa ejecutor* | *DeepSeek V4 Flash* | *$0.14 / $0.28* | *$1.39* |
| | | *Total alternativo* | *$26.39* |

Grok 4.5 es el modelo más eficiente en tokens por tarea — planes concisos y precisos.

**Presupuesto bajo — ~$1.39:**

| Rol | Modelo | Precio in/out | Costo 6 meses |
|---|---|---|---|
| Planificador | **Kimi K2.6** (Cloudflare) | Gratis | $0 |
| Ejecutor | **Kimi K2.6** (Cloudflare) | Gratis | $0 |
| | | **Total** | **$0** |
| *Alternativa ejecutor* | *DeepSeek V4 Flash* | *$0.14 / $0.28* | *$1.39* |
| | | *Total alternativo* | *$1.39* |

Kimi K2.6 gratis es el #8 de la tabla general de calidad — mejor que 12 modelos de pago.

### 14.4 Tabla comparativa: Opción A vs Opción B

| | Opción A (modelo único) | Opción B (dupla) |
|---|---|---|
| Simplicidad | Más simple — un solo cliente | Dos clientes, enrutamiento |
| Costo mínimo | $0 (Kimi K2.6 free) | $0 (Kimi K2.6 free para ambos) |
| Costo con premium | $66 (Kimi K3) | $50.66 (K3 planifica, K2.6 ejecuta gratis) |
| Ahorro de la dupla vs único | — | ~24% menos con K3, ~26% menos con Grok |
| Calidad del plan | Depende del modelo elegido | Siempre el mejor modelo disponible |
| Calidad de ejecución | Misma que el plan | Puede ser menor sin problema |
| Esfuerzo de desarrollo | Base | +1 semana adicional |
| Cuándo elegir | Presupuesto bajo o prototipo rápido | Producción donde el plan importa más que el ahorro |

### 14.5 Salvaguardas obligatorias

Sin importar qué opción se elija:

- **Lista blanca de comandos:** solo se ejecutan patrones validados (reiniciar servicio, borrar logs en rutas específicas, liberar espacio en directorios predefinidos). Nunca comandos genéricos generados libremente.
- **Modo `--dry-run`:** muestra qué haría sin ejecutar. Obligatorio durante desarrollo y demo.
- **Logging de auditoría:** cada comando ejecutado, su resultado, y la decisión del modelo quedan en el informe final.
- **Aborto automático:** si cualquier paso produce un resultado inesperado, el remediador se detiene y escala (notifica, deja el informe, no sigue).
- **Flag explícito:** el remediador solo se activa con `--auto-fix` o configuración explícita. Por defecto, Doctor J/K solo diagnostica.

---

## 15. Escenarios de prueba

### 15.1 Escenarios básicos

| # | Escenario | Provocación |
|---|---|---|
| 1 | Servicio caído | `systemctl stop postgresql` |
| 2 | Disco lleno | `fallocate -l 18G /tmp/relleno` |
| 3 | Memoria agotada | Script que reserva RAM hasta OOM |
| 4 | Puerto ocupado | `nc -l 5432` antes de arrancar Postgres |

### 15.2 Escenarios realistas

| # | Escenario | Provocación | Por qué es difícil |
|---|---|---|---|
| 5 | Disco lleno por logs | Debug sin logrotate | La causa es de hace horas |
| 6 | Fuga de memoria | RAM lenta hasta OOM | Fallo gradual |
| 7 | **Cascada** | Disco → Postgres → app → Nginx | Tres fallos, una causa |
| 8 | Config rota | Modificar `pg_hba.conf` | Causa en archivo, no en log |
| 9 | Puerto secuestrado | Otro proceso toma el 5432 | Síntoma no dice la causa |

### 15.3 Casos negativos (NO debe dispararse)

| # | Escenario |
|---|---|
| N1 | Pico de CPU por `apt upgrade` |
| N2 | Reinicio programado de un servicio |
| N3 | Pico de tráfico con `hey` |
| N4 | Rotación de logs nocturna |
| N5 | Backup programado |

### 15.4 Condiciones

Todas las pruebas deben correr **con tráfico de fondo**.

---

## 16. Cómo se mide el éxito

| Métrica | Definición | Meta |
|---|---|---|
| Tasa de detección | Incidentes detectados / provocados | > 90% |
| Precisión de causa raíz | Informes con causa correcta | > 80% |
| Tasa de falsos positivos | Disparos en escenarios negativos | < 10% |
| Tiempo a informe | Del fallo al archivo escrito | < 120 s |
| Utilidad de la guía | Guías que resuelven el problema | > 70% |
| Comprensibilidad | Personas no expertas que entienden | > 80% |
| Corrección automática | Remediaciones exitosas | > 85% |

**Protocolo:** 42 corridas controladas (9 escenarios × 3 + 5 negativos × 3), con causa raíz definida antes de ejecutar cada escenario.

**Prueba de comprensibilidad:** 5 informes a 3–5 personas que no son administradores de sistemas. ¿Entendieron qué pasó? ¿Podrían seguir los pasos?

---

## 17. Decisiones de diseño y su justificación

### 17.1 El LLM no ejecuta nada (Modo 1 y 2)

El modelo solo redacta. La corrección la hacen scripts probados por el equipo. Esto delimita la responsabilidad y elimina el riesgo de alucinación destructiva.

### 17.2 El Remediador Automático (Modo 3) tiene salvaguardas

Cuando el modelo sí genera comandos, estos pasan por lista blanca, validación, modo dry-run, y aborto automático ante resultados inesperados. Es la versión responsable de auto-healing.

### 17.3 El agente vive en la máquina vigilada

El diagnóstico requiere acceso local a `journalctl`, systemd y el sistema de archivos. Hacerlo remotamente exigiría SSH desde una máquina central — un punto de compromiso peor que el problema que resuelve.

### 17.4 Detección por persistencia, no por umbral instantáneo

Reduce falsos positivos intercambiando unos segundos de latencia por una reducción grande de ruido.

### 17.5 Informe como herramienta educativa

Cada informe explica conceptos, no solo los nombra. La persona que lo lee hoy debería necesitar menos a Doctor J/K para el mismo problema mañana.

### 17.6 Sanitización antes del envío

Los logs contienen IPs, rutas internas y a veces credenciales. Versiones anteriores de este documento resolvían esto con un modo de modelo local; se descartó por alcance y foco de producto, no porque fuera técnicamente inviable (ver pregunta de privacidad en la sección 22). En su lugar, el módulo `sanitizador.py` (detalle completo en la sección 5.3) enmascara los datos sensibles antes de que la evidencia salga del servidor — reduce el riesgo de fuga sin sacrificar la simplicidad de mantener un único par de backends de inferencia.

---

## 18. Riesgos

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| Falsos positivos excesivos | Alta | Alto | 2 semanas en el detector + casos negativos |
| Modelo alucina causas o comandos | Media | Alto | Niveles de confianza, sección "Descartado", lista blanca, auditoría |
| Guías incomprensibles | Media | Alto | Prueba de comprensibilidad, iteración del prompt |
| Proveedor de LLM cambia límites | Media | Medio | 2 backends intercambiables (antes 3 con Ollama; mitigación más débil sin respaldo local) |
| Falla la red durante demo | Media | Alto | Informes pregenerados. Ya no hay modo offline de respaldo (se eliminó el modo Ollama local) |
| Oracle recorta free tier o reclama la instancia | Media | **Alto** | Snapshots frecuentes exportables. Si se pierde la instancia, se recrea en Oracle (cada miembro puede crear su propia cuenta free) o se migra a Hetzner CX22 (~€4/mes) |
| Dependencia de un solo VPS compartido | Media | Alto | Si el VPS de Brian se pierde (Oracle reclama la instancia, error de configuración, cuenta comprometida), el equipo pierde el entorno de desarrollo completo. Mitigación: snapshots frecuentes (al menos antes de cada fase), y que cada miembro del equipo tenga su propia cuenta de Oracle Always Free como respaldo |
| Cascada no se resuelve bien | Media | Medio | Se reporta como limitación si falla |
| Modo 3 obligatorio sobrecarga la Fase 9 | Media | Alto | Incluir el Remediador Automático en el alcance obligatorio aumenta la carga de la Fase 9 y reduce el margen de maniobra si la Fase 2 (Detector) se atrasa. Se prioriza sobre extensiones opcionales (backend, panel) si hay que recortar |

---

## 19. Alcance del prototipo

### Dentro del alcance

- Agente detectando 9 escenarios (4 básicos + 5 realistas)
- Trigger bash en tiempo real
- Informes con diagnóstico + guía paso a paso
- Sanitización de datos sensibles antes de cualquier envío externo
- Remediador por scripts (Modo 2)
- Remediador Automático con modelo (Modo 3), con las salvaguardas de la sección 14.5
- Dos backends de LLM intercambiables
- Batería de pruebas con métricas
- Prueba de comprensibilidad
- Script de instalación

### Fuera del alcance (trabajo futuro)

- Modo de modelo local (Ollama) — descartado para esta versión, no pendiente
- Panel web con historial
- Notificaciones por correo o Telegram
- Soporte para distribuciones no systemd
- Detección de incidentes de red
- Correlación entre múltiples servidores
- Integración con Graphify para diagnóstico de bugs de código
- Control de licencias por API key contra backend de Beetle (ver sección 23)

---

## 20. Cronograma

| Semana | Trabajo |
|---|---|
| 1 | Fase 0 + Fase 1 — entorno, monitor y trigger bash |
| 2–3 | Fase 2 — detector (la parte crítica) |
| 4 | Fase 3 + Fase 4 — recolector, sanitización y cliente LLM |
| 5 | Fase 5 — prompt (paralelizable desde semana 3) |
| 6 | Fase 6 — persistencia y servicio systemd |
| 7 | Fase 7 — remediador por scripts |
| 8 | Fase 8 — escenarios de prueba y medición |
| 9 | Fase 9 — Remediador Automático (obligatorio) + prueba de comprensibilidad |
| 10 | Fase 10 — documentación, empaquetado y entrega |

El detector concentra el riesgo técnico. Si se atrasa, se recorta la semana 9 — pero el Remediador Automático ya no es opcional, así que lo primero en recortarse ahí son las extensiones opcionales (backend, panel), no la 7 ni la 8. Ver riesgo de cronograma en la sección 18.

---

## 21. Comparativa de modelos de IA

Base del cálculo: 550 informes en 6 meses. 5.5M tokens input + 1.375M output (modo diagnóstico). Presupuesto máximo: $80 en 6 meses.

Ordenados del mejor al peor en calidad para Doctor J/K (lectura de logs, correlación de causas, redacción estructurada, generación de comandos correctos):

| # | Modelo | Precio in/out por 1M | Gratis o pago | Costo 6 meses | Calidad |
|---|---|---|---|---|---|
| 1 | **Kimi K3** | $3.00 / $15.00 | Pago | $37.13 | Excepcional — 93.4% SWE-bench (Vals AI), #1 Arena.ai Frontend |
| 2 | **Claude Opus 5** | $5.00 / $25.00 | Pago | $61.88 | Excepcional — 1,861 Elo GDPval-AA v2, top en tareas agénticas |
| 3 | **GPT-5.5** | $5.00 / $30.00 | Pago | $68.75 | Excepcional — 88.7% SWE-bench Verified |
| 4 | **Claude Opus 4.8** | $5.00 / $25.00 | Pago | $61.88 | Excepcional — 88.6% SWE-bench, probado en producción |
| 5 | **Claude Sonnet 5** | $2.00 / $10.00 (intro) | Pago | $24.75 | Excelente — 85.2% SWE-bench, mitad de precio de Opus |
| 6 | **Grok 4.5** | $2.00 / $6.00 | Pago | $19.25 | Excelente — 83.3% Terminal-Bench, el más eficiente en tokens |
| 7 | **Gemini 3.1 Pro** | $2.00 / $12.00 | Pago | $27.50 | Excelente — ~80.6% SWE-bench, 1M contexto |
| 8 | **Kimi K2.6** | $0.95 / $4.00 (Moonshot) | **Gratis** vía Cloudflare / NIM | **$0** / $10.73 | Excelente — 80.2% SWE-bench, políglota en DevOps |
| 9 | **MiniMax M3** | $0.60 / $2.40 | Pago | $6.60 | Excelente — 80.5% SWE-bench, mejor ratio calidad/precio de pago |
| 10 | **Qwen3.7 Max** | $1.25 / $3.75 | Pago | $12.03 | Excelente — 80.4% SWE-bench, precio promocional |
| 11 | **Qwen3.8 Max** | $2.00 / $6.00 | Pago | $19.00 | Muy buena — 2.4T MoE, sin benchmarks independientes aún |
| 12 | **GLM-5.2** | $1.40 / $4.40 | Pago | $13.75 | Muy buena — top open en AA Intelligence Index, MIT |
| 13 | **DeepSeek V4 Pro** | $0.435 / $0.87 | Pago | $3.59 | Muy buena — sólido, precio excelente |
| 14 | **Claude Haiku 4.5** | $1.00 / $5.00 | Pago | $12.38 | Buena — rápido y barato, pierde en cascadas complejas |
| 15 | **GLM-4.7 Flash** | Gratis | **Gratis** | **$0** | Buena — fuerte en código, débil en narrativa larga |
| 16 | **DeepSeek V4 Flash** | $0.14 / $0.28 | Pago | $1.16 | Buena — el modelo capaz más barato del mercado |
| 17 | **Mistral Small 4** | $0.15 / $0.60 | Pago | $1.65 | Buena — data residency EU, compliance GDPR |
| 18 | **Qwen3.6 Flash** | $0.19 / $1.13 | Pago | $2.60 | Buena — útil para clasificación rápida |
| 19 | **Llama 4 Scout** | Varía por host | **Gratis** vía Groq | **$0** | Aceptable — sigue formato pero correlaciona peor |

Todos caben en el presupuesto de $80. El motor principal recomendado (Kimi K2.6 #8, gratis) tiene mejor calidad que 12 modelos de pago.

---

## 22. Preguntas frecuentes sobre el proyecto

**¿No es lo mismo que Datadog o Grafana?**
No. Ellas muestran métricas para expertos. Doctor J/K explica qué pasó y cómo resolverlo para cualquier persona. Además, son herramientas pesadas que requieren infraestructura propia — Doctor J/K es un binario que se instala en 2 minutos.

**¿Qué pasa si el modelo se equivoca?**
En Modo 1 y 2, no importa: el informe se lee y se descarta; la corrección la hacen scripts probados. En Modo 3, cada comando pasa por lista blanca y validación, y el remediador aborta ante cualquier resultado inesperado.

**¿No es solo un wrapper de un LLM?**
El LLM es el 5% del código. El aporte está en tres capas: detección (distinguir incidente de pico normal), recolección (la evidencia correcta en la ventana correcta), y diseño del prompt (formato comprensible y accionable). Un LLM con evidencia equivocada produce un informe equivocado con mucha seguridad.

**¿Y la privacidad de los logs?**
La evidencia sí se envía a un proveedor externo (Cloudflare o DeepSeek), pero antes pasa por el módulo de sanitización (`sanitizador.py`, ver sección 5.3): enmascara IPs, credenciales, tokens y rutas con nombre de usuario. Solo se envían logs de sistema recortados a la ventana temporal del incidente (−5 min a +1 min) — nunca datos de aplicación ni contenido de bases de datos. La evidencia cruda, sin sanitizar, queda guardada localmente en el servidor vigilado para que quien la opera pueda inspeccionarla. La sanitización por patrones no es exhaustiva — cubre los casos comunes, no garantiza cobertura total.

**¿Escala a muchos servidores?**
El agente es independiente por máquina — escala horizontalmente sin coordinación. La correlación entre servidores es trabajo futuro.

**¿Cuánto cuesta operarlo?**
Motor principal (Cloudflare con Kimi K2.6): $0. Fallback (DeepSeek V4 Flash): ~$0.002 por informe. Hardware: el servidor ya existe — Doctor J/K solo se instala ahí.

**¿Por qué no se corre el modelo en nuestro servidor?**
Kimi K2.6 necesita ~1 TB de memoria de video. No es un problema de configuración — es una cuestión de física. Consumirlo vía API cuesta $0; correrlo tú cuesta ~$25.000/mes. El modelo es exactamente el mismo.

**¿Qué pasa si Cloudflare cambia el free tier?**
Cambias una variable de entorno y el agente funciona con otro proveedor. Por eso diseñamos el cliente con formato OpenAI-compatible desde el día uno.

---

## 23. Modelo de producto y distribución

### Naturaleza del producto

Doctor J/K es código cerrado y propietario. Se distribuye como paquete instalable o imagen Docker, no como código fuente. La propiedad intelectual pertenece a Beetle.

### El acceso al LLM es parte del servicio

El cliente no necesita cuenta propia de Cloudflare ni gestionar tokens de API. Beetle provee el acceso al modelo como parte del producto. Esto simplifica radicalmente la instalación (coherente con la expectativa de <15 minutos) y elimina una barrera de adopción, pero traslada el costo de inferencia a Beetle — un costo que hoy es cercano a cero gracias a Cloudflare Workers AI, y que debe monitorearse si el free tier cambia.

### Modelo de precio

- Prueba gratuita: hasta 5 servidores durante 30 días, funcionalidad completa
- Después del periodo de prueba: modelo de pago por servidor/mes

Se rechaza explícitamente el modelo de precio por incidente: penaliza a quien más problemas tiene, que es justamente quien más necesita la herramienta.

**Nota sobre el prototipo:** el control de licencias (API key con límite de servidores verificado contra un backend de Beetle) es la implementación seria de este modelo de precio, pero queda fuera del alcance del prototipo (ver sección 19). En esta versión el límite es honor system — se documenta la intención comercial sin implementar el mecanismo de control.

### Riesgo de adopción

| Expectativa del cliente | Tensión con código cerrado | Cómo se aborda |
|---|---|---|
| Prefiere código auditable antes de dar acceso a producción | El código no es inspeccionable | Transparencia operativa: cada acción del agente queda registrada en journald y en el informe. El comportamiento es auditable aunque el código no lo sea |
| Descubre herramientas vía GitHub, Hacker News, r/sysadmin | Esos canales favorecen proyectos abiertos | Requiere estrategia de distribución distinta: contenido técnico, demos públicas, documentación abierta aunque el código no lo sea |
| Desconfía de cajas negras | Un agente cerrado con acceso a logs y capacidad de ejecutar comandos es exactamente eso | Modo 1 por defecto (no ejecuta nada), `--dry-run` disponible, lista blanca de comandos documentada públicamente |

Esta tensión es un riesgo real de adopción para el buyer persona descrito en la sección 2.1 — Mateo desconfía de cajas negras por naturaleza. No es un detalle resuelto; es algo que la estrategia de distribución y la transparencia operativa deben seguir trabajando activamente.

### Diferenciadores del producto

1. Diagnóstico en lenguaje accesible, no solo alertas
2. Remediación auditable — registro completo de qué hizo y por qué
3. Precio accesible frente a herramientas enterprise
4. Instalación en menos de 15 minutos
5. Sanitización de datos sensibles antes de cualquier envío externo

### Repositorio

El repositorio de código permanece privado. Si se publica un repositorio de showcase para portafolio, contiene documentación, arquitectura, capturas e informes de ejemplo — nunca el código fuente del agente.

---

*Documento de proyecto — Beetle / Doctor J/K*
*Versión 4.0 — Agosto 2026*
