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
| Dry-run | Debe respetar `dry_run` de `config.toml` (leído vía `comun.sh: read_config_attr dry_run` / `is_dry_run`): imprime lo que haría, no lo hace |
| Salida | Código `0` = corregido (o simulado) y verificado; distinto de `0` = no se pudo, escalar |
| Verificación | El script comprueba el resultado por sí mismo (el servicio quedó `active`, el disco bajó del umbral, el puerto realmente escucha) |
| Idempotencia | Correrlo dos veces no debe empeorar nada |
| Alcance | Solo toca rutas y servicios predefinidos en `config.toml`; nada de rutas recibidas sin validar |
| Registro | Cada comando y su resultado se imprimen a stdout — el remediador los guarda (sanitizados) en journald y en el informe |

### Desviación deliberada del plan original: la política no viaja por variables de entorno

El documento de proyecto y las tareas #199-202 describían `DOCTORJK_DRY_RUN=1` como una
variable de entorno que el remediador le pasaría al script. Una auditoría de seguridad
(2026-09-01) encontró que eso es inservible en producción: estos scripts corren vía
`sudo -n <ruta-exacta>` (ver más abajo), y sudo con `env_reset` — su comportamiento por
defecto, no una opción rara — elimina **cualquier** variable `DOCTORJK_*` antes de que el
script la vea. Con la variable, cada script fallaba cerrado (o, en el caso de disco, caía
a un umbral por defecto silencioso) en todo despliegue real.

La corrección **no** es agregar `SETENV:`/`env_keep` en sudoers para que esas variables
sobrevivan: eso le daría al proceso `doctorjk` (sin privilegios) la posibilidad de fabricar
la política que ve el script que corre como root, justo la escalación que estas
salvaguardas existen para evitar. En su lugar, cada `fix_*.sh` relee `config.toml`
directamente — ya como root, con el mismo parser validado de Python
(`doctorjk.config.load_config`) — desde una ruta fija que `comun.sh` no acepta como
argumento ni variable sobreviviente a sudo, y verifica que ese archivo sea root-owned y no
escribible por nadie más antes de confiar en él. Ver la cabecera de `comun.sh` para el
detalle completo.

## Convenciones

- Nada destructivo sin límite: borrar logs sí, en rutas específicas y con retención; `rm -rf`
  sobre una ruta variable, nunca.
- Todo script se prueba contra su escenario de `demo/` antes de darse por terminado.
- Estos cuatro scripts SÍ necesitan root (reiniciar servicios, limpiar `/var/log`, liberar
  puertos); `doctorjk` corre sin privilegios. La escalación es un sudoers exacto por ruta
  absoluta de script (`instalador/install.sh` lo genera, `visudo -cf` lo valida antes de
  instalarlo), nunca un comando `systemctl`/`find` suelto ni un shell genérico.
