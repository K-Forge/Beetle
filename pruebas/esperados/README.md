# `pruebas/esperados/` — causa raíz definida de antemano

Un archivo por escenario, escrito **antes** de correrlo. Es la referencia contra la que se
compara el informe que genera el agente.

El orden importa más que el contenido: si la causa esperada se escribe después de leer el
informe, uno termina calificando al modelo contra su propia respuesta y la precisión medida deja
de significar nada.

## Estructura recomendada

```
esperados/
├── 01_servicio_caido.md
├── 02_disco_lleno.md
├── ...
└── 09_puerto_secuestrado.md
```

El nombre del archivo coincide con el del escenario en `demo/`.

## Plantilla sugerida

```markdown
# Escenario 07 — Cascada

**Provocación:** demo/07_cascada.sh
**Fecha de definición:** 2026-08-20 (antes de la primera corrida)

## Causa raíz real
El disco se llena → Postgres no puede escribir su WAL y se detiene → la app pierde
la base de datos y devuelve 500 → Nginx registra errores de upstream.

## Qué debe identificar el agente
- La causa raíz es el disco lleno, no Postgres ni la app.
- Debe reconocer los tres fallos como una sola cadena, no como tres incidentes.

## Qué NO debe decir
- Que el problema es de Postgres.
- Que hay que reiniciar Nginx.

## Guía mínima aceptable
Liberar espacio → verificar → reiniciar Postgres → verificar la app → prevenir (logrotate).
```

Las secciones "qué NO debe decir" y "guía mínima aceptable" son las que permiten calificar sin
discutir: o el informe las cumple o no.
