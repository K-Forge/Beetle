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
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError:
        message = f"comando no encontrado: {argv[0]}"
        logger.warning(message)
        return CommandResult(stdout="", success=False, error=message)
    except subprocess.TimeoutExpired:
        message = f"tiempo agotado tras {timeout_s}s ejecutando: {' '.join(argv)}"
        logger.warning(message)
        return CommandResult(stdout="", success=False, error=message)

    if completed.returncode != 0:
        message = (
            f"{argv[0]} terminó con código {completed.returncode}: "
            f"{completed.stderr.strip()}"
        )
        logger.warning(message)
        return CommandResult(stdout=completed.stdout, success=False, error=message)

    return CommandResult(stdout=completed.stdout, success=True, error=None)


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
        completed = subprocess.run(
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
    lines = completed.stdout.splitlines()
    return {service: line.strip() == "active" for service, line in zip(services, lines)}


# --------------------------------------------------------------- parsers puros


def parse_failed_services_output(stdout: str) -> tuple[FailedService, ...]:
    services: list[FailedService] = []
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        columns = line.split()
        services.append(FailedService(name=columns[0]))
    return tuple(services)


def parse_disk_output(stdout: str) -> tuple[DiskUsage, ...]:
    disks: list[DiskUsage] = []
    # La primera línea es el encabezado de df ("Filesystem Use% Mounted on").
    for line in stdout.splitlines()[1:]:
        columns = line.split()
        if len(columns) < 3:
            continue
        try:
            percentage = int(columns[1].rstrip("%"))
        except ValueError:
            continue
        disks.append(
            DiskUsage(source=columns[0], usage_percent=percentage, target=columns[2])
        )
    return tuple(disks)


def parse_memory_output(stdout: str) -> MemoryUsage | None:
    for line in stdout.splitlines():
        if not line.startswith("Mem:"):
            continue
        columns = line.split()
        try:
            return MemoryUsage(
                total_mb=int(columns[1]),
                used_mb=int(columns[2]),
                free_mb=int(columns[3]),
                available_mb=int(columns[6]),
            )
        except (IndexError, ValueError):
            # free sin columna "available" (procps viejo) u otra salida
            # inesperada: se trata como lectura ausente, no como memoria sana.
            return None
    return None


def parse_ports_output(stdout: str) -> tuple[ListeningPort, ...]:
    ports: list[ListeningPort] = []
    # La primera línea es el encabezado de ss ("State Recv-Q Send-Q ...").
    for line in stdout.splitlines()[1:]:
        columns = line.split()
        if len(columns) < 4:
            continue
        local_address = columns[3]
        try:
            host, port = local_address.rsplit(":", 1)
            ports.append(ListeningPort(address=host, port=int(port)))
        except ValueError:
            continue
    return tuple(ports)


def parse_load_output(stdout: str) -> LoadAverage | None:
    if "load average:" not in stdout:
        return None
    tail = stdout.split("load average:", 1)[1].strip()
    values = [v.strip() for v in tail.split(",")]
    if len(values) != 3:
        return None
    try:
        return LoadAverage(
            load_1m=float(values[0]),
            load_5m=float(values[1]),
            load_15m=float(values[2]),
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
    services_result = run_command(
        ["systemctl", "list-units", "--failed", "--no-legend", "--plain", "--no-pager"],
        timeout_s,
    )
    disk_result = run_command(["df", "-h", "--output=source,pcent,target"], timeout_s)
    memory_result = run_command(["free", "-m"], timeout_s)
    ports_result = run_command(["ss", "-tlnp"], timeout_s)
    load_result = run_command(["uptime"], timeout_s)

    parsed_memory = parse_memory_output(memory_result.stdout) if memory_result.success else None
    parsed_load = parse_load_output(load_result.stdout) if load_result.success else None

    if monitored_services:
        states = query_service_states(sorted(monitored_services), timeout_s)
        states_available = states is not None
        states_tuple = (
            tuple(ServiceState(name=name, active=active) for name, active in states.items())
            if states is not None
            else ()
        )
    else:
        # Nada vigilado explícitamente: no es una falla de adquisición, es
        # que no se pidió nada.
        states_available = True
        states_tuple = ()

    return SystemSnapshot(
        captured_at=datetime.now(timezone.utc),
        failed_services=(
            parse_failed_services_output(services_result.stdout) if services_result.success else ()
        ),
        services_available=services_result.success,
        disks=parse_disk_output(disk_result.stdout) if disk_result.success else (),
        disk_available=disk_result.success,
        memory=parsed_memory,
        memory_available=memory_result.success and parsed_memory is not None,
        ports=parse_ports_output(ports_result.stdout) if ports_result.success else (),
        ports_available=ports_result.success,
        load=parsed_load,
        load_available=load_result.success and parsed_load is not None,
        service_states=states_tuple,
        service_states_available=states_available,
    )


# ----------------------------------------------------------- normalización


def normalize_snapshot(
    snapshot: SystemSnapshot,
    disk_pct_threshold: int,
    memory_available_mb_threshold: int,
    monitored_ports: tuple[MonitoredPort, ...],
    monitored_mount_points: tuple[str, ...],
) -> tuple[Signal, ...]:
    """Convierte un SystemSnapshot a Signal (contrato de la tarea #173).

    Los umbrales se inyectan como parámetros; este módulo no lee config.toml
    (eso es responsabilidad de config.py, bloque B1). Una categoría marcada
    como no disponible en el snapshot no emite señal — ni sana ni cruzada —
    para que el detector (Fase 2) no confunda un fallo de adquisición con un
    recurso saludable.
    """
    signals: list[Signal] = []
    timestamp = snapshot.captured_at

    # Servicios vigilados explícitamente (config.servicios_vigilados): se
    # emite una señal por cada uno, sano o cruzado, en todos los ciclos. A
    # diferencia de `failed_services` (que solo lista lo ya fallido y por eso
    # nunca informa una recuperación), `service_states` viene de consultar
    # cada unidad de la lista, así que el detector se entera igual cuando el
    # servicio vuelve a estar activo (plan-finalizacion-mvp.md defecto 1).
    if snapshot.service_states_available:
        for service_state in snapshot.service_states:
            signals.append(
                Signal(
                    timestamp=timestamp,
                    signal_type=SignalType.SERVICE_FAILED,
                    value="active" if service_state.active else "inactive",
                    threshold="active",
                    crossed=not service_state.active,
                    key=f"service:{service_state.name}",
                )
            )

    # Disco: una señal por punto de montaje vigilado, cruzada o no según el
    # umbral (hallazgo de auditoría, 2026-09-01). `df` reporta TODOS los
    # filesystems montados, incluidos los que no son responsabilidad del
    # agente (/boot, /boot/efi, efivars); sin este filtro, un umbral bajo
    # dispara disk_full sobre particiones ajenas y pequeñas que ningún
    # cliente pidió vigilar. La recolección (`df`) no cambia -- se sigue
    # leyendo todo -- solo se filtra acá cuáles targets producen señal.
    monitored_targets = set(monitored_mount_points)
    if snapshot.disk_available:
        for disk_reading in snapshot.disks:
            if disk_reading.target not in monitored_targets:
                continue
            signals.append(
                Signal(
                    timestamp=timestamp,
                    signal_type=SignalType.DISK_FULL,
                    value=str(disk_reading.usage_percent),
                    threshold=str(disk_pct_threshold),
                    crossed=disk_reading.usage_percent > disk_pct_threshold,
                    key=f"disk:{disk_reading.target}",
                )
            )

    # Memoria: una sola señal global, no hay "por recurso" que distinguir.
    if snapshot.memory_available and snapshot.memory is not None:
        signals.append(
            Signal(
                timestamp=timestamp,
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
        listening_ports = {p.port for p in snapshot.ports}
        service_active_by_name = {e.name: e.active for e in snapshot.service_states}
        for monitored in monitored_ports:
            listening = monitored.port in listening_ports
            signals.append(
                Signal(
                    timestamp=timestamp,
                    signal_type=SignalType.PORT_DOWN,
                    value="listening" if listening else "down",
                    threshold="listening",
                    crossed=not listening,
                    key=f"port:{monitored.port}:down",
                )
            )

            service_active = service_active_by_name.get(monitored.service)
            wrongly_occupied = listening and service_active is False
            signals.append(
                Signal(
                    timestamp=timestamp,
                    signal_type=SignalType.PORT_OCCUPIED,
                    value="occupied_by_other" if wrongly_occupied else "owned_or_free",
                    threshold="owned_or_free",
                    crossed=wrongly_occupied,
                    key=f"port:{monitored.port}:occupied",
                )
            )

    # Carga: se queda fuera de Signal a propósito (plan-mvp.md bloque A4).
    # snapshot.load sigue disponible para logging mientras no exista un
    # criterio de incidente aprobado para ella.

    return tuple(signals)
