# Recolector: arma la ventana de evidencia alrededor de un incidente ya
# confirmado por el detector, la acota a un presupuesto de tokens y guarda
# una copia cruda sin sanitizar en disco (tareas #179-183, plan-mvp.md
# bloques C1 y C2).
#
# Recibe un Incident, nunca el estado interno del detector (frontera dura,
# CONTEXTO-IA.md §3), y ensambla un Evidence con 5 secciones etiquetadas:
# metadatos, logs, snapshot, cambios recientes e historial. Cada comando
# externo tiene su propio timeout; si uno falla, esa sección queda vacía y
# marcada en `partial_errors`, pero las demás igual se recolectan -- una
# evidencia incompleta sigue siendo mejor que ninguna.
from __future__ import annotations

import logging
import os
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

# Tarea #182: heurística fijada por la tarea (1 token ≈ 4 caracteres) y
# presupuesto objetivo de ~10k tokens para el bloque de evidencia completo.
CHARS_PER_TOKEN_ESTIMATE = 4
TOKEN_BUDGET_DEFAULT = 10_000
# Piso de líneas de log por debajo del cual no se sigue recortando aunque el
# presupuesto no alcance: sin esto, un incidente muy ruidoso podría vaciar
# la sección de logs por completo.
LOG_LINES_FLOOR = 20


def _format_timestamp(moment: datetime) -> str:
    """journalctl y find -newermt interpretan la marca en la hora local del
    sistema; se convierte antes de formatear para no desalinear la ventana
    si el incidente llegó con tzinfo distinto (p. ej. UTC)."""
    return moment.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _resource_name(resource_key: str) -> str:
    """Signal.key trae un prefijo de categoría ("service:nombre",
    "disk:/mnt"...); esta función devuelve solo el nombre del recurso."""
    _, _, name = resource_key.partition(":")
    return name or resource_key


def truncate_oldest_lines(text: str, max_lines: int) -> tuple[str, int]:
    """Si el texto supera max_lines, recorta por el extremo más antiguo
    (tarea #179): journalctl -o short-iso devuelve las líneas en orden
    cronológico ascendente, así que las primeras son las más viejas."""
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text, 0
    trimmed = len(lines) - max_lines
    return "\n".join(lines[trimmed:]), trimmed


# --------------------------------------------------------------------- logs


def collect_journal_window(since: datetime, until: datetime, timeout_s: float) -> CommandResult:
    """Ventana general filtrada en warning o superior (tareas #179, #180).
    `-p warning` incluye prioridades 0-4 (emerg..warning)."""
    return run_command(
        [
            "journalctl",
            "--since",
            _format_timestamp(since),
            "--until",
            _format_timestamp(until),
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
            _format_timestamp(since),
            "--until",
            _format_timestamp(until),
            "-o",
            "short-iso",
            "--no-pager",
        ],
        timeout_s,
    )


def _logs_section(
    incident: Incident, since: datetime, until: datetime, timeout_s: float
) -> tuple[str, str | None]:
    parts: list[str] = []
    error: str | None = None

    result = collect_journal_window(since, until, timeout_s)
    if result.success:
        text, trimmed = truncate_oldest_lines(result.stdout, MAX_LOG_LINES)
        if trimmed:
            text = f"[TRUNCADO: se recortaron {trimmed} líneas de logs antiguos]\n{text}"
        parts.append(f"-- Ventana general (prioridad warning o superior) --\n{text}")
    else:
        error = f"logs (ventana general): {result.error}"
        parts.append(f"-- Ventana general: no disponible ({result.error}) --")

    if incident.signal_type is SignalType.SERVICE_FAILED:
        unit = _resource_name(incident.resource_key)
        unit_result = collect_unit_journal(unit, since, until, timeout_s)
        if unit_result.success:
            unit_text, trimmed = truncate_oldest_lines(unit_result.stdout, MAX_LOG_LINES)
            if trimmed:
                unit_text = (
                    f"[TRUNCADO: se recortaron {trimmed} líneas de logs antiguos]\n{unit_text}"
                )
            parts.append(f"-- Unidad afectada: {unit} (sin filtro de prioridad) --\n{unit_text}")
        elif error is None:
            error = f"logs (unidad {unit}): {unit_result.error}"
            parts.append(f"-- Unidad afectada {unit}: no disponible ({unit_result.error}) --")

    return "\n\n".join(parts), error


# ----------------------------------------------------------------- snapshot


