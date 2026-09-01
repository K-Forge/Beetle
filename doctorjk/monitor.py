# Monitor: muestrea el estado del servidor cada ciclo usando herramientas
# nativas del sistema (systemctl, df, free, ss, uptime) y normaliza esa
# lectura a Signal, el formato único que consume el detector (Fase 2).
#
# Este módulo no decide nada ni sabe de incidentes: solo produce datos. No
# tiene loop propio — desde plan-mvp.md §3.1, main.py es el único dueño del
# estado y de la temporización; este módulo expone funciones puras que main.py
# invoca en cada ciclo.
#
# Separación deliberada en tres capas para poder probar sin tocar el sistema
# real:
#   1. run_command(): la única función que llama subprocess.
#   2. parse_*_output(): funciones puras, reciben texto y devuelven datos.
#   3. take_snapshot() / normalize_snapshot(): componen las dos anteriores.
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from doctorjk.modelos import (
    DiskUsage,
    FailedService,
    ListeningPort,
    LoadAverage,
    MemoryUsage,
    MonitoredPort,
    ServiceState,
    Signal,
    SignalType,
    SystemSnapshot,
)

logger = logging.getLogger(__name__)

# Cada llamada a una herramienta del sistema es rápida (systemctl, df, free,
# ss y uptime no hacen red ni E/S pesada); 5 s es margen generoso para no
# colgar el ciclo de muestreo si una herramienta se comporta mal.
DEFAULT_COMMAND_TIMEOUT_S = 5.0


@dataclass(frozen=True)
class CommandResult:
    stdout: str
    success: bool
    error: str | None


# ------------------------------------------------------- frontera con el SO


def run_command(argv: Sequence[str], timeout_s: float) -> CommandResult:
    """Ejecuta un comando del sistema y nunca lanza: los tres fallos posibles
    (comando ausente, tiempo agotado, código distinto de 0) se devuelven como
    CommandResult con success=False para que el llamador decida qué hacer."""
    try:
        completado = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        mensaje = f"comando no encontrado: {argv[0]}"
        logger.warning(mensaje)
        return CommandResult(stdout="", success=False, error=mensaje)
    except subprocess.TimeoutExpired:
        mensaje = f"tiempo agotado tras {timeout_s}s ejecutando: {' '.join(argv)}"
        logger.warning(mensaje)
        return CommandResult(stdout="", success=False, error=mensaje)

    if completado.returncode != 0:
        mensaje = (
            f"{argv[0]} terminó con código {completado.returncode}: "
            f"{completado.stderr.strip()}"
        )
        logger.warning(mensaje)
        return CommandResult(stdout=completado.stdout, success=False, error=mensaje)

    return CommandResult(stdout=completado.stdout, success=True, error=None)


