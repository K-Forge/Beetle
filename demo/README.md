# `demo/` — escenarios que provocan incidentes

Scripts que rompen el servidor de pruebas a propósito, de forma controlada y repetible. Son la
materia prima de la medición: sin escenarios reproducibles no hay forma de calcular tasa de
detección ni precisión de causa raíz.

Estos scripts **solo se corren en el VPS de pruebas**, nunca en producción.

## Estructura recomendada

```
demo/
├── 01_servicio_caido.sh        # systemctl stop postgresql
├── 02_disco_lleno.sh           # fallocate -l 18G /tmp/relleno
├── 03_memoria_agotada.sh       # reservar RAM hasta OOM
├── 04_puerto_ocupado.sh        # nc -l 5432 antes de arrancar Postgres
├── 05_disco_por_logs.sh        # debug sin logrotate; la causa es de hace horas
├── 06_fuga_memoria.sh          # fuga gradual de RAM hasta OOM
├── 07_cascada.sh               # disco → Postgres → app → Nginx: tres fallos, una causa
├── 08_config_rota.sh           # modificar pg_hba.conf; la causa está en un archivo, no en el log
├── 09_puerto_secuestrado.sh    # otro proceso toma el 5432
├── negativos/                  # ver su propio README
└── trafico_fondo.sh            # arranca el tráfico de fondo con hey o wrk
```

Los primeros cuatro son los escenarios básicos (§15.1); del 5 al 9 son los realistas (§15.2),
donde la causa no está a la vista en el síntoma.

## Contrato que debe cumplir todo escenario

| Aspecto | Regla |
|---|---|
| Numeración | Prefijo de dos dígitos, en el orden de las secciones 15.1 y 15.2 |
| Cabecera | Comentario con: qué provoca, qué causa raíz debe detectar el agente, y cuánto tarda |
| Restauración | Cada escenario trae su forma de deshacerse (o se documenta que hace falta snapshot) |
| Tráfico | Todo escenario se corre **con tráfico de fondo**; sin ruido los incidentes son obvios y la prueba no vale (§15.4) |
| Determinismo | Correrlo tres veces debe producir el mismo incidente — el protocolo son 3 corridas por escenario |

## Cómo se usa

1. Arrancar el tráfico de fondo.
2. Escribir la causa raíz esperada en `pruebas/esperados/` **antes** de correr el escenario.
3. Correr el escenario y dejar que el agente actúe.
4. Guardar el informe generado en `pruebas/resultados/`.
5. Restaurar el VPS (script propio del escenario o snapshot de Oracle).
