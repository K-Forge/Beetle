# Recolector: arma la ventana de evidencia alrededor de un incidente ya
# confirmado por el detector (tareas #179-181, plan-mvp.md bloque C1).
#
# Recibe un Incident, nunca el estado interno del detector (frontera dura,
# CONTEXTO-IA.md §3), y ensambla un Evidence con 5 secciones etiquetadas:
# metadatos, logs, snapshot, cambios recientes e historial. Cada comando
# externo tiene su propio timeout; si uno falla, esa sección queda vacía y
# marcada en `partial_errors`, pero las demás igual se recolectan -- una
# evidencia incompleta sigue siendo mejor que ninguna.
from __future__ import annotations

import logging
import socket
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from doctorjk.modelos import Evidence, Incident, SignalType, SystemSnapshot
from doctorjk.monitor import CommandResult, run_command, take_snapshot

logger = logging.getLogger(__name__)

# Ventana de la tarea #179: -5 min captura la causa, +1 min captura el efecto
# inmediato. No es configurable porque es una decisión de diseño del
# producto, no un umbral que el cliente deba ajustar.
WINDOW_BEFORE = timedelta(minutes=5)
WINDOW_AFTER = timedelta(minutes=1)

DEFAULT_COMMAND_TIMEOUT_S = 5.0
RECENT_CHANGES_WINDOW = timedelta(hours=48)
MAX_LOG_LINES = 200
HISTORY_MAX_ENTRIES = 5

DPKG_LOG_PATH = Path("/var/log/dpkg.log")
CONFIG_SEARCH_ROOT = Path("/etc")


def _formatear_marca_de_tiempo(momento: datetime) -> str:
    """journalctl y find -newermt interpretan la marca en la hora local del
    sistema; se convierte antes de formatear para no desalinear la ventana
    si el incidente llegó con tzinfo distinto (p. ej. UTC)."""
    return momento.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _resource_name(resource_key: str) -> str:
    """Signal.key trae un prefijo de categoría ("service:nombre",
    "disk:/mnt"...); esta función devuelve solo el nombre del recurso."""
    _, _, nombre = resource_key.partition(":")
    return nombre or resource_key


def truncate_oldest_lines(text: str, max_lines: int) -> tuple[str, int]:
    """Si el texto supera max_lines, recorta por el extremo más antiguo
    (tarea #179): journalctl -o short-iso devuelve las líneas en orden
    cronológico ascendente, así que las primeras son las más viejas."""
    lineas = text.splitlines()
    if len(lineas) <= max_lines:
        return text, 0
    recortadas = len(lineas) - max_lines
    return "\n".join(lineas[recortadas:]), recortadas


# --------------------------------------------------------------------- logs


def collect_journal_window(since: datetime, until: datetime, timeout_s: float) -> CommandResult:
    """Ventana general filtrada en warning o superior (tareas #179, #180).
    `-p warning` incluye prioridades 0-4 (emerg..warning)."""
    return run_command(
        [
            "journalctl",
            "--since",
            _formatear_marca_de_tiempo(since),
            "--until",
            _formatear_marca_de_tiempo(until),
            "-p",
            "warning",
            "-o",
            "short-iso",
            "--no-pager",
        ],
        timeout_s,
    )


def collect_unit_journal(unit: str, since: datetime, until: datetime, timeout_s: float) -> CommandResult:
    """Consulta sin filtro de prioridad, acotada a una sola unidad ya
    confirmada como fallida.

    Existe porque `-p warning` no alcanza para service_failed: la línea
    "Control process exited, code=exited" que trae el código de salida real
    es prioridad notice (5), por debajo de warning -- medido en beetle-vps al
    matar PostgreSQL con SIGKILL, documentado en trigger.sh. Acotar a una
    unidad ya identificada mantiene el volumen bajo sin bajar el filtro de
    prioridad global, que traería de vuelta todo el ruido informativo del
    resto del sistema.
    """
    return run_command(
        [
            "journalctl",
            "-u",
            unit,
            "--since",
            _formatear_marca_de_tiempo(since),
            "--until",
            _formatear_marca_de_tiempo(until),
            "-o",
            "short-iso",
            "--no-pager",
        ],
        timeout_s,
    )


def _seccion_logs(
    incident: Incident, since: datetime, until: datetime, timeout_s: float
) -> tuple[str, str | None]:
    partes: list[str] = []
    error: str | None = None

    resultado = collect_journal_window(since, until, timeout_s)
    if resultado.success:
        texto, recortadas = truncate_oldest_lines(resultado.stdout, MAX_LOG_LINES)
        if recortadas:
            texto = f"[TRUNCADO: se recortaron {recortadas} líneas de logs antiguos]\n{texto}"
        partes.append(f"-- Ventana general (prioridad warning o superior) --\n{texto}")
    else:
        error = f"logs (ventana general): {resultado.error}"
        partes.append(f"-- Ventana general: no disponible ({resultado.error}) --")

    if incident.signal_type is SignalType.SERVICE_FAILED:
        unidad = _resource_name(incident.resource_key)
        resultado_unidad = collect_unit_journal(unidad, since, until, timeout_s)
        if resultado_unidad.success:
            texto_unidad, recortadas = truncate_oldest_lines(resultado_unidad.stdout, MAX_LOG_LINES)
            if recortadas:
                texto_unidad = (
                    f"[TRUNCADO: se recortaron {recortadas} líneas de logs antiguos]\n{texto_unidad}"
                )
            partes.append(f"-- Unidad afectada: {unidad} (sin filtro de prioridad) --\n{texto_unidad}")
        elif error is None:
            error = f"logs (unidad {unidad}): {resultado_unidad.error}"
            partes.append(f"-- Unidad afectada {unidad}: no disponible ({resultado_unidad.error}) --")

    return "\n\n".join(partes), error