def query_service_states(
    services: Sequence[str], timeout_s: float
) -> dict[str, bool] | None:
    """Consulta el estado activo de cada servicio vigilado con una sola
    llamada a `systemctl is-active`.

    A diferencia de run_command(), un código de salida distinto de 0 acá es
    normal y esperado: `systemctl is-active` devuelve no-cero si CUALQUIERA
    de los servicios pedidos no está activo, no significa que el comando
    haya fallado (plan-finalizacion-mvp.md Gate 1.3, defecto 1). Por eso este
    helper no usa run_command() y solo trata como falla real la ausencia del
    comando o un timeout: la única forma correcta de saber si un servicio
    vigilado está sano es preguntarle a systemd, nunca inferirlo de su
    ausencia en `--failed`.
    """
    if not services:
        return {}
    try:
        completado = subprocess.run(
            ["systemctl", "is-active", *services],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as error:
        logger.warning("comando no encontrado: systemctl (%s)", error)
        return None
    except subprocess.TimeoutExpired:
        logger.warning(
            "tiempo agotado tras %ss consultando estado de %d servicio(s)",
            timeout_s,
            len(services),
        )
        return None

    # systemctl is-active imprime exactamente una línea por unidad pedida, en
    # el mismo orden -- incluida "unknown" para una unidad inexistente, que
    # se trata como inactiva y no como falla de adquisición.
    lineas = completado.stdout.splitlines()
    return {servicio: linea.strip() == "active" for servicio, linea in zip(services, lineas)}


# --------------------------------------------------------------- parsers puros


def parse_failed_services_output(stdout: str) -> tuple[FailedService, ...]:
    servicios: list[FailedService] = []
    for linea in stdout.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        columnas = linea.split()
        servicios.append(FailedService(name=columnas[0]))
    return tuple(servicios)


def parse_disk_output(stdout: str) -> tuple[DiskUsage, ...]:
    discos: list[DiskUsage] = []
    # La primera línea es el encabezado de df ("Filesystem Use% Mounted on").
    for linea in stdout.splitlines()[1:]:
        columnas = linea.split()
        if len(columnas) < 3:
            continue
        try:
            porcentaje = int(columnas[1].rstrip("%"))
        except ValueError:
            continue
        discos.append(
            DiskUsage(source=columnas[0], usage_percent=porcentaje, target=columnas[2])
        )
    return tuple(discos)


def parse_memory_output(stdout: str) -> MemoryUsage | None:
    for linea in stdout.splitlines():
        if not linea.startswith("Mem:"):
            continue
        columnas = linea.split()
        try:
            return MemoryUsage(
                total_mb=int(columnas[1]),
                used_mb=int(columnas[2]),
                free_mb=int(columnas[3]),
                available_mb=int(columnas[6]),
            )
        except (IndexError, ValueError):
            # free sin columna "available" (procps viejo) u otra salida
            # inesperada: se trata como lectura ausente, no como memoria sana.
            return None
    return None


def parse_ports_output(stdout: str) -> tuple[ListeningPort, ...]:
    puertos: list[ListeningPort] = []
    # La primera línea es el encabezado de ss ("State Recv-Q Send-Q ...").
    for linea in stdout.splitlines()[1:]:
        columnas = linea.split()
        if len(columnas) < 4:
            continue
        direccion_local = columnas[3]
        try:
            host, puerto = direccion_local.rsplit(":", 1)
            puertos.append(ListeningPort(address=host, port=int(puerto)))
        except ValueError:
            continue
    return tuple(puertos)


def parse_load_output(stdout: str) -> LoadAverage | None:
    if "load average:" not in stdout:
        return None
    cola = stdout.split("load average:", 1)[1].strip()
    valores = [v.strip() for v in cola.split(",")]
    if len(valores) != 3:
        return None
    try:
        return LoadAverage(
            load_1m=float(valores[0]),
            load_5m=float(valores[1]),
            load_15m=float(valores[2]),
        )
    except ValueError:
        return None


# --------------------------------------------------------------- muestreo


def take_snapshot(
    timeout_s: float = DEFAULT_COMMAND_TIMEOUT_S,
    monitored_services: frozenset[str] = frozenset(),
) -> SystemSnapshot:
    """Toma una lectura completa del servidor. Cada categoría es independiente:
    si una herramienta falla, esa categoría queda vacía y marcada como no
    disponible, pero las demás igual se reportan.

    `monitored_services` es aparte de `failed_services`: sin esa lista
    explícita no hay forma de emitir una señal sana para un servicio que se
    recuperó, porque `systemctl --failed` simplemente deja de mencionarlo
    (plan-finalizacion-mvp.md Gate 1.3, defecto 1).
    """
    servicios = run_command(
        ["systemctl", "list-units", "--failed", "--no-legend", "--plain", "--no-pager"],
        timeout_s,
    )
    disco = run_command(["df", "-h", "--output=source,pcent,target"], timeout_s)
    memoria = run_command(["free", "-m"], timeout_s)
    puertos = run_command(["ss", "-tlnp"], timeout_s)
    carga = run_command(["uptime"], timeout_s)

    memoria_parseada = parse_memory_output(memoria.stdout) if memoria.success else None
    carga_parseada = parse_load_output(carga.stdout) if carga.success else None

    if monitored_services:
        estados = query_service_states(sorted(monitored_services), timeout_s)
        estados_disponibles = estados is not None
        estados_tupla = (
            tuple(ServiceState(name=nombre, active=activo) for nombre, activo in estados.items())
            if estados is not None
            else ()
        )
    else:
        # Nada vigilado explícitamente: no es una falla de adquisición, es
        # que no se pidió nada.
        estados_disponibles = True
        estados_tupla = ()

    return SystemSnapshot(
        captured_at=datetime.now(timezone.utc),
        failed_services=(
            parse_failed_services_output(servicios.stdout) if servicios.success else ()
        ),
        services_available=servicios.success,
        disks=parse_disk_output(disco.stdout) if disco.success else (),
        disk_available=disco.success,
        memory=memoria_parseada,
        memory_available=memoria.success and memoria_parseada is not None,
        ports=parse_ports_output(puertos.stdout) if puertos.success else (),
        ports_available=puertos.success,
        load=carga_parseada,
        load_available=carga.success and carga_parseada is not None,
        service_states=estados_tupla,
        service_states_available=estados_disponibles,
    )


# ----------------------------------------------------------- normalización


def normalize_snapshot(
    snapshot: SystemSnapshot,
    disk_pct_threshold: int,
    memory_available_mb_threshold: int,
    monitored_ports: tuple[MonitoredPort, ...],
) -> tuple[Signal, ...]:
    """Convierte un SystemSnapshot a Signal (contrato de la tarea #173).

    Los umbrales se inyectan como parámetros; este módulo no lee config.toml
    (eso es responsabilidad de config.py, bloque B1). Una categoría marcada
    como no disponible en el snapshot no emite señal — ni sana ni cruzada —
    para que el detector (Fase 2) no confunda un fallo de adquisición con un
    recurso saludable.
    """
    señales: list[Signal] = []
    marca_de_tiempo = snapshot.captured_at

    # Servicios vigilados explícitamente (config.servicios_vigilados): se
    # emite una señal por cada uno, sano o cruzado, en todos los ciclos. A
    # diferencia de `failed_services` (que solo lista lo ya fallido y por eso
    # nunca informa una recuperación), `service_states` viene de consultar
    # cada unidad de la lista, así que el detector se entera igual cuando el
    # servicio vuelve a estar activo (plan-finalizacion-mvp.md defecto 1).
    if snapshot.service_states_available:
        for estado in snapshot.service_states:
            señales.append(
                Signal(
                    timestamp=marca_de_tiempo,
                    signal_type=SignalType.SERVICE_FAILED,
                    value="active" if estado.active else "inactive",
                    threshold="active",
                    crossed=not estado.active,
                    key=f"service:{estado.name}",
                )
            )

    # Disco: una señal por punto de montaje, cruzada o no según el umbral.
    if snapshot.disk_available:
        for disco_leido in snapshot.disks:
            señales.append(
                Signal(
                    timestamp=marca_de_tiempo,
                    signal_type=SignalType.DISK_FULL,
                    value=str(disco_leido.usage_percent),
                    threshold=str(disk_pct_threshold),
                    crossed=disco_leido.usage_percent > disk_pct_threshold,
                    key=f"disk:{disco_leido.target}",
                )
            )

    # Memoria: una sola señal global, no hay "por recurso" que distinguir.
    if snapshot.memory_available and snapshot.memory is not None:
        señales.append(
            Signal(
                timestamp=marca_de_tiempo,
                signal_type=SignalType.MEMORY_LOW,
                value=str(snapshot.memory.available_mb),
                threshold=str(memory_available_mb_threshold),
                crossed=snapshot.memory.available_mb < memory_available_mb_threshold,
                key="memory",
            )
        )

    # Puertos: solo se evalúan los que el cliente configuró como esperados.
    # Sin esa lista no hay umbral contra el cual cruzar, así que un puerto
    # abierto que nadie pidió vigilar no genera señal.
    #
    # Dos tipos por puerto, con claves distintas porque el detector guarda un
    # estado por clave (defecto 6): PORT_DOWN es "nadie escucha"; PORT_OCCUPIED
    # es "alguien escucha, pero no es el servicio que se esperaba" -- distinto
    # de sano aunque el puerto esté "ocupado", porque quien lo tomó no es quien
    # debía. Sin estado del servicio esperado (no vigilado, o consulta no
    # disponible) no hay base para declarar ocupación indebida: queda sano.
    if snapshot.ports_available:
        puertos_escuchando = {p.port for p in snapshot.ports}
        estado_por_servicio = {e.name: e.active for e in snapshot.service_states}
        for vigilado in monitored_ports:
            escuchando = vigilado.port in puertos_escuchando
            señales.append(
                Signal(
                    timestamp=marca_de_tiempo,
                    signal_type=SignalType.PORT_DOWN,
                    value="listening" if escuchando else "down",
                    threshold="listening",
                    crossed=not escuchando,
                    key=f"port:{vigilado.port}:down",
                )
            )

            servicio_activo = estado_por_servicio.get(vigilado.service)
            ocupado_indebidamente = escuchando and servicio_activo is False
            señales.append(
                Signal(
                    timestamp=marca_de_tiempo,
                    signal_type=SignalType.PORT_OCCUPIED,
                    value="occupied_by_other" if ocupado_indebidamente else "owned_or_free",
                    threshold="owned_or_free",
                    crossed=ocupado_indebidamente,
                    key=f"port:{vigilado.port}:occupied",
                )
            )

    # Carga: se queda fuera de Signal a propósito (plan-mvp.md bloque A4).
    # snapshot.load sigue disponible para logging mientras no exista un
    # criterio de incidente aprobado para ella.

    return tuple(señales)
