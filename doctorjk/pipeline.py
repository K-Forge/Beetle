"""Corte vertical del Modo 1: de incidente confirmado a informe en disco.

Este módulo solo *ordena* pasos; no implementa ninguno. Recibe cada etapa como
una función inyectada y las encadena por sus contratos (plan-mvp.md D4, paso 1).
Así el orden queda probado sin tocar disco, red ni subprocess.

El orden no es negociable:

    evidencia cruda -> se guarda local -> se sanitiza -> se diagnostica -> informe

La evidencia cruda se escribe ANTES de diagnosticar a propósito: si el modelo
falla o el proceso muere, la evidencia del incidente ya está en disco. Y lo que
viaja al proveedor es `SanitizedEvidence`, un tipo que solo el sanitizador
construye, así que no hay forma de enviar la cruda por descuido.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from doctorjk.modelos import Diagnosis, Evidence, Incident, SanitizedEvidence

log = logging.getLogger("doctorjk.pipeline")


@dataclass(frozen=True)
class PipelineDeps:
    """Cada etapa como función inyectable.

    En producción son las implementaciones reales de recolector, sanitizador,
    llm e informe; en tests son dobles. El pipeline no sabe cuál recibió.
    """

    collect_evidence: Callable[[Incident, Path, datetime], Evidence]
    write_raw_evidence: Callable[[Evidence, Path], Path]
    sanitize_evidence: Callable[[Evidence], SanitizedEvidence]
    diagnose: Callable[[SanitizedEvidence, str], Diagnosis]
    save_report: Callable[[Diagnosis, Incident, Path, datetime], Path | None]


def handle_incident(
    incident: Incident,
    prompt: str,
    reports_dir: Path,
    now: datetime,
    deps: PipelineDeps,
) -> Path | None:
    """Procesa un incidente confirmado y devuelve la ruta del informe.

    Devuelve None si no se pudo escribir el informe. No propaga excepciones de
    etapas intermedias hacia el bucle del agente: un incidente que falla no
    debe tumbar la vigilancia de los demás.
    """
    log.info("procesando incidente %s (%s)", incident.incident_id, incident.resource_key)

    try:
        evidence = deps.collect_evidence(incident, reports_dir, now)
    except OSError as error:
        log.error("no pude recolectar evidencia de %s: %s", incident.incident_id, error)
        return None

    # Primero al disco: si el proveedor falla o el proceso muere después, la
    # evidencia del incidente no se pierde. Que falle esta escritura no impide
    # diagnosticar -- se pierde la copia de auditoría, no el diagnóstico.
    try:
        raw_path = deps.write_raw_evidence(evidence, reports_dir)
        log.info("evidencia cruda guardada en %s", raw_path.name)
    except OSError as error:
        log.error("no pude guardar la evidencia cruda: %s", error)

    # Única frontera hacia afuera. A partir de aquí no se toca `evidence`.
    sanitized = deps.sanitize_evidence(evidence)

    diagnosis = deps.diagnose(sanitized, prompt)
    if diagnosis.from_fallback:
        log.warning(
            "incidente %s diagnosticado sin modelo (fallback local)", incident.incident_id
        )

    try:
        destination = deps.save_report(diagnosis, incident, reports_dir, now)
    except OSError as error:
        log.error("no pude escribir el informe de %s: %s", incident.incident_id, error)
        return None

    if destination is not None:
        log.info("informe escrito en %s", destination.name)
    return destination
