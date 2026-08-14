# `doctorjk/` — el agente

Todo el código del agente que se instala en el servidor vigilado. Es un paquete Python 3.11+
sin más dependencia externa real que un cliente HTTP (`requests` o `httpx`); el resto sale de
la librería estándar y de las herramientas del sistema.

Regla de la carpeta: **un módulo = una etapa del flujo**. El flujo es lineal
(vigilar → detectar → recolectar → sanitizar → diagnosticar → corregir) y los módulos deben
poder probarse por separado, sin necesidad de un servidor roto de verdad.

## Estructura recomendada

```
doctorjk/
├── __init__.py           # versión del paquete
├── main.py               # punto de entrada; parsea --dry-run y --auto-fix
├── config.py             # lee config.toml + variables de entorno
│
├── monitor.py            # muestreo de señales cada 30 s
├── trigger.sh            # detección en tiempo real por journalctl -f
├── detector.py           # confirma incidente por persistencia (N ciclos)
├── recolector.py         # arma la ventana de evidencia (−5 min / +1 min)
├── sanitizador.py        # enmascara IPs, credenciales, tokens y rutas
├── llm.py                # cliente HTTP OpenAI-compatible
├── informe.py            # escribe y rota los informes en disco
│
├── clasificador.py       # tipo de incidente → script de scripts-fix/ (Modo 2)
├── remediador.py         # ejecuta correcciones y deja bitácora de auditoría
├── planificador.py       # Modo 3 — genera el plan de corrección
├── ejecutor.py           # Modo 3 — ejecuta el plan paso a paso con validación
└── lista_blanca.py       # salvaguarda: patrones de comando permitidos
```

## Qué va en cada módulo

| Módulo | Responsabilidad | Referencia |
|---|---|---|
| `main.py` | Arranque del agente y flags de seguridad. Por defecto solo diagnostica | §14.5 |
| `config.py` | Config del TOML; los secretos vienen del entorno, nunca del archivo | §7.1 |
| `monitor.py` | Muestrea servicios, disco, memoria, reinicios y puertos. No decide nada | §5.1 |
| `trigger.sh` | Escucha logs en vivo y dispara el agente ante un error puntual | §5.1 |
| `detector.py` | Convierte candidato en incidente si la condición se sostiene | §5.1, §17.4 |
| `recolector.py` | Logs, snapshot, cambios de 48 h e historial de la máquina | §5.2 |
| `sanitizador.py` | Reemplazo consistente dentro del mismo informe | §5.3 |
| `llm.py` | Un POST; cambiar de proveedor = cambiar 3 variables de entorno | §5.5 |
| `informe.py` | `<timestamp>_<tipo>.md` + `_evidencia.txt` cruda al lado | §5.3, §13 |
| `clasificador.py` | Mapeo explícito, sin ambigüedad | tarea #85 |
| `remediador.py` | Orquesta Modo 2 y Modo 3; registra cada comando y su resultado | §14 |
| `planificador.py` | Plan con comando, resultado esperado, condición de continuar y de abortar | §14.3 |
| `ejecutor.py` | Valida → ejecuta → compara → avanza o aborta | tareas #94, #95 |
| `lista_blanca.py` | Nunca se ejecuta un comando genérico generado libremente | §14.5 |

## Convenciones

- Nombres de módulos y funciones en español, igual que la documentación del proyecto.
- El agente se audita con las mismas herramientas que vigila: `logging` a journald.
- Ningún módulo escribe secretos en disco ni en el log.
- `sanitizador.py` es el último punto por el que pasa la evidencia antes de salir del servidor;
  nada debe poder saltárselo.