def render_snapshot_text(snapshot: SystemSnapshot) -> str:
    """Convierte el SystemSnapshot ya estructurado a texto legible para el
    modelo. monitor.py no hace esto: produce datos, no redacción (frontera
    dura, CONTEXTO-IA.md §3)."""
    lines: list[str] = [f"capturado: {snapshot.captured_at.isoformat()}"]

    if snapshot.services_available:
        if snapshot.failed_services:
            names = ", ".join(s.name for s in snapshot.failed_services)
            lines.append(f"servicios fallidos: {names}")
        else:
            lines.append("servicios fallidos: ninguno")
    else:
        lines.append("servicios: no disponible")

    if snapshot.disk_available:
        for disk in snapshot.disks:
            lines.append(f"disco {disk.target}: {disk.usage_percent}% usado ({disk.source})")
    else:
        lines.append("disco: no disponible")

    if snapshot.memory_available and snapshot.memory is not None:
        lines.append(
            f"memoria: {snapshot.memory.available_mb} MB disponibles de {snapshot.memory.total_mb} MB"
        )
    else:
        lines.append("memoria: no disponible")

    if snapshot.ports_available:
        ports = ", ".join(f"{p.address}:{p.port}" for p in snapshot.ports)
        lines.append(f"puertos escuchando: {ports or 'ninguno'}")
    else:
        lines.append("puertos: no disponible")

    if snapshot.load_available and snapshot.load is not None:
        lines.append(
            f"carga: {snapshot.load.load_1m} (1m) {snapshot.load.load_5m} (5m) "
            f"{snapshot.load.load_15m} (15m)"
        )
    else:
        lines.append("carga: no disponible")

    return "\n".join(lines)


# ------------------------------------------------------------ cambios recientes


def parse_dpkg_log(text: str, since: datetime) -> tuple[str, ...]:
    """Extrae líneas de instalación/actualización de paquetes desde `since`.

    Formato real de /var/log/dpkg.log: "AAAA-MM-DD HH:MM:SS accion paquete
    version1 version2 ...". `since` llega con tzinfo (UTC normalmente) y el
    log está en hora local del sistema, igual que journalctl.
    """
    since_local_naive = since.astimezone().replace(tzinfo=None)
    result: list[str] = []
    for line in text.splitlines():
        columns = line.split(" ", 3)
        if len(columns) < 3:
            continue
        date_str, time_str, action = columns[0], columns[1], columns[2]
        if action not in ("install", "upgrade"):
            continue
        try:
            moment = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if moment >= since_local_naive:
            result.append(line)
    return tuple(result)


def read_dpkg_log(path: Path) -> CommandResult:
    try:
        return CommandResult(stdout=path.read_text(encoding="utf-8", errors="replace"), success=True, error=None)
    except OSError as error:
        message = f"no se pudo leer {path}: {error}"
        logger.warning(message)
        return CommandResult(stdout="", success=False, error=message)


