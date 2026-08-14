# `prompts/` — prompts del modelo

Los prompts de sistema que se envían al LLM, versionados como archivos aparte del código.
Separarlos importa porque el prompt se itera muchas más veces que el código que lo usa: durante
la Fase 5 se reescribe contra informes reales hasta que la salida sea comprensible para alguien
que no administra servidores.

## Estructura recomendada

```
prompts/
├── diagnosticador.md     # Modo 1 — evidencia → diagnóstico + guía de solución
├── planificador.md       # Modo 3 — evidencia → plan de corrección estructurado
├── ejecutor.md           # Modo 3 — plan + resultado del paso → seguir / reintentar / abortar
└── versiones/            # copias fechadas de los prompts que se probaron
    └── diagnosticador_v1.md
```

`planificador.md` y `ejecutor.md` solo hacen falta si se elige la Opción B (dupla de modelos)
de la sección 14.3. Con la Opción A (modelo único) basta `diagnosticador.md`.

## Qué debe contener `diagnosticador.md`

Según la sección 12 del documento de proyecto:

1. **Rol** — diagnosticador experto que escribe para alguien que no es administrador de sistemas.
2. **Reglas de confianza** — cada causa raíz se etiqueta con confianza alta / media / baja.
3. **Causas descartadas** — obliga al modelo a decir qué consideró y por qué lo descartó; es la
   defensa contra la alucinación de causas.
4. **Formato de salida** — `## DIAGNÓSTICO` (qué pasó, cronología, causa raíz, causas
   descartadas) y `## GUÍA DE SOLUCIÓN` (pasos numerados, con el comando exacto, qué hace y qué
   se espera ver).
5. **Prohibiciones** — el modelo no ejecuta nada y no inventa datos que no estén en la evidencia.

## Convenciones

- Un archivo por rol de modelo, nunca prompts embebidos en el código Python.
- Al cambiar un prompt de forma significativa, guardar la versión anterior en `versiones/` y
  anotar en `pruebas/resultados/` con qué versión se corrió cada tanda de escenarios.
- El prompt se escribe en español, igual que el informe que produce.
