# `pruebas/resultados/` — informes generados y matriz de medición

La salida cruda de cada corrida, tal como la produjo el agente, más la tabla que resume las 42
corridas del protocolo.

Los informes se guardan sin editar. Un informe malo es tan valioso como uno bueno: es lo que
justifica la siguiente iteración del prompt o del detector.

## Estructura recomendada

```
resultados/
├── matriz_resultados.md          # tabla consolidada de las 42 corridas
├── 2026-08-20_v1/                # una carpeta por tanda, con la versión de prompt usada
│   ├── 01_servicio_caido_run1.md
│   ├── 01_servicio_caido_run2.md
│   ├── 07_cascada_run1.md
│   └── N1_pico_cpu_apt_run1.md   # los negativos también se registran
└── 2026-09-03_v2/
```

Agrupar por tanda y anotar la versión del prompt es lo que permite responder "¿mejoró o
empeoró?" cuando se cambie algo.

## Plantilla de `matriz_resultados.md`

| # | Escenario | Corrida | ¿Detectó? | Tiempo a informe | ¿Causa correcta? | ¿Guía resolvió? | Notas |
|---|---|---|---|---|---|---|---|
| 07 | Cascada | 1 | Sí | 78 s | Sí | Sí | — |
| 07 | Cascada | 2 | Sí | 91 s | Parcial | Sí | Culpó a Postgres primero |
| N1 | Pico CPU apt | 1 | No | — | — | — | Correcto: no debía dispararse |

Al cierre de cada tanda se calculan las métricas de la sección 16 sobre esta tabla y se comparan
contra las metas.

## Convención

Esta carpeta puede crecer mucho. Si se vuelve pesada, se versiona solo `matriz_resultados.md` y
una muestra representativa de informes, no las 42 corridas completas de cada tanda.
