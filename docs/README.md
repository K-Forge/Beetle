# `docs/` — documentación del proyecto

Los documentos que definen qué se está construyendo y por qué. Es la fuente de verdad: cuando el
código y el documento no coincidan, se corrige uno de los dos explícitamente, no se deja la
diferencia sin resolver.

## Estructura recomendada

```
docs/
├── doctor-jk-proyecto.md            # documento maestro (v4.0)
├── doctor-jk-roadmap.md             # fases y cronograma
├── doctor-jk-tareas.md              # 56 tareas con criterio de avance
├── plan-finalizacion-mvp.md          # auditoría vigente y plan hasta v0.1.0
├── plan-mvp.md                       # plan histórico inicial del MVP
├── links.md                         # enlaces de trabajo del equipo
├── runbook-restore.md               # cómo restaurar el VPS desde snapshot (#168)
├── arquitectura.md                  # (pendiente) detalle técnico para quien toque el código
└── sanitizador_limitaciones.md      # qué NO cubre la sanitización (#185)
```

## Qué hay hoy

| Documento | Contenido |
|---|---|
| [doctor-jk-proyecto.md](doctor-jk-proyecto.md) | Ikigai, problema, solución, arquitectura, stack, costos, prompt, remediador, escenarios, métricas, riesgos, modelo de producto |
| [doctor-jk-roadmap.md](doctor-jk-roadmap.md) | Las 10 fases con su duración y su lista de recorte |
| [doctor-jk-tareas.md](doctor-jk-tareas.md) | Issues #166–#221, cada una con qué hacer, por qué importa y criterio de avance |
| [plan-finalizacion-mvp.md](plan-finalizacion-mvp.md) | Estado verificado de ramas, código, VPS e issues; orden de commits, PR, merges, pruebas y gates hasta v0.1.0 |
| [plan-mvp.md](plan-mvp.md) | Plan inicial conservado como referencia histórica; su estado ya no es el vigente |
| [links.md](links.md) | Canva, formularios y repositorios de referencia |
| [runbook-restore.md](runbook-restore.md) | Restauración del VPS: procedimiento, quién puede ejecutarla, política de snapshots y el gotcha de Tailscale |
| [sanitizador_limitaciones.md](sanitizador_limitaciones.md) | Seis escenarios que el sanitizador por patrones NO cubre, con su riesgo residual (tarea #185) |

## Qué falta escribir

- **`arquitectura.md`** — el detalle técnico que no cabe en el documento de proyecto: contratos
  entre módulos, formato de la evidencia, formato del plan de corrección del Modo 3.

## Convención

El documento de proyecto lleva número de versión. Al cambiarlo de forma sustantiva se sube la
versión y se anota qué cambió, para que las tareas y el roadmap puedan referirse a una versión
concreta.
