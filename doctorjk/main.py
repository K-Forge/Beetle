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

from doctorjk import informe, llm, monitor, recolector, sanitizador
from doctorjk.config import AppConfig
from doctorjk.detector import Detector
from doctorjk.modelos import Incident, SystemSnapshot
from doctorjk.pipeline import PipelineDeps, handle_incident

logger = logging.getLogger(__name__)

DEFAULT_FIFO_PATH = "/run/doctorjk/trigger.fifo"
DEFAULT_INTERVAL_S = 30.0


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
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_S,
        help=f"segundos entre ciclos de polling (default: {DEFAULT_INTERVAL_S})",
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
    if args.interval <= 0:
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


def log_snapshot(snapshot: SystemSnapshot) -> None:
    """Callback por defecto para el bloque A3: registra un resumen legible.
    El detector (Fase 2) reemplaza esto por la máquina de estados real."""
    memoria_disponible = (
        f"{snapshot.memory.available_mb} MB" if snapshot.memory else "desconocida"
    )
    logger.info(
        "muestra tomada: %d servicio(s) fallido(s), %d disco(s) leídos, "
        "memoria disponible=%s",
        len(snapshot.failed_services),
        len(snapshot.disks),
        memoria_disponible,
    )


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
        collect_evidence=lambda incident, directorio, ahora: recolector.collect_evidence(
            incident, reports_dir=directorio, now=ahora
        ),
        write_raw_evidence=recolector.write_raw_evidence,
        sanitize_evidence=sanitizador.sanitize_evidence,
        diagnose=lambda sanitizada, prompt: llm.diagnose(
            sanitizada, prompt, llm_config, session
        ),
        save_report=informe.save_and_rotate,
    )


def on_incident(
    incident: Incident,
    prompt: str,
    reports_dir: Path,
    deps: PipelineDeps,
    now: datetime,
) -> None:
    """Puente entre el detector y el pipeline. Nunca deja escapar una excepción:
    un incidente que falla al procesarse no debe detener la vigilancia."""
    try:
        handle_incident(incident, prompt, reports_dir, now, deps)
    except Exception:  # noqa: BLE001 -- frontera del bucle: se registra y se sigue
        logger.exception("fallo procesando el incidente %s", incident.incident_id)


def build_app(args: argparse.Namespace) -> AppContext:
    return AppContext(
        interval_s=args.interval,
        fifo_path=Path(args.fifo_path),
        once=args.once,
        take_snapshot=monitor.take_snapshot,
        on_snapshot=log_snapshot,
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
        eventos = selector.select(timeout=interval_s)
        if not eventos:
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
        context.on_snapshot(context.take_snapshot())
        return

    fifo_fd = None
    if ensure_fifo(context.fifo_path):
        fifo_fd = open_fifo_nonblocking(context.fifo_path)

    detener = threading.Event()

    def manejar_sigterm(signum: int, frame: object) -> None:
        logger.info("SIGTERM recibido, cerrando de forma ordenada")
        detener.set()

    signal.signal(signal.SIGTERM, manejar_sigterm)

    try:
        while not detener.is_set():
            motivo = wait_for_next_cycle(fifo_fd, context.interval_s)
            if detener.is_set():
                break
            logger.debug("ciclo disparado por: %s", motivo)
            context.on_snapshot(context.take_snapshot())
    finally:
        if fifo_fd is not None:
            os.close(fifo_fd)


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
