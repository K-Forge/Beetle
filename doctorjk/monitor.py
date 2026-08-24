#rodri
from datetime import datetime
import subprocess
import time

def ejecutar_comando(comando):
    try:
        resultado = subprocess.run(
            comando,
            capture_output=True,
            text=True,
            check=True
        )

        return resultado.stdout

    except subprocess.CalledProcessError as error:
        print(f"Error ejecutando {comando}: {error}")
        return ""


def obtener_memoria():
    salida = ejecutar_comando(["free", "-m"])

    lineas = salida.splitlines()

    for linea in lineas:
        if linea.startswith("Mem:"):
            datos = linea.split()

            return {
                "total": int(datos[1]),
                "used": int(datos[2]),
                "free": int(datos[3]),
                "available": int(datos[6])
            }

    return {}
    
def obtener_disco():
    salida = ejecutar_comando(
        ["df", "-h", "--output=source,pcent,target"]
    )

    lineas = salida.splitlines()

    discos = []

    for linea in lineas[1:]:
        datos = linea.split()

        if len(datos) >= 3:
            discos.append({
                "source": datos[0],
                "usage_percent": int(datos[1].replace("%", "")),
                "target": datos[2]
            })

    return discos
    
def obtener_servicios():
    salida = ejecutar_comando(
        ["systemctl", "list-units", "--failed", "--no-pager"]
    )

    servicios_fallidos = []

    for linea in salida.splitlines():
        linea = linea.strip()

        if not linea:
            continue

        if linea.startswith("UNIT"):
            continue

        if linea.startswith("0 loaded units"):
            continue

        datos = linea.split()

        if datos:
            servicios_fallidos.append(datos[0])

    return {
        "failed": servicios_fallidos
    }
   
   
def obtener_puertos():
    salida = ejecutar_comando(
        ["ss", "-tlnp"]
    )

    puertos = []

    for linea in salida.splitlines()[1:]:
        datos = linea.split()

        if len(datos) < 4:
            continue

        direccion = datos[3]

        try:
            host, puerto = direccion.rsplit(":", 1)

            puertos.append({
                "address": host,
                "port": int(puerto)
            })

        except ValueError:
            continue

    return puertos


def obtener_carga():
    salida = ejecutar_comando(["uptime"])

    if not salida:
        return {}

    try:
        parte_carga = salida.split("load average:")[1]

        valores = parte_carga.strip().split(",")

        return {
            "1m": float(valores[0]),
            "5m": float(valores[1]),
            "15m": float(valores[2])
        }

    except (IndexError, ValueError):
        return {}
    
def tomar_muestra():
    return {
        "timestamp": datetime.now().isoformat(),
        "services": obtener_servicios(),
        "disk": obtener_disco(),
        "memory": obtener_memoria(),
        "ports": obtener_puertos(),
        "load": obtener_carga()
    }
    
while True:
    muestra = tomar_muestra()
    print(muestra)
    time.sleep(30)