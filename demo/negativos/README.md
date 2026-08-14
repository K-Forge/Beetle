# `demo/negativos/` — casos que NO deben disparar el agente

Situaciones ruidosas pero normales. El agente que se dispara con estas es un agente que nadie va
a dejar instalado: la meta es **menos de 10% de falsos positivos** (§16), y estos cinco casos son
la forma de medirla.

Son tan importantes como los escenarios positivos. El detector se lleva dos semanas del
cronograma justamente por esto: distinguir "el servidor está trabajando duro" de "el servidor se
rompió" es la parte difícil del producto.

## Estructura recomendada

```
negativos/
├── N1_pico_cpu_apt.sh          # apt upgrade satura CPU y memoria por 20 s
├── N2_reinicio_programado.sh   # un servicio se reinicia a propósito
├── N3_pico_trafico.sh          # ráfaga de tráfico con hey
├── N4_rotacion_logs.sh         # logrotate nocturno mueve archivos grandes
└── N5_backup_programado.sh     # backup llena disco y I/O temporalmente
```

## Contrato que debe cumplir todo caso negativo

| Aspecto | Regla |
|---|---|
| Prefijo | `N` + número, igual que la tabla de la sección 15.3 |
| Cabecera | Comentario con qué señal falsa produce y por qué es legítima |
| Intensidad | Debe acercarse al umbral sin cruzarlo de forma sostenida — un negativo demasiado suave no prueba nada |
| Duración | Corto y acotado: la señal sube y vuelve a bajar sola |
| Restauración | Se limpia solo, sin necesidad de snapshot |

## Cómo se mide

Cada negativo se corre 3 veces (15 corridas en total, dentro de las 42 del protocolo). Se anota
en `pruebas/resultados/matriz_resultados.md` si el agente se disparó o no. Cualquier disparo
cuenta como falso positivo, aunque el informe generado sea razonable.
