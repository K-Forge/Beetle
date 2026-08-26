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


def _armar_raw_text(metadatos: str, logs: str, snapshot: str, cambios: str, historial: str) -> str:
    return "\n\n".join(
        [
            "=== METADATOS ===\n" + metadatos,
            "=== LOGS ===\n" + logs,
            "=== SNAPSHOT ===\n" + snapshot,
            "=== CAMBIOS RECIENTES ===\n" + cambios,
            "=== HISTORIAL ===\n" + historial,
        ]
    )


def estimate_tokens(text: str) -> int:
    """Heurística fijada por la tarea #182: 1 token ≈ 4 caracteres."""
    return len(text) // CHARS_PER_TOKEN_ESTIMATE


def _reducir_snapshot_a_categoria_del_incidente(snapshot_text: str, signal_type: SignalType) -> str:
    """#182 paso 2: si truncar logs no alcanza, el snapshot se reduce a la
    categoría del incidente (p. ej. solo líneas de disco si fue disk_full).

    Sin los umbrales del cliente (config.py, capa superior de este módulo)
    no se puede decidir "anómalo" métrica por métrica aquí; la categoría del
    incidente ya confirmado es la mejor aproximación disponible sin acoplar
    el recolector a la configuración (CONTEXTO-IA.md §8.1: la config se
    inyecta desde arriba, no se lee dentro de la lógica de negocio).
    """
    prefijo_por_tipo = {
        SignalType.DISK_FULL: "disco ",
        SignalType.MEMORY_LOW: "memoria:",
        SignalType.SERVICE_FAILED: "servicios fallidos:",
        SignalType.PORT_DOWN: "puertos",
    }
    prefijo = prefijo_por_tipo.get(signal_type)
    if prefijo is None:
        return snapshot_text

    lineas = snapshot_text.splitlines()
    relevantes = [l for l in lineas if l.startswith("capturado") or l.startswith(prefijo)]
    if not relevantes:
        return snapshot_text
    return "\n".join(relevantes) + "\n[SNAPSHOT REDUCIDO: solo métricas relacionadas con el incidente]"


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
    logs_actual = logs_text
    snapshot_actual = snapshot_text
    raw = _armar_raw_text(metadata_text, logs_actual, snapshot_actual, changes_text, history_text)

    if estimate_tokens(raw) <= budget_tokens:
        return logs_actual, snapshot_actual, raw

    lineas_originales = logs_text.splitlines()
    max_lineas = len(lineas_originales)
    while True:
        max_lineas = max(LOG_LINES_FLOOR, max_lineas - max(1, max_lineas // 5))
        recortado, recortadas = truncate_oldest_lines("\n".join(lineas_originales), max_lineas)
        # La nota de truncado se agrega DENTRO del candidato antes de medir:
        # su propio tamaño también cuenta para el presupuesto, si no la
        # comparación de abajo subestima el resultado final.
        logs_actual = (
            f"[TRUNCADO: se recortaron {recortadas} líneas de logs antiguos]\n{recortado}"
            if recortadas
            else recortado
        )
        raw = _armar_raw_text(metadata_text, logs_actual, snapshot_actual, changes_text, history_text)
        if estimate_tokens(raw) <= budget_tokens or max_lineas == LOG_LINES_FLOOR:
            break

    if estimate_tokens(raw) > budget_tokens:
        snapshot_actual = _reducir_snapshot_a_categoria_del_incidente(snapshot_text, signal_type)
        raw = _armar_raw_text(metadata_text, logs_actual, snapshot_actual, changes_text, history_text)

    return logs_actual, snapshot_actual, raw


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

    logs, snapshot_texto, raw_text = apply_token_budget(
        metadatos, logs, snapshot_texto, cambios, historial, incident.signal_type, token_budget
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


# --------------------------------------------------------- evidencia cruda


def _nombre_evidencia(incident: Incident) -> str:
    assert incident.confirmed_at is not None  # ya validado en collect_evidence
    marca = incident.confirmed_at.strftime("%Y%m%d_%H%M%S")
    return f"{marca}_{incident.signal_type.value}_evidencia.txt"


def _resolver_nombre_sin_colision(reports_dir: Path, incident: Incident) -> Path:
    """Tarea #183: si ya existe un archivo con ese nombre (dos incidentes
    del mismo tipo confirmados en el mismo segundo), se agrega un sufijo
    numérico en vez de pisar la evidencia anterior."""
    nombre_base = _nombre_evidencia(incident)
    destino = reports_dir / nombre_base
    sufijo = 2
    raiz = nombre_base[: -len("_evidencia.txt")]
    while destino.exists():
        destino = reports_dir / f"{raiz}_{sufijo}_evidencia.txt"
        sufijo += 1
    return destino


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
    destino = _resolver_nombre_sin_colision(reports_dir, evidence.incident)
    temporal = destino.parent / (destino.name + ".tmp")

    descriptor = os.open(temporal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as archivo:
            archivo.write(evidence.raw_text)
        os.replace(temporal, destino)
    except OSError:
        temporal.unlink(missing_ok=True)
        raise
    return destino