# ----------------------------------------------------------------- snapshot


def render_snapshot_text(snapshot: SystemSnapshot) -> str:
    """Convierte el SystemSnapshot ya estructurado a texto legible para el
    modelo. monitor.py no hace esto: produce datos, no redacción (frontera
    dura, CONTEXTO-IA.md §3)."""
    lineas: list[str] = [f"capturado: {snapshot.captured_at.isoformat()}"]

    if snapshot.services_available:
        if snapshot.failed_services:
            nombres = ", ".join(s.name for s in snapshot.failed_services)
            lineas.append(f"servicios fallidos: {nombres}")
        else:
            lineas.append("servicios fallidos: ninguno")
    else:
        lineas.append("servicios: no disponible")

    if snapshot.disk_available:
        for disco in snapshot.disks:
            lineas.append(f"disco {disco.target}: {disco.usage_percent}% usado ({disco.source})")
    else:
        lineas.append("disco: no disponible")

    if snapshot.memory_available and snapshot.memory is not None:
        lineas.append(
            f"memoria: {snapshot.memory.available_mb} MB disponibles de {snapshot.memory.total_mb} MB"
        )
    else:
        lineas.append("memoria: no disponible")

    if snapshot.ports_available:
        puertos = ", ".join(f"{p.address}:{p.port}" for p in snapshot.ports)
        lineas.append(f"puertos escuchando: {puertos or 'ninguno'}")
    else:
        lineas.append("puertos: no disponible")

    if snapshot.load_available and snapshot.load is not None:
        lineas.append(
            f"carga: {snapshot.load.load_1m} (1m) {snapshot.load.load_5m} (5m) "
            f"{snapshot.load.load_15m} (15m)"
        )
    else:
        lineas.append("carga: no disponible")

    return "\n".join(lineas)


# ------------------------------------------------------------ cambios recientes


def parse_dpkg_log(text: str, since: datetime) -> tuple[str, ...]:
    """Extrae líneas de instalación/actualización de paquetes desde `since`.

    Formato real de /var/log/dpkg.log: "AAAA-MM-DD HH:MM:SS accion paquete
    version1 version2 ...". `since` llega con tzinfo (UTC normalmente) y el
    log está en hora local del sistema, igual que journalctl.
    """
    desde_local_naive = since.astimezone().replace(tzinfo=None)
    resultado: list[str] = []
    for linea in text.splitlines():
        columnas = linea.split(" ", 3)
        if len(columnas) < 3:
            continue
        fecha_str, hora_str, accion = columnas[0], columnas[1], columnas[2]
        if accion not in ("install", "upgrade"):
            continue
        try:
            momento = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if momento >= desde_local_naive:
            resultado.append(linea)
    return tuple(resultado)


def read_dpkg_log(path: Path) -> CommandResult:
    try:
        return CommandResult(stdout=path.read_text(encoding="utf-8", errors="replace"), success=True, error=None)
    except OSError as error:
        mensaje = f"no se pudo leer {path}: {error}"
        logger.warning(mensaje)
        return CommandResult(stdout="", success=False, error=mensaje)


