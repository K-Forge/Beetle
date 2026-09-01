# Punto de entrada del agente (issue #222). Es el único proceso de larga vida
# y el único dueño del estado (plan-mvp.md §3.1): mantiene una sola instancia
# del detector, así que los contadores de persistencia y la deduplicación de
# incidentes no se reparten entre procesos efímeros.
#
# Recibe eventos de dos fuentes que confluyen en el mismo callback:
#   - el tick de polling cada --interval segundos;
#   - una señal de doctorjk-trigger.sh a través de un FIFO local.
#
# Cada muestra se normaliza a señales, pasa por el detector y, cuando este
# confirma un incidente, se ejecuta el corte vertical del Modo 1: recolectar
# evidencia, sanitizarla, diagnosticar e informar (bloque D4). --dry-run y
# --auto-fix se validan acá porque son responsabilidad del punto de entrada,
# pero no los consume nadie hasta que exista el remediador (Gate H).
from __future__ import annotations

import argparse
import logging
import os
import selectors
import signal
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Sequence

import requests

from doctorjk import informe, llm, monitor, recolector, remediador, sanitizador
from doctorjk.config import AppConfig, ConfigError, load_config
from doctorjk.detector import Detector
from doctorjk.modelos import Incident, IncidentState, SignalType, SystemSnapshot
from doctorjk.pipeline import PipelineDeps, handle_incident

logger = logging.getLogger(__name__)

DEFAULT_FIFO_PATH = "/run/doctorjk/trigger.fifo"
# Rutas que deja instalador/install.sh; --config y --prompt las sobrescriben
# para pruebas o instalaciones no estándar.
DEFAULT_CONFIG_PATH = "/etc/doctorjk/config.toml"
DEFAULT_PROMPT_PATH = "/opt/doctorjk/prompts/diagnosticador.md"
DEFAULT_SCRIPTS_DIR = "/opt/doctorjk/scripts-fix"
# Tope de incidentes esperando su ventana +1 minuto (Gate 2.2): protege la
# memoria si journalctl o systemctl se degradan y el agente confirma
# incidentes más rápido de lo que puede procesarlos.
MAX_PENDING_INCIDENTS = 50


