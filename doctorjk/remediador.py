# Remediador: orquesta el Modo 2 (tareas #199-202, plan-finalizacion-mvp.md
# Gate 4.3). Recibe un incidente ya confirmado por el detector, pide al
# clasificador qué script le corresponde, lo ejecuta con las salvaguardas
# mínimas de Modo 2 y devuelve una bitácora de auditoría completa.
#
# Frontera dura (CONTEXTO-IA.md §3): este módulo no decide si un incidente
# existe -- eso ya lo hizo detector.py -- ni redacta el diagnóstico -- eso es
# llm.py. Solo ejecuta la corrección determinista y audita lo que pasó.
#
# Frontera de privilegios (hallazgos de auditoría #1 y #1-bis, 2026-09-01):
# este módulo corre sin privilegios y NUNCA pasa política (listas
# vigiladas, umbrales, dry-run) al script -- ni por variables de entorno ni
# por argv. En producción el script corre vía "sudo -n" y sudo con
# env_reset (default de seguridad) elimina cualquier DOCTORJK_* antes de
# que el script las vea; agregar SETENV/env_keep en sudoers para que
# sobrevivan le daría al proceso sin privilegios la posibilidad de fabricar
# la allowlist que ve el script que corre como root. Pasar la ruta de
# config.toml por argv tampoco es seguro: sudoers autoriza la ruta exacta
# del script pero no restringe sus argumentos, así que sería igual de
# manipulable. `argv` acá solo lleva el recurso objetivo (unidad, punto de
# montaje, puerto); cada script relee su propia política de la ruta fija
# que define comun.sh, ya con privilegios, usando el mismo parser validado
# (doctorjk.config.load_config).
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


def _target_argument(incident: Incident) -> str:
    """Extrae el identificador concreto que el script necesita como argv[1]
    a partir de `Signal.key` (acoplado a cómo lo arma monitor.py: "service:x",
    "disk:/mnt", "port:N:occupied"). Documentado acá porque es la única
    lectura que este módulo hace del formato interno de otro módulo -- si
    monitor.py cambia ese formato, este es el único lugar que hay que tocar.

    memory_low no tiene recurso específico -- la unidad la fija
    config.toml (unidad_memoria_aprobada), no el incidente -- así que se
    pasa el resource_key tal cual ("memory"); fix_memoria.sh lo ignora.
    """
    parts = incident.resource_key.split(":")
    if incident.signal_type in (SignalType.SERVICE_FAILED, SignalType.DISK_FULL):
        return parts[1] if len(parts) > 1 else incident.resource_key
    if incident.signal_type is SignalType.PORT_OCCUPIED:
        return parts[1] if len(parts) > 1 else incident.resource_key
    return incident.resource_key


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
    timeout_s: float | None = None,
    command_prefix: tuple[str, ...] = (),
) -> RemediationResult:
    """Ejecuta la corrección determinista de `incident` si corresponde.

    No se le pasa al script ni la ruta de config.toml ni ningún dato de
    política: cada script la relee él mismo de la ruta fija que define
    comun.sh (ver nota de frontera de privilegios arriba) -- ni argv ni el
    entorno son un canal confiable para eso desde un proceso sin privilegios
    (hallazgo de auditoría #1 y su corrección #1-bis, 2026-09-01). `argv`
    solo lleva el recurso objetivo. `timeout_s` por default usa
    `config.command_timeout_s` (mismo contrato que el resto de los comandos
    externos del agente, hallazgo de auditoría #9); se puede pisar para
    pruebas o para un timeout específico de remediación.

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
    effective_timeout_s = timeout_s if timeout_s is not None else config.command_timeout_s

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

    argv = command_prefix + (
        str(scripts_dir / script_name),
        _target_argument(incident),
    )

    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=effective_timeout_s,
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
        stderr = f"tiempo agotado tras {effective_timeout_s}s"

    finished_at = datetime.now(timezone.utc)

    # DRY_RUN solo aplica cuando el script efectivamente corrió y salió 0
    # (hallazgo #5, corregido tras revisión post-commit 2026-09-01): un
    # script ausente, colgado o que sale con código distinto de 0 sigue
    # siendo FAILED sin importar config.dry_run -- dry_run no puede
    # esconder un fallo real detrás de una etiqueta que suena a "todo bien,
    # solo faltó ejecutar". remediador.py no confía en que el script se
    # auto-reporte como resuelto: lo decide por su propia config, la misma
    # fuente que el script releyó.
    if exit_code == 0 and config.dry_run:
        outcome = RemediationOutcome.DRY_RUN
    elif exit_code == 0:
        outcome = RemediationOutcome.RESOLVED
    else:
        outcome = RemediationOutcome.FAILED

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
    # Tarea #201: timestamp de inicio y fin, comando ejecutado, código de
    # salida, stdout y stderr completos (ya sanitizados) -- todo a journald,
    # no solo un resumen de una línea (hallazgo de auditoría #2).
    nivel = logging.ERROR if result.outcome is RemediationOutcome.FAILED else logging.INFO
    logger.log(
        nivel,
        "Modo 2: incidente=%s tipo=%s script=%s argv=%s inicio=%s fin=%s "
        "código=%s resultado=%s\nstdout:\n%s\nstderr:\n%s",
        result.incident_id,
        result.signal_type.value,
        result.script,
        result.argv,
        result.started_at.isoformat(),
        result.finished_at.isoformat(),
        result.exit_code,
        result.outcome.value,
        result.stdout,
        result.stderr,
    )