def _run_find_tolerando_permisos(argv: list[str], timeout_s: float) -> CommandResult:
    """Variante de run_command() solo para `find`.

    `find` bajo /etc corriendo como el usuario sin privilegios `doctorjk`
    (CONTEXTO-IA.md §8.5) topa con subdirectorios sin permiso de lectura
    (sudoers.d, ssl/private...) y termina con código 1 aunque haya listado
    bien el resto de las rutas. run_command() trataría ese 1 como fallo total
    y descartaría una sección que en realidad sí tiene datos útiles; acá un
    código 1 con stdout se toma como éxito parcial. Un código distinto de 0
    y 1 sí es un fallo real (find mal invocado, por ejemplo).
    """
    try:
        completado = subprocess.run(
            argv,
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

    if completado.returncode not in (0, 1):
        mensaje = f"{argv[0]} terminó con código {completado.returncode}: {completado.stderr.strip()}"
        logger.warning(mensaje)
        return CommandResult(stdout=completado.stdout, success=False, error=mensaje)

    return CommandResult(stdout=completado.stdout, success=True, error=None)


def collect_modified_configs(since: datetime, root: Path, timeout_s: float) -> CommandResult:
    """Lista rutas (no contenido) de archivos bajo `root` modificados desde
    `since`. Nunca lee el contenido: podría traer secretos (CONTEXTO-IA.md
    §8.5); solo el nombre del archivo ya orienta el diagnóstico."""
    return _run_find_tolerando_permisos(
        ["find", str(root), "-type", "f", "-newermt", _formatear_marca_de_tiempo(since)],
        timeout_s,
    )


def _seccion_cambios(
    since: datetime,
    timeout_s: float,
    dpkg_log_path: Path,
    config_search_root: Path,
) -> tuple[str, str | None]:
    partes: list[str] = []
    error: str | None = None

    resultado_dpkg = read_dpkg_log(dpkg_log_path)
    if resultado_dpkg.success:
        paquetes = parse_dpkg_log(resultado_dpkg.stdout, since)
        texto_paquetes = "\n".join(paquetes) if paquetes else "sin instalaciones/actualizaciones en 48 h"
        partes.append(f"-- Paquetes (48 h) --\n{texto_paquetes}")
    else:
        error = f"paquetes: {resultado_dpkg.error}"
        partes.append(f"-- Paquetes: no disponible ({resultado_dpkg.error}) --")

    resultado_configs = collect_modified_configs(since, config_search_root, timeout_s)
    if resultado_configs.success:
        rutas = [linea for linea in resultado_configs.stdout.splitlines() if linea.strip()]
        texto_configs = "\n".join(rutas) if rutas else "sin archivos modificados en 48 h"
        partes.append(f"-- Configuración modificada en {config_search_root} (48 h) --\n{texto_configs}")
    elif error is None:
        error = f"configs: {resultado_configs.error}"
        partes.append(f"-- Configuración modificada: no disponible ({resultado_configs.error}) --")

    return "\n\n".join(partes), error


# ----------------------------------------------------------------- historial


def _seccion_historial(reports_dir: Path) -> tuple[str, str | None]:
    try:
        informes = sorted(reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError as error:
        mensaje = f"historial: no se pudo leer {reports_dir}: {error}"
        return f"sin historial disponible ({error})", mensaje

    if not informes:
        return "sin incidentes previos registrados", None

    nombres = "\n".join(p.name for p in informes[:HISTORY_MAX_ENTRIES])
    return nombres, None


# ------------------------------------------------------------------ metadatos


def _seccion_metadatos(incident: Incident, generated_at: datetime) -> str:
    confirmado = incident.confirmed_at.isoformat() if incident.confirmed_at else "desconocido"
    return "\n".join(
        [
            f"host: {socket.gethostname()}",
            f"tipo de incidente: {incident.signal_type.value}",
            f"recurso: {_resource_name(incident.resource_key)}",
            f"inicio: {incident.started_at.isoformat()}",
            f"confirmado: {confirmado}",
            f"informe generado: {generated_at.isoformat()}",
        ]
    )


# --------------------------------------------------------------- ensamblado


def collect_evidence(
    incident: Incident,
    reports_dir: Path,
    now: datetime,
    command_timeout_s: float = DEFAULT_COMMAND_TIMEOUT_S,
    dpkg_log_path: Path = DPKG_LOG_PATH,
    config_search_root: Path = CONFIG_SEARCH_ROOT,
) -> Evidence:
    """Punto de entrada del recolector: recibe un Incident ya confirmado y
    arma la evidencia completa. No conoce el estado interno del detector ni
    decide nada sobre incidentes -- solo recolecta (frontera dura). Una
    sección que falla no descarta las demás: el error queda en
    `partial_errors` y el texto de esa sección lo explica.
    """
    if incident.confirmed_at is None:
        raise ValueError("incident.confirmed_at es obligatorio para recolectar evidencia")

    desde = incident.confirmed_at - WINDOW_BEFORE
    hasta = incident.confirmed_at + WINDOW_AFTER
    desde_cambios = incident.confirmed_at - RECENT_CHANGES_WINDOW

    errores: list[str] = []

    metadatos = _seccion_metadatos(incident, now)

    logs, error_logs = _seccion_logs(incident, desde, hasta, command_timeout_s)
    if error_logs:
        errores.append(error_logs)

    snapshot_texto = render_snapshot_text(take_snapshot(command_timeout_s))

    cambios, error_cambios = _seccion_cambios(
        desde_cambios, command_timeout_s, dpkg_log_path, config_search_root
    )
    if error_cambios:
        errores.append(error_cambios)

    historial, error_historial = _seccion_historial(reports_dir)
    if error_historial:
        errores.append(error_historial)

    raw_text = "\n\n".join(
        [
            "=== METADATOS ===\n" + metadatos,
            "=== LOGS ===\n" + logs,
            "=== SNAPSHOT ===\n" + snapshot_texto,
            "=== CAMBIOS RECIENTES ===\n" + cambios,
            "=== HISTORIAL ===\n" + historial,
        ]
    )

    return Evidence(
        incident=incident,
        generated_at=now,
        metadata_text=metadatos,
        logs_text=logs,
        snapshot_text=snapshot_texto,
        changes_text=cambios,
        history_text=historial,
        raw_text=raw_text,
        partial_errors=tuple(errores),
    )
