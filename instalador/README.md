# `instalador/` — instalación y ejecución como servicio

Todo lo necesario para dejar el agente corriendo en un servidor ajeno. La restricción de diseño
viene del cliente: **si la instalación pasa de 15 minutos, Mateo la abandona** (§2.2). Un solo
comando, sin pasos manuales de edición de archivos salvo pegar el token.

## Estructura recomendada

```
instalador/
├── install.sh            # instalación completa en un comando
├── desinstalar.sh        # revierte todo lo que install.sh dejó
├── doctorjk.service      # unidad systemd del agente
├── doctorjk.timer        # (opcional) si el monitor corre por timer en vez de bucle
└── config.toml.example   # plantilla de configuración — se copia a /etc/doctorjk/
```

La plantilla de secretos (`.env.example`) vive en la raíz del repo, no acá — es la convención
estándar para que quien clona el repo la vea de entrada.

## Qué debe hacer `install.sh`

1. Verificar el sistema: Ubuntu/Debian, Python 3.11+, systemd presente.
2. Crear el usuario de servicio `doctorjk` sin shell de login.
3. Instalar el paquete en `/opt/doctorjk` con su entorno virtual.
4. Copiar `config.toml.example` (de `instalador/`) y `.env.example` (de la raíz del repo) a
   `/etc/doctorjk/` si aún no existen —
   nunca sobrescribir la config de una instalación previa.
5. Pedir (o leer de un flag) las credenciales del proveedor de LLM y escribirlas en
   `/etc/doctorjk/.env` con permisos `600`.
6. Crear el directorio de informes `/var/lib/doctorjk/informes`.
7. Instalar y habilitar la unidad systemd, arrancarla y comprobar que quedó `active`.
8. Imprimir un resumen: dónde quedó la config, dónde quedan los informes, y en qué modo arrancó.

## Decisiones que el instalador debe respetar

| Decisión | Por qué |
|---|---|
| Arranca siempre en Modo 1 (solo diagnostica) | El cliente necesita confiar antes de permitir que el agente actúe (§2.2) |
| El monitor corre como `doctorjk`, no como root | Privilegios mínimos; root solo cuando se activa el remediador |
| Secretos en `/etc/doctorjk/.env` con permisos `600` | Fuera del archivo de config y fuera del repo (§7.1) |
| `Restart=always` en la unidad | El agente que vigila no puede ser el que se cae en silencio |
| Reinstalar no pisa la configuración existente | Actualizar no debe reabrir decisiones ya tomadas |

## Convenciones

- El instalador es idempotente: correrlo dos veces deja el mismo estado.
- `desinstalar.sh` deja el servidor como estaba, conservando los informes ya generados.
- Nada de descargas de fuentes no verificadas dentro del script.