# ------------------------------------------------------------------- CLI


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="doctorjk",
        description="Agente que detecta, diagnostica y opcionalmente corrige incidentes.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="genera y valida el plan de corrección sin ejecutar nada (Modo 3)",
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="opt-in explícito para ejecutar remediaciones (tarea #210)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="toma una sola muestra y termina; no abre el FIFO ni entra en loop",
    )
    parser.add_argument(
        "--config",
        default=os.environ.get("DOCTORJK_CONFIG_PATH", DEFAULT_CONFIG_PATH),
        help=f"ruta de config.toml (default: {DEFAULT_CONFIG_PATH})",
    )
    parser.add_argument(
        "--prompt",
        default=os.environ.get("DOCTORJK_PROMPT_PATH", DEFAULT_PROMPT_PATH),
        help=f"ruta del prompt de diagnóstico (default: {DEFAULT_PROMPT_PATH})",
    )
    parser.add_argument(
        "--scripts-dir",
        default=os.environ.get("DOCTORJK_SCRIPTS_DIR", DEFAULT_SCRIPTS_DIR),
        help=f"directorio de scripts-fix/ para el Modo 2 (default: {DEFAULT_SCRIPTS_DIR})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="segundos entre ciclos de polling; sin esto se usa intervalo_monitor_s de config.toml",
    )
    parser.add_argument(
        "--fifo-path",
        default=os.environ.get("DOCTORJK_FIFO_PATH", DEFAULT_FIFO_PATH),
        help="ruta del FIFO que escribe doctorjk-trigger.sh",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    args = parser.parse_args(argv)

    if args.auto_fix and args.dry_run:
        parser.error(
            "--auto-fix y --dry-run son incompatibles: uno ejecuta correcciones, "
            "el otro las simula sin tocar el servidor"
        )
    if args.interval is not None and args.interval <= 0:
        parser.error("--interval debe ser mayor que 0")

    return args


# ------------------------------------------------------------- construcción


@dataclass(frozen=True)
class AppContext:
    interval_s: float
    fifo_path: Path
    once: bool
    take_snapshot: Callable[[], SystemSnapshot]
    on_snapshot: Callable[[SystemSnapshot], None]
    # Gate 2.2: cuánto esperar hasta el próximo evento (tick de polling o
    # incidente pendiente que vence), dado el reloj actual. Con default
    # constante para no romper construcciones directas de AppContext en
    # tests que no ejercitan la cola de pendientes.
    next_wakeup_delay: Callable[[datetime], float] = lambda now: 30.0
    # Cierre ordenado de recursos que build_app() haya abierto (la sesión
    # HTTP del cliente LLM). No-op por default por la misma razón de arriba.
    close: Callable[[], None] = lambda: None


def log_snapshot(snapshot: SystemSnapshot) -> None:
    """Callback de solo-registro de Gate A, conservado para --once sin
    configuración y como referencia de qué trae un SystemSnapshot. El
    callback real que usa build_app() está en build_incident_pipeline()."""
    available_memory = (
        f"{snapshot.memory.available_mb} MB" if snapshot.memory else "desconocida"
    )
    logger.info(
        "muestra tomada: %d servicio(s) fallido(s), %d disco(s) leídos, "
        "memoria disponible=%s",
        len(snapshot.failed_services),
        len(snapshot.disks),
        available_memory,
    )


# --------------------------------------------------- ventana +1 minuto (Gate 2.2)


@dataclass(frozen=True)
class PendingIncident:
    """Un incidente ya confirmado, esperando a que pase la ventana +1 minuto
    de recolector.WINDOW_AFTER antes de recolectar evidencia. No se puede
    pedirle a journalctl `--until <futuro>` y esperar que invente logs que
    todavía no existen (defecto 8): hay que esperar de verdad a que ese
    minuto transcurra."""

    incident: Incident
    collect_after: datetime


def queue_pending_incident(
    queue: list[PendingIncident], incident: Incident, collect_after: datetime
) -> None:
    """Encola un incidente recién confirmado. Acotada: si journalctl o
    systemctl se degradan y el detector confirma incidentes más rápido de lo
    que el agente puede procesarlos, se descarta el más viejo en vez de
    crecer sin límite (protocolo del plan, punto 4: "limitar la cola para no
    agotar memoria")."""
    if len(queue) >= MAX_PENDING_INCIDENTS:
        discarded = queue.pop(0)
        logger.warning(
            "cola de incidentes pendientes llena (%d); se descarta sin evidencia: %s",
            MAX_PENDING_INCIDENTS,
            discarded.incident.incident_id,
        )
    queue.append(PendingIncident(incident=incident, collect_after=collect_after))


def pop_due_incidents(queue: list[PendingIncident], now: datetime) -> list[PendingIncident]:
    """Extrae de la cola, en el orden en que vencieron, los incidentes cuya
    ventana +1 minuto ya pasó. Los que todavía no vencen quedan en la cola
    para el próximo ciclo. Si el reloj saltó hacia adelante (reinicio del
    servicio, ajuste de hora), igual se procesan con lo que journalctl tenga
    disponible en ese momento -- no se inventa el minuto faltante."""
    due = [pending for pending in queue if pending.collect_after <= now]
    for pending in due:
        queue.remove(pending)
    due.sort(key=lambda pending: pending.collect_after)
    return due


def seconds_until_next_event(queue: list[PendingIncident], interval_s: float, now: datetime) -> float:
    """Cuánto falta hasta que corresponda despertar: el próximo tick de
    polling normal, o el incidente pendiente más próximo, lo que ocurra
    antes. Nunca negativo: un incidente ya vencido despierta de inmediato."""
    if not queue:
        return interval_s
    next_deadline = min(pending.collect_after for pending in queue)
    remaining = (next_deadline - now).total_seconds()
    return max(0.0, min(interval_s, remaining))


def build_pipeline_deps(config: AppConfig, session: object) -> PipelineDeps:
    """Cablea las implementaciones reales detrás de los contratos del pipeline.

    Es el único lugar donde el Modo 1 conoce módulos concretos; `pipeline.py`
    solo ve funciones. Cambiar de proveedor o de escritor de informes se hace
    acá, sin tocar la orquestación.
    """
    llm_config = llm.LLMConfig(
        base_url=config.llm_url,
        model=config.llm_model,
        api_key=config.llm_api_key,
        timeout_s=config.llm_timeout_s,
        cache_enabled=config.llm_cache,
        cache_dir=config.reports_dir / ".cache" if config.llm_cache else None,
    )

    return PipelineDeps(
        collect_evidence=lambda incident, directory, now: recolector.collect_evidence(
            incident,
            reports_dir=directory,
            now=now,
            command_timeout_s=config.command_timeout_s,
        ),
        write_raw_evidence=recolector.write_raw_evidence,
        sanitize_evidence=sanitizador.sanitize_evidence,
        diagnose=lambda sanitized, prompt: llm.diagnose(
            sanitized, prompt, llm_config, session
        ),
        save_report=informe.save_and_rotate,
    )


def on_incident(
    incident: Incident,
    prompt: str,
    reports_dir: Path,
    deps: PipelineDeps,
    now: datetime,
) -> Path | None:
    """Puente entre el detector y el pipeline. Devuelve la ruta del informe
    escrito (o None si no se pudo escribir) para que build_incident_pipeline()
    pueda anexarle el resultado del Modo 2 después.

    No lleva try/except propio (defecto 10: nada de `except Exception` a
    secas): `handle_incident()` ya garantiza no propagar los fallos de E/S
    esperables de cada etapa (recolección, evidencia cruda, informe). Si algo
    más escapa de acá es un bug real, no una falla operativa esperada, y debe
    hacer ruido en vez de esconderse.
    """
    return handle_incident(incident, prompt, reports_dir, now, deps)


def _persistence_cycles_by_type(config: AppConfig) -> dict[SignalType, int]:
    """Arma el mapeo SignalType -> ciclos que exige el Detector (Gate 1.3):
    cada tipo usa el parámetro de config.toml que le corresponde, no un
    número global único."""
    return {
        SignalType.SERVICE_FAILED: config.service_cycles,
        SignalType.DISK_FULL: config.persistence_cycles,
        SignalType.MEMORY_LOW: config.persistence_cycles,
        SignalType.PORT_DOWN: config.port_cycles,
        SignalType.PORT_OCCUPIED: config.port_cycles,
    }


def _monitored_service_names(config: AppConfig) -> frozenset[str]:
    """Unión de `servicios_vigilados` y los servicios dueños de cada puerto
    de `puertos_vigilados`: ambos necesitan su estado consultado por
    query_service_states() para que normalize_snapshot() pueda emitir
    service_failed y port_occupied correctamente."""
    return frozenset(config.monitored_services) | frozenset(
        port.service for port in config.monitored_ports
    )


def build_incident_pipeline(
    config: AppConfig,
    prompt: str,
    session: object,
    scripts_dir: Path | None = None,
    interval_s: float | None = None,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    remediation_command_prefix: tuple[str, ...] = ("sudo", "-n"),
) -> tuple[Callable[[SystemSnapshot], None], Callable[[datetime], float]]:
    """Arma el Detector de larga vida, la cola de incidentes pendientes de la
    ventana +1 minuto (Gate 2.2) y las dos piezas que el loop de main()
    necesita: el callback real de snapshot y cuánto esperar hasta el próximo
    evento. Es el único lugar donde vive el estado del Modo 1 en ejecución.

    `interval_s` es el intervalo de polling EFECTIVO (config.toml salvo
    override de --interval); si se usara siempre config.monitor_interval_s
    acá adentro, un --interval de prueba más corto no tendría ningún efecto
    sobre cuánto espera next_wakeup_delay(), solo sobre AppContext.interval_s
    -- que run() ya no usa directamente. Default a config.monitor_interval_s
    para quien llame esta función sin pasar un override.

    `now_fn` es el reloj de pared que decide si un incidente pendiente ya
    venció -- separado de `snapshot.captured_at` porque la ventana +1 minuto
    es tiempo real transcurrido, no un campo del snapshot. Inyectable para
    poder probar la cola sin depender de time.sleep() de verdad.

    `scripts_dir` habilita el Modo 2 después de cada diagnóstico (Gate 4):
    con None, remediate() nunca se llama y el comportamiento es idéntico al
    de antes de Gate 4 -- Modo 1 nunca depende de que Modo 2 esté disponible.
    `remediation_command_prefix` es ("sudo", "-n") en producción (doctorjk no
    tiene privilegios propios, ver remediador.py); vacío en pruebas que
    corren un script de prueba sin sudoers real.
    """
    effective_interval = interval_s if interval_s is not None else config.monitor_interval_s
    detector = Detector(
        persistence_cycles=_persistence_cycles_by_type(config),
        cooldown_cycles=config.cooldown_cycles,
    )
    deps = build_pipeline_deps(config, session)
    pending: list[PendingIncident] = []

    def process_snapshot(snapshot: SystemSnapshot) -> None:
        signals = monitor.normalize_snapshot(
            snapshot,
            disk_pct_threshold=config.disk_pct_threshold,
            memory_available_mb_threshold=config.memory_available_mb_threshold,
            monitored_ports=config.monitored_ports,
            monitored_mount_points=config.monitored_mount_points,
        )
        for transition in detector.evaluate(signals, snapshot.captured_at):
            if transition.new_state is IncidentState.INCIDENT and transition.incident is not None:
                due_at = snapshot.captured_at + recolector.WINDOW_AFTER
                queue_pending_incident(pending, transition.incident, due_at)
                logger.info(
                    "incidente confirmado, evidencia programada para %s: clave=%s",
                    due_at.isoformat(),
                    transition.key,
                )
            elif transition.new_state is IncidentState.RESOLVED:
                # Resolución: se registra, no se vuelve a invocar al LLM. El
                # informe del incidente original ya cubrió el diagnóstico.
                logger.info(
                    "incidente resuelto sin diagnóstico adicional: clave=%s tipo=%s",
                    transition.key,
                    transition.signal_type.value,
                )

        now = now_fn()
        for pending_incident in pop_due_incidents(pending, now):
            report_path = on_incident(pending_incident.incident, prompt, config.reports_dir, deps, now)
            # Remediar no depende de que el informe se haya podido escribir
            # (hallazgo de auditoría #7): un disco lleno que impide guardar
            # el informe es justo el caso donde más importa que Modo 2 igual
            # actúe. La falla de persistencia ya quedó en journald por su
            # cuenta (informe.save_and_rotate); si no hay report_path, la
            # auditoría de la corrección también solo va a journald.
            if scripts_dir is not None:
                resultado = remediador.remediate(
                    pending_incident.incident,
                    config,
                    scripts_dir,
                    command_prefix=remediation_command_prefix,
                )
                if report_path is not None:
                    informe.append_remediation(report_path, resultado)

    def next_wait(now: datetime) -> float:
        return seconds_until_next_event(pending, effective_interval, now)

    return process_snapshot, next_wait


def build_app(args: argparse.Namespace) -> AppContext:
    """Composition root del Modo 1: carga configuración y prompt una sola
    vez, arma la sesión HTTP real y cablea el pipeline completo. Antes de
    Gate 2 esto dejaba on_snapshot=log_snapshot y nada de lo cargado se
    usaba (defecto 1); ahora es el único lugar donde el ejecutable conoce
    módulos concretos, igual que build_pipeline_deps() para el pipeline.
    """
    config_path = Path(args.config)
    try:
        config = load_config(config_path)
    except ConfigError as error:
        raise SystemExit(f"configuración inválida en {config_path}: {error}") from error

    prompt_path = Path(args.prompt)
    try:
        prompt = prompt_path.read_text(encoding="utf-8")
    except OSError as error:
        raise SystemExit(f"no se pudo leer el prompt en {prompt_path}: {error}") from error

    interval_s = args.interval if args.interval is not None else config.monitor_interval_s

    session = requests.Session()
    on_snapshot, next_wait = build_incident_pipeline(
        config, prompt, session, scripts_dir=Path(args.scripts_dir), interval_s=interval_s
    )
    monitored_service_names = _monitored_service_names(config)

    return AppContext(
        interval_s=interval_s,
        fifo_path=Path(args.fifo_path),
        once=args.once,
        take_snapshot=lambda: monitor.take_snapshot(
            timeout_s=config.command_timeout_s, monitored_services=monitored_service_names
        ),
        on_snapshot=on_snapshot,
        next_wakeup_delay=next_wait,
        close=session.close,
    )


# ------------------------------------------------------------------- FIFO


def ensure_fifo(path: Path) -> bool:
    """Crea el FIFO de trigger si hace falta. Devuelve False si no se pudo
    preparar (sin permisos, ruta inválida) en vez de abortar: el agente sigue
    funcionando en modo solo-polling, que es degradado pero seguro."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if not path.exists():
            os.mkfifo(path, mode=0o600)
        return True
    except OSError as error:
        logger.warning(
            "no se pudo preparar el FIFO %s: %s; sigue en modo solo-polling",
            path,
            error,
        )
        return False


def open_fifo_nonblocking(path: Path) -> int | None:
    """Abre el FIFO en lectura/escritura no bloqueante.

    Abrirlo también para escritura evita que el descriptor reciba EOF cada vez
    que trigger.sh cierra su extremo de escritura -- sin esto, selectors
    entraría en un bucle ocupado marcando el FIFO como listo una y otra vez.
    """
    try:
        return os.open(str(path), os.O_RDWR | os.O_NONBLOCK)
    except OSError as error:
        logger.warning(
            "no se pudo abrir el FIFO %s: %s; sigue en modo solo-polling",
            path,
            error,
        )
        return None


def wait_for_next_cycle(fifo_fd: int | None, interval_s: float) -> str:
    """Espera hasta el próximo tick de polling o hasta que llegue una señal
    del trigger, lo que ocurra primero. Devuelve "trigger" o "tick"; en ambos
    casos el llamador toma una muestra y la entrega al mismo callback."""
    if fifo_fd is None:
        time.sleep(interval_s)
        return "tick"

    selector = selectors.DefaultSelector()
    selector.register(fifo_fd, selectors.EVENT_READ)
    try:
        events = selector.select(timeout=interval_s)
        if not events:
            return "tick"
        try:
            os.read(fifo_fd, 4096)  # drena la señal; el contenido no importa
        except OSError:
            pass
        return "trigger"
    finally:
        selector.close()


# --------------------------------------------------------------------- loop


def run(context: AppContext) -> None:
    if context.once:
        try:
            context.on_snapshot(context.take_snapshot())
        finally:
            context.close()
        return

    fifo_fd = None
    if ensure_fifo(context.fifo_path):
        fifo_fd = open_fifo_nonblocking(context.fifo_path)

    stop = threading.Event()

    def handle_sigterm(signum: int, frame: object) -> None:
        logger.info("SIGTERM recibido, cerrando de forma ordenada")
        stop.set()

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        while not stop.is_set():
            # Gate 2.2: la espera no es siempre context.interval_s -- se
            # acorta si hay un incidente pendiente cuya ventana +1 minuto
            # vence antes del próximo tick de polling.
            wait_s = context.next_wakeup_delay(datetime.now(timezone.utc))
            reason = wait_for_next_cycle(fifo_fd, wait_s)
            if stop.is_set():
                break
            logger.debug("ciclo disparado por: %s (espera=%.1fs)", reason, wait_s)
            context.on_snapshot(context.take_snapshot())
    finally:
        if fifo_fd is not None:
            os.close(fifo_fd)
        context.close()


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    run(build_app(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