def _run_find_tolerating_permission_errors(argv: list[str], timeout_s: float) -> CommandResult:
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
        completed = subprocess.run(
            argv,
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

    if completed.returncode not in (0, 1):
        message = f"{argv[0]} terminó con código {completed.returncode}: {completed.stderr.strip()}"
        logger.warning(message)
        return CommandResult(stdout=completed.stdout, success=False, error=message)

    return CommandResult(stdout=completed.stdout, success=True, error=None)


def collect_modified_configs(since: datetime, root: Path, timeout_s: float) -> CommandResult:
    """Lista rutas (no contenido) de archivos bajo `root` modificados desde
    `since`. Nunca lee el contenido: podría traer secretos (CONTEXTO-IA.md
    §8.5); solo el nombre del archivo ya orienta el diagnóstico."""
    return _run_find_tolerating_permission_errors(
        ["find", str(root), "-type", "f", "-newermt", _format_timestamp(since)],
        timeout_s,
    )


def _changes_section(
    since: datetime,
    timeout_s: float,
    dpkg_log_path: Path,
    config_search_root: Path,
) -> tuple[str, str | None]:
    parts: list[str] = []
    error: str | None = None

    dpkg_result = read_dpkg_log(dpkg_log_path)
    if dpkg_result.success:
        packages = parse_dpkg_log(dpkg_result.stdout, since)
        packages_text = "\n".join(packages) if packages else "sin instalaciones/actualizaciones en 48 h"
        parts.append(f"-- Paquetes (48 h) --\n{packages_text}")
    else:
        error = f"paquetes: {dpkg_result.error}"
        parts.append(f"-- Paquetes: no disponible ({dpkg_result.error}) --")

    configs_result = collect_modified_configs(since, config_search_root, timeout_s)
    if configs_result.success:
        paths = [line for line in configs_result.stdout.splitlines() if line.strip()]
        configs_text = "\n".join(paths) if paths else "sin archivos modificados en 48 h"
        parts.append(f"-- Configuración modificada en {config_search_root} (48 h) --\n{configs_text}")
    elif error is None:
        error = f"configs: {configs_result.error}"
        parts.append(f"-- Configuración modificada: no disponible ({configs_result.error}) --")

    return "\n\n".join(parts), error


# ----------------------------------------------------------------- historial


def _history_section(reports_dir: Path) -> tuple[str, str | None]:
    try:
        reports = sorted(reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError as error:
        message = f"historial: no se pudo leer {reports_dir}: {error}"
        return f"sin historial disponible ({error})", message

    if not reports:
        return "sin incidentes previos registrados", None

    names = "\n".join(p.name for p in reports[:HISTORY_MAX_ENTRIES])
    return names, None


# ------------------------------------------------------------------ metadatos


def _metadata_section(incident: Incident, generated_at: datetime) -> str:
    confirmed = incident.confirmed_at.isoformat() if incident.confirmed_at else "desconocido"
    return "\n".join(
        [
            f"host: {socket.gethostname()}",
            f"tipo de incidente: {incident.signal_type.value}",
            f"recurso: {_resource_name(incident.resource_key)}",
            f"inicio: {incident.started_at.isoformat()}",
            f"confirmado: {confirmed}",
            f"informe generado: {generated_at.isoformat()}",
        ]
    )


# --------------------------------------------------------------- ensamblado


def _assemble_raw_text(metadata: str, logs: str, snapshot: str, changes: str, history: str) -> str:
    return "\n\n".join(
        [
            "=== METADATOS ===\n" + metadata,
            "=== LOGS ===\n" + logs,
            "=== SNAPSHOT ===\n" + snapshot,
            "=== CAMBIOS RECIENTES ===\n" + changes,
            "=== HISTORIAL ===\n" + history,
        ]
    )


def estimate_tokens(text: str) -> int:
    """Heurística fijada por la tarea #182: 1 token ≈ 4 caracteres."""
    return len(text) // CHARS_PER_TOKEN_ESTIMATE


def _reduce_snapshot_to_incident_category(snapshot_text: str, signal_type: SignalType) -> str:
    """#182 paso 2: si truncar logs no alcanza, el snapshot se reduce a la
    categoría del incidente (p. ej. solo líneas de disco si fue disk_full).

    Sin los umbrales del cliente (config.py, capa superior de este módulo)
    no se puede decidir "anómalo" métrica por métrica aquí; la categoría del
    incidente ya confirmado es la mejor aproximación disponible sin acoplar
    el recolector a la configuración (CONTEXTO-IA.md §8.1: la config se
    inyecta desde arriba, no se lee dentro de la lógica de negocio).
    """
    prefix_by_type = {
        SignalType.DISK_FULL: "disco ",
        SignalType.MEMORY_LOW: "memoria:",
        SignalType.SERVICE_FAILED: "servicios fallidos:",
        SignalType.PORT_DOWN: "puertos",
    }
    prefix = prefix_by_type.get(signal_type)
    if prefix is None:
        return snapshot_text

    lines = snapshot_text.splitlines()
    relevant = [l for l in lines if l.startswith("capturado") or l.startswith(prefix)]
    if not relevant:
        return snapshot_text
    return "\n".join(relevant) + "\n[SNAPSHOT REDUCIDO: solo métricas relacionadas con el incidente]"


def apply_token_budget(
    metadata_text: str,
    logs_text: str,
    snapshot_text: str,
    changes_text: str,
    history_text: str,
    signal_type: SignalType,
    budget_tokens: int = TOKEN_BUDGET_DEFAULT,
) -> tuple[str, str, str]:
    """Acota la evidencia al presupuesto de tokens (tarea #182).

    Orden de recorte: primero los logs más antiguos (manteniendo un piso de
    LOG_LINES_FLOOR líneas cercanas al incidente), después el snapshot
    reducido a la categoría del incidente. Metadatos, cambios recientes e
    historial nunca se tocan -- metadatos por mandato explícito de la tarea;
    cambios e historial porque ya son compactos por construcción.

    Devuelve (logs_text, snapshot_text, raw_text) ya ajustados.
    """
    current_logs = logs_text
    current_snapshot = snapshot_text
    raw = _assemble_raw_text(metadata_text, current_logs, current_snapshot, changes_text, history_text)

    if estimate_tokens(raw) <= budget_tokens:
        return current_logs, current_snapshot, raw

    original_lines = logs_text.splitlines()
    max_lines = len(original_lines)
    while True:
        max_lines = max(LOG_LINES_FLOOR, max_lines - max(1, max_lines // 5))
        trimmed_text, trimmed_count = truncate_oldest_lines("\n".join(original_lines), max_lines)
        # La nota de truncado se agrega DENTRO del candidato antes de medir:
        # su propio tamaño también cuenta para el presupuesto, si no la
        # comparación de abajo subestima el resultado final.
        current_logs = (
            f"[TRUNCADO: se recortaron {trimmed_count} líneas de logs antiguos]\n{trimmed_text}"
            if trimmed_count
            else trimmed_text
        )
        raw = _assemble_raw_text(metadata_text, current_logs, current_snapshot, changes_text, history_text)
        if estimate_tokens(raw) <= budget_tokens or max_lines == LOG_LINES_FLOOR:
            break

    if estimate_tokens(raw) > budget_tokens:
        current_snapshot = _reduce_snapshot_to_incident_category(snapshot_text, signal_type)
        raw = _assemble_raw_text(metadata_text, current_logs, current_snapshot, changes_text, history_text)

    return current_logs, current_snapshot, raw


def collect_evidence(
    incident: Incident,
    reports_dir: Path,
    now: datetime,
    command_timeout_s: float = DEFAULT_COMMAND_TIMEOUT_S,
    dpkg_log_path: Path = DPKG_LOG_PATH,
    config_search_root: Path = CONFIG_SEARCH_ROOT,
    token_budget: int = TOKEN_BUDGET_DEFAULT,
) -> Evidence:
    """Punto de entrada del recolector: recibe un Incident ya confirmado y
    arma la evidencia completa, acotada al presupuesto de tokens. No conoce
    el estado interno del detector ni decide nada sobre incidentes -- solo
    recolecta (frontera dura). Una sección que falla no descarta las demás:
    el error queda en `partial_errors` y el texto de esa sección lo explica.
    """
    if incident.confirmed_at is None:
        raise ValueError("incident.confirmed_at es obligatorio para recolectar evidencia")

    since = incident.confirmed_at - WINDOW_BEFORE
    until = incident.confirmed_at + WINDOW_AFTER
    changes_since = incident.confirmed_at - RECENT_CHANGES_WINDOW

    errors: list[str] = []

    metadata = _metadata_section(incident, now)

    logs, logs_error = _logs_section(incident, since, until, command_timeout_s)
    if logs_error:
        errors.append(logs_error)

    snapshot_text = render_snapshot_text(take_snapshot(command_timeout_s))

    changes, changes_error = _changes_section(
        changes_since, command_timeout_s, dpkg_log_path, config_search_root
    )
    if changes_error:
        errors.append(changes_error)

    history, history_error = _history_section(reports_dir)
    if history_error:
        errors.append(history_error)

    logs, snapshot_text, raw_text = apply_token_budget(
        metadata, logs, snapshot_text, changes, history, incident.signal_type, token_budget
    )

    return Evidence(
        incident=incident,
        generated_at=now,
        metadata_text=metadata,
        logs_text=logs,
        snapshot_text=snapshot_text,
        changes_text=changes,
        history_text=history,
        raw_text=raw_text,
        partial_errors=tuple(errors),
    )


# --------------------------------------------------------- evidencia cruda


def _evidence_filename(incident: Incident) -> str:
    assert incident.confirmed_at is not None  # ya validado en collect_evidence
    stamp = incident.confirmed_at.strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{incident.signal_type.value}_evidencia.txt"


def _resolve_collision_free_name(reports_dir: Path, incident: Incident) -> Path:
    """Tarea #183: si ya existe un archivo con ese nombre (dos incidentes
    del mismo tipo confirmados en el mismo segundo), se agrega un sufijo
    numérico en vez de pisar la evidencia anterior."""
    base_name = _evidence_filename(incident)
    destination = reports_dir / base_name
    suffix = 2
    root = base_name[: -len("_evidencia.txt")]
    while destination.exists():
        destination = reports_dir / f"{root}_{suffix}_evidencia.txt"
        suffix += 1
    return destination


def write_raw_evidence(evidence: Evidence, reports_dir: Path) -> Path:
    """Guarda la evidencia completa sin sanitizar (tarea #183).

    Esta copia nunca sale del servidor ni se envía al LLM -- eso pasa por
    sanitizador.py primero (Gate C3). Es la copia de auditoría que el
    administrador puede comparar contra lo que sí viajó. Creación atómica
    (escribir a un temporal en el mismo directorio y renombrar) y modo 600,
    porque trae los mismos datos crudos que journalctl/df/etc: pueden
    incluir IPs, credenciales o rutas reales.
    """
    reports_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = _resolve_collision_free_name(reports_dir, evidence.incident)
    temp_file = destination.parent / (destination.name + ".tmp")

    descriptor = os.open(temp_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(evidence.raw_text)
        os.replace(temp_file, destination)
    except OSError:
        temp_file.unlink(missing_ok=True)
        raise
    return destination
