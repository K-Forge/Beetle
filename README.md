# Beetle

Agente de diagnóstico y corrección automática de incidentes de servidor, potenciado por IA.

El producto se llama **Doctor J/K**. Vive dentro del servidor vigilado, detecta cuando algo se
rompe, explica qué pasó en lenguaje claro y — en su modo avanzado — lo corrige solo.

## Estructura del repositorio

```
Beetle/
├── doctorjk/            # el agente: un módulo por etapa del flujo
├── prompts/             # prompts del modelo, versionados aparte del código
├── scripts-fix/         # correcciones deterministas del Modo 2
├── instalador/          # install.sh y unidad systemd
├── demo/                # escenarios que provocan incidentes
│   └── negativos/       # casos ruidosos que NO deben disparar el agente
├── pruebas/             # verificación y medición contra las metas
│   ├── unitarias/       # pytest
│   ├── esperados/       # causa raíz definida antes de cada corrida
│   ├── resultados/      # informes generados + matriz de medición
│   └── comprensibilidad/# retroalimentación de personas no expertas
└── docs/                # documento de proyecto, roadmap y tareas
```

Cada carpeta tiene su propio `README.md` con qué va dentro, la estructura de archivos recomendada
y las convenciones que debe respetar.

## Por dónde empezar

| Si vas a… | Lee |
|---|---|
| Entender el proyecto completo | [docs/doctor-jk-proyecto.md](docs/doctor-jk-proyecto.md) |
| Saber qué toca ahora | [docs/doctor-jk-roadmap.md](docs/doctor-jk-roadmap.md) y [docs/doctor-jk-tareas.md](docs/doctor-jk-tareas.md) |
| Escribir código del agente | [doctorjk/README.md](doctorjk/README.md) |
| Iterar el prompt | [prompts/README.md](prompts/README.md) |
| Probar y medir | [pruebas/README.md](pruebas/README.md) y [demo/README.md](demo/README.md) |

## Estado

Estructura del repositorio creada (tarea #49). Sin código todavía — la Fase 1 arranca por
`monitor.py` y `trigger.sh`.

## Los tres modos

| Modo | Qué hace | Estado |
|---|---|---|
| 1 — Diagnosticador | Detecta, investiga y explica. No toca el servidor | El núcleo; por defecto |
| 2 — Remediador por scripts | Ejecuta un script probado según el tipo de incidente | Fase 7 |
| 3 — Remediador automático | El modelo genera el plan y el agente lo ejecuta con validación | Fase 9; diferenciador comercial |

Los Modos 2 y 3 solo se activan con configuración explícita (`--auto-fix`). Por defecto,
Doctor J/K únicamente diagnostica.
