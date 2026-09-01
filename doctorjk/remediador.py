# Remediador: orquesta el Modo 2 (tareas #199-202, plan-finalizacion-mvp.md
# Gate 4.3). Recibe un incidente ya confirmado por el detector, pide al
# clasificador qué script le corresponde, lo ejecuta con las salvaguardas
# mínimas de Modo 2 y devuelve una bitácora de auditoría completa.
#
# Frontera dura (CONTEXTO-IA.md §3): este módulo no decide si un incidente
# existe -- eso ya lo hizo detector.py -- ni redacta el diagnóstico -- eso es
# llm.py. Solo ejecuta la corrección determinista y audita lo que pasó.
from __future__ import annotations

import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from doctorjk.clasificador import classify
from doctorjk.config import AppConfig, RemediationMode
from doctorjk.modelos import Incident, RemediationOutcome, RemediationResult, SignalType
from doctorjk.sanitizador import sanitize

logger = logging.getLogger(__name__)

# Un script de corrección real (reiniciar un servicio, limpiar /tmp) termina
# en segundos; 120s es margen generoso sin dejar un incidente colgado si el
# script se queda esperando algo que nunca va a pasar.
DEFAULT_SCRIPT_TIMEOUT_S = 120.0


def _target_argument(incident: Incident) -> str:
    """Extrae el identificador concreto que el script necesita como argv[1]
    a partir de `Signal.key` (acoplado a cómo lo arma monitor.py: "service:x",
    "disk:/mnt", "port:N:occupied"). Documentado acá porque es la única
    lectura que este módulo hace del formato interno de otro módulo -- si
    monitor.py cambia ese formato, este es el único lugar que hay que tocar.
    """
    parts = incident.resource_key.split(":")
    if incident.signal_type in (SignalType.SERVICE_FAILED, SignalType.DISK_FULL):
        return parts[1] if len(parts) > 1 else incident.resource_key
    if incident.signal_type is SignalType.PORT_OCCUPIED:
        return parts[1] if len(parts) > 1 else incident.resource_key
    return incident.resource_key


def _build_script_env(incident: Incident, config: AppConfig) -> dict[str, str]:
    """Variables de entorno que ven los scripts de scripts-fix/: listas de
    permitidos y umbrales, nunca datos crudos del incidente más allá de lo
    que el propio script necesita para actuar dentro de su alcance
    predefinido (plan-finalizacion-mvp.md §4.2, "alcance: solo toca rutas y
    servicios predefinidos")."""
    return {
        "DOCTORJK_DRY_RUN": "1" if config.dry_run else "0",
        "DOCTORJK_DISK_THRESHOLD_PCT": str(config.disk_pct_threshold),
        "DOCTORJK_MEMORY_THRESHOLD_MB": str(config.memory_available_mb_threshold),
        "DOCTORJK_APPROVED_MEMORY_UNIT": config.approved_memory_unit,
        "DOCTORJK_MONITORED_SERVICES": ",".join(config.monitored_services),
        "DOCTORJK_PORT_OWNERS": ",".join(
            f"{port.port}={port.service}" for port in config.monitored_ports
        ),
    }


def _skip(incident: Incident, outcome: RemediationOutcome, now: datetime) -> RemediationResult:
    return RemediationResult(
        incident_id=incident.incident_id,
        signal_type=incident.signal_type,
        script=None,
        argv=(),
        started_at=now,
        finished_at=now,
        exit_code=None,
        stdout="",
        stderr="",
        outcome=outcome,
    )


def remediate(
    incident: Incident,
    config: AppConfig,
    scripts_dir: Path,
    timeout_s: float = DEFAULT_SCRIPT_TIMEOUT_S,
    command_prefix: tuple[str, ...] = (),
) -> RemediationResult:
    """Ejecuta la corrección determinista de `incident` si corresponde.

    `command_prefix` antepone argumentos al script (en producción,
    `("sudo", "-n")`, ver build_incident_pipeline() en main.py): el propio
    `doctorjk` corre sin privilegios (CONTEXTO-IA.md §8.5), así que necesita
    escalar para reiniciar servicios o limpiar espacio. `sudo -n` nunca pide
    contraseña -- si el sudoers no está bien configurado, falla rápido en vez
    de colgarse esperando una entrada que nunca llega. Vacío por default para
    que las pruebas corran los scripts directo, sin depender de sudoers real.

    Nunca lanza: un script ausente, sin permiso de ejecución o que se cuelga
    se registra como FAILED, igual que uno que corrió pero no verificó el
    resultado -- para el administrador, "no pude corregirlo" es la misma
    señal de "hay que mirarlo a mano" en los dos casos.
    """
    started_at = datetime.now(timezone.utc)

    if config.remediation_mode is not RemediationMode.SCRIPTS or not config.auto_fix:
        return _skip(incident, RemediationOutcome.NOT_ENABLED, started_at)

    script_name = classify(incident.signal_type)
    if script_name is None:
        logger.info(
            "sin script de corrección para %s, queda solo diagnosticado: %s",
            incident.signal_type.value,
            incident.incident_id,
        )
        return _skip(incident, RemediationOutcome.NOT_MAPPED, started_at)

    argv = command_prefix + (str(scripts_dir / script_name), _target_argument(incident))
    env = _build_script_env(incident, config)

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
            check=False,
        )
        exit_code: int | None = completed.returncode
        stdout, stderr = completed.stdout, completed.stderr
    except FileNotFoundError as error:
        exit_code, stdout, stderr = None, "", f"script no encontrado: {error}"
    except PermissionError as error:
        exit_code, stdout, stderr = None, "", f"sin permiso de ejecución: {error}"
    except subprocess.TimeoutExpired as error:
        exit_code = None
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = f"tiempo agotado tras {timeout_s}s"

    finished_at = datetime.now(timezone.utc)
    outcome = RemediationOutcome.RESOLVED if exit_code == 0 else RemediationOutcome.FAILED

    result = RemediationResult(
        incident_id=incident.incident_id,
        signal_type=incident.signal_type,
        script=script_name,
        argv=argv,
        started_at=started_at,
        finished_at=finished_at,
        exit_code=exit_code,
        # Sanitizado antes de journald y del informe (tarea #201): un script
        # que falla puede volcar una ruta, una IP o una variable de entorno
        # completa a stderr sin que nadie se lo haya pedido.
        stdout=sanitize(stdout),
        stderr=sanitize(stderr),
        outcome=outcome,
    )
    _log_result(result)
    return result


def _log_result(result: RemediationResult) -> None:
    if result.outcome is RemediationOutcome.RESOLVED:
        logger.info(
            "Modo 2: %s resuelto por %s (incidente %s)",
            result.signal_type.value,
            result.script,
            result.incident_id,
        )
    elif result.outcome is RemediationOutcome.FAILED:
        logger.error(
            "Modo 2: corrección fallida — escalar. tipo=%s script=%s incidente=%s "
            "código=%s stderr=%s",
            result.signal_type.value,
            result.script,
            result.incident_id,
            result.exit_code,
            result.stderr,
        )
