"""Vigilancia pasiva: muestrea el estado del servidor cada 30 segundos.

Este modulo NO decide si hay un incidente -- esa es responsabilidad del detector,
que aplica persistencia sobre N ciclos. Aqui solo se toman lecturas crudas y se
entregan como estructura de datos.

Dos modos:
  - bucle (por defecto): muestrea cada 30 s, es la vigilancia continua
  - --once: una sola muestra y termina. Lo usa trigger.sh cuando el journal
    reporta un fallo, para capturar el estado *mientras todavia es cierto*
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from datetime import datetime
from typing import Any

# El nombre del logger aparece en cada linea que va a journald, y trigger.sh
# descarta las lineas que contienen "doctorjk" para no dispararse con los errores
# del propio agente. Si alguien cambia este prefijo, el trigger se realimenta en
# bucle. Ver la funcion is_self() en trigger.sh.
LOGGER_NAME = "doctorjk.monitor"
log = logging.getLogger(LOGGER_NAME)

SAMPLE_INTERVAL_S = 30

# Ningun comando de muestreo deberia tardar mas que esto. Sin timeout, un df
# colgado en un montaje de red congela la vigilancia entera y el agente se queda
# ciego sin avisar.
COMMAND_TIMEOUT_S = 10


def run_command(command: list[str]) -> str:
    """Ejecuta un comando de sistema y devuelve su stdout, o cadena vacia si falla.

    Se degrada en vez de propagar: que una senal no se pueda leer no debe tumbar
    el muestreo de las otras cuatro.
    """
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=COMMAND_TIMEOUT_S,
        )
        return result.stdout
    except subprocess.CalledProcessError as error:
        log.warning("comando %s fallo con codigo %s", command[0], error.returncode)
        return ""
    except subprocess.TimeoutExpired:
        log.warning("comando %s excedio %s s", command[0], COMMAND_TIMEOUT_S)
        return ""
    except FileNotFoundError:
        log.warning("comando %s no existe en este sistema", command[0])
        return ""


def get_memory() -> dict[str, int]:
    """Memoria en MB. 'available' es la que importa: 'free' ignora cache reclamable."""
    output = run_command(["free", "-m"])

    for line in output.splitlines():
        if not line.startswith("Mem:"):
            continue
        fields = line.split()
        if len(fields) < 7:
            continue
        try:
            return {
                "total": int(fields[1]),
                "used": int(fields[2]),
                "free": int(fields[3]),
                "available": int(fields[6]),
            }
        except ValueError:
            log.warning("no pude interpretar la linea de memoria: %s", line)
            break

    return {}


def get_disk() -> list[dict[str, Any]]:
    """Uso por sistema de archivos montado."""
    output = run_command(["df", "-h", "--output=source,pcent,target"])

    disks: list[dict[str, Any]] = []
    for line in output.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 3:
            continue
        # Algunos montajes especiales reportan "-" en vez de un porcentaje.
        # Se omiten en vez de reventar el muestreo completo.
        percent = fields[1].replace("%", "")
        if not percent.isdigit():
            continue
        disks.append(
            {
                "source": fields[0],
                "usage_percent": int(percent),
                "target": fields[2],
            }
        )

    return disks


def get_services() -> dict[str, list[str]]:
    """Unidades de systemd en estado failed.

    --no-legend --plain no son opcionales. Sin ellos systemd antepone una vinieta
    "*" al nombre de cada unidad fallida y agrega leyenda y pie de conteo, asi que
    el parseo devuelve la vinieta y trozos de texto en vez del nombre del servicio.
    Con cero fallos el error no se nota: aparece solo cuando hay algo que detectar.
    """
    output = run_command(
        ["systemctl", "list-units", "--failed", "--no-legend", "--plain", "--no-pager"]
    )

    failed = [line.split()[0] for line in output.splitlines() if line.strip()]
    return {"failed": failed}


def get_ports() -> list[dict[str, Any]]:
    """Puertos TCP en escucha."""
    output = run_command(["ss", "-tlnp"])

    ports: list[dict[str, Any]] = []
    for line in output.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4:
            continue
        try:
            host, port = fields[3].rsplit(":", 1)
            ports.append({"address": host, "port": int(port)})
        except ValueError:
            continue

    return ports


def get_load() -> dict[str, float]:
    """Carga promedio a 1, 5 y 15 minutos."""
    output = run_command(["uptime"])
    if not output:
        return {}

    try:
        values = output.split("load average:")[1].strip().split(",")
        # Algunas locales usan coma decimal y parten los tres valores en seis
        # trozos; se normaliza antes de convertir.
        if len(values) == 6:
            values = [f"{values[i]}.{values[i + 1]}" for i in range(0, 6, 2)]
        return {
            "1m": float(values[0]),
            "5m": float(values[1]),
            "15m": float(values[2]),
        }
    except (IndexError, ValueError):
        log.warning("no pude interpretar la carga: %s", output.strip())
        return {}


def take_sample() -> dict[str, Any]:
    """Una lectura completa de las cinco senales, con marca de tiempo."""
    return {
        "timestamp": datetime.now().isoformat(),
        "services": get_services(),
        "disk": get_disk(),
        "memory": get_memory(),
        "ports": get_ports(),
        "load": get_load(),
    }


def run_once() -> dict[str, Any]:
    """Captura puntual. La invoca trigger.sh al detectar un fallo en el journal."""
    sample = take_sample()
    # INFO y no WARNING a proposito: journald lo registra en prioridad 6, por
    # debajo del umbral que escucha trigger.sh, asi que no puede autodispararse.
    log.info("muestra puntual: %s", json.dumps(sample))
    return sample


def run_loop(interval_s: int = SAMPLE_INTERVAL_S) -> None:
    """Vigilancia continua. Se detiene con SIGINT o SIGTERM."""
    log.info("monitor iniciado, muestreando cada %s s", interval_s)
    while True:
        # DEBUG porque a 30 s son ~2.900 lineas diarias: util al depurar,
        # ruido puro en operacion normal.
        log.debug("muestra: %s", json.dumps(take_sample()))
        time.sleep(interval_s)


def main() -> None:
    parser = argparse.ArgumentParser(description="Vigilancia pasiva de Doctor J/K")
    parser.add_argument(
        "--once",
        action="store_true",
        help="toma una sola muestra y termina, en vez de vigilar en bucle",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=SAMPLE_INTERVAL_S,
        help=f"segundos entre muestras (por defecto {SAMPLE_INTERVAL_S})",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format=f"{LOGGER_NAME}: %(message)s")

    if args.once:
        run_once()
        return

    try:
        run_loop(args.interval)
    except KeyboardInterrupt:
        log.info("monitor detenido")


# El bucle no puede vivir a nivel de modulo: importar monitor.py para probar una
# sola funcion arrancaria la vigilancia infinita.
if __name__ == "__main__":
    main()
