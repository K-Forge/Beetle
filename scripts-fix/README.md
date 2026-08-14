# `scripts-fix/` — correcciones deterministas (Modo 2)

Scripts de bash escritos y probados por el equipo, uno por tipo de incidente conocido. El
Modo 2 **no improvisa**: para el mismo tipo de problema siempre corre el mismo script. Esa es la
diferencia con el Modo 3, donde el plan lo genera el modelo.

El agente nunca elige un script por su cuenta: `doctorjk/clasificador.py` mapea el tipo de
incidente detectado a un archivo de esta carpeta, y ese mapeo es explícito. Ejecutar el script
equivocado es peor que no ejecutar nada.

## Estructura recomendada

```
scripts-fix/
├── fix_disco.sh          # incidente tipo "disco_lleno"
├── fix_servicio.sh       # incidente tipo "servicio_caido"
├── fix_memoria.sh        # incidente tipo "memoria_agotada"
├── fix_puerto.sh         # incidente tipo "puerto_ocupado"
└── comun.sh              # funciones compartidas: log, verificar, abortar
```

El nombre del archivo debe coincidir con el tipo de incidente que declara el detector. Un tipo
nuevo de incidente = un script nuevo aquí + una entrada nueva en el clasificador.

## Contrato que debe cumplir todo script

Cada `fix_*.sh` se escribe con la misma forma, para que el remediador pueda tratarlos igual:

| Aspecto | Regla |
|---|---|
| Cabecera | `#!/usr/bin/env bash` y `set -euo pipefail` |
| Dry-run | Debe respetar la variable `DOCTORJK_DRY_RUN=1`: imprime lo que haría, no lo hace |
| Salida | Código `0` = corregido y verificado; distinto de `0` = no se pudo, escalar |
| Verificación | El script comprueba el resultado por sí mismo (el servicio quedó `active`, el disco bajó del umbral) |
| Idempotencia | Correrlo dos veces no debe empeorar nada |
| Alcance | Solo toca rutas y servicios predefinidos; nada de rutas recibidas sin validar |
| Registro | Cada comando y su resultado se imprimen a stdout — el remediador los guarda en el informe |

## Convenciones

- Nada destructivo sin límite: borrar logs sí, en rutas específicas y con retención; `rm -rf`
  sobre una ruta variable, nunca.
- Todo script se prueba contra su escenario de `demo/` antes de darse por terminado.
- Si un script necesita root, se documenta en su cabecera; el monitor corre sin privilegios.
