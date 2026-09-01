"""Escritura y rotación de informes en disco (tareas #195 y #198).

Un incidente produce dos archivos que van siempre juntos:

    20260826_041500_service_failed.md              <- el informe legible
    20260826_041500_service_failed_evidencia.txt   <- la evidencia cruda

El informe se puede leer sin acceso al servidor; la evidencia es la copia de
auditoría que permite verificar de dónde salió cada afirmación. La rotación
los trata como una unidad: nunca se borra uno dejando el otro huérfano.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from doctorjk.modelos import Diagnosis, Incident

log = logging.getLogger("doctorjk.informe")

# Cuántos pares informe+evidencia se conservan (sección 5.4 del documento).
DEFAULT_KEEP = 30

EVIDENCE_SUFFIX = "_evidencia.txt"

# El nombre se construye a partir de datos internos, no de entrada del usuario,
# pero se valida igual: si algún día un tipo de señal llegara de configuración,
# un "../" en el nombre escribiría fuera del directorio de informes.
_SAFE_STEM_PATTERN = re.compile(r"^[0-9]{8}_[0-9]{6}_[a-z_]+(_[0-9]+)?$")


@dataclass(frozen=True)
class ReportPaths:
    """Par informe + evidencia. Se devuelven juntos porque viven y mueren juntos."""

    report: Path
    evidence: Path | None


def _incident_stem(incident: Incident) -> str:
    if incident.confirmed_at is None:
        raise ValueError("no se puede nombrar un informe de un incidente sin confirmar")
    stamp = incident.confirmed_at.strftime("%Y%m%d_%H%M%S")
    stem = f"{stamp}_{incident.signal_type.value}"
    if not _SAFE_STEM_PATTERN.match(stem):
        raise ValueError(f"nombre de informe inseguro: {stem!r}")
    return stem


def _resolve_collision_free_path(reports_dir: Path, stem: str) -> Path:
    """Dos incidentes del mismo tipo en el mismo segundo no deben pisarse."""
    destination = reports_dir / f"{stem}.md"
    suffix = 2
    while destination.exists():
        destination = reports_dir / f"{stem}_{suffix}.md"
        suffix += 1
    return destination


def _write_atomic(destination: Path, content: str, mode: int) -> None:
    """Escribe a un temporal en el mismo directorio y renombra.

    Un informe a medio escribir es peor que ninguno: quien lo lea creería
    tener el diagnóstico completo. `os.replace` es atómico dentro del mismo
    sistema de archivos, así que el archivo final aparece entero o no aparece.
    """
    temp_file = destination.parent / (destination.name + ".tmp")
    descriptor = os.open(temp_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content)
        os.replace(temp_file, destination)
    except OSError:
        temp_file.unlink(missing_ok=True)
        raise


def render_report(diagnosis: Diagnosis, incident: Incident, generated_at: datetime) -> str:
    """Arma el Markdown final: encabezado trazable + el texto del modelo."""
    lines = [
        f"# Informe de incidente — {incident.signal_type.value}",
        "",
        f"- **Incidente:** `{incident.incident_id}`",
        f"- **Recurso:** `{incident.resource_key}`",
        f"- **Detectado:** {incident.started_at.isoformat()}",
        f"- **Confirmado:** {incident.confirmed_at.isoformat() if incident.confirmed_at else 'n/d'}",
        f"- **Informe generado:** {generated_at.isoformat()}",
        f"- **Diagnóstico por:** {diagnosis.model}",
    ]
    if diagnosis.from_fallback:
        # Que quede visible en el propio informe: quien lo lea debe saber que
        # ningún modelo analizó esto, para no atribuirle una confianza que no tiene.
        lines.append("- **Aviso:** generado sin modelo, por fallback local")
    lines += ["", "---", "", diagnosis.text, ""]
    return "\n".join(lines)


def write_report(
    diagnosis: Diagnosis,
    incident: Incident,
    reports_dir: Path,
    generated_at: datetime,
) -> Path:
    """Escribe el informe. Modo 644: es para leerse, ya está sanitizado."""
    reports_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = _resolve_collision_free_path(reports_dir, _incident_stem(incident))
    _write_atomic(destination, render_report(diagnosis, incident, generated_at), 0o644)
    return destination


def _existing_pairs(reports_dir: Path) -> list[ReportPaths]:
    """Lista los pares informe+evidencia, del más viejo al más nuevo.

    El orden sale del nombre, no de la fecha del archivo: el nombre lleva el
    timestamp del incidente y no cambia si alguien copia el directorio.
    """
    pairs: list[ReportPaths] = []
    for report in sorted(reports_dir.glob("*.md")):
        evidence = reports_dir / f"{report.stem}{EVIDENCE_SUFFIX}"
        pairs.append(ReportPaths(report, evidence if evidence.exists() else None))
    return pairs


def rotate_reports(reports_dir: Path, keep: int = DEFAULT_KEEP) -> list[ReportPaths]:
    """Conserva los `keep` pares más recientes y borra el resto.

    Borra el informe y su evidencia como unidad. Dejar una evidencia sin su
    informe deja datos crudos en disco sin nada que explique por qué están
    ahí; dejar un informe sin evidencia lo vuelve inauditable.
    """
    if keep < 0:
        raise ValueError("keep no puede ser negativo")

    pairs = _existing_pairs(reports_dir)
    surplus = pairs[: max(0, len(pairs) - keep)]

    removed: list[ReportPaths] = []
    for pair in surplus:
        try:
            pair.report.unlink(missing_ok=True)
            if pair.evidence is not None:
                pair.evidence.unlink(missing_ok=True)
        except OSError as error:
            # Que falle un borrado no debe impedir rotar los demás.
            log.warning("no pude rotar %s: %s", pair.report.name, error)
            continue
        removed.append(pair)

    if removed:
        log.info("rotación: %s informe(s) antiguo(s) eliminado(s)", len(removed))
    return removed


def save_and_rotate(
    diagnosis: Diagnosis,
    incident: Incident,
    reports_dir: Path,
    generated_at: datetime,
    keep: int = DEFAULT_KEEP,
) -> Path | None:
    """Escribe el informe y rota. Devuelve None si no se pudo escribir.

    Un fallo de disco no debe perder el diagnóstico: se registra completo en
    el log antes de propagar el problema hacia arriba como None, para que
    quede al menos en journald (plan-mvp.md D3, paso 4).
    """
    try:
        destination = write_report(diagnosis, incident, reports_dir, generated_at)
    except OSError as error:
        log.error("no pude escribir el informe de %s: %s", incident.incident_id, error)
        log.error("diagnóstico que no se pudo guardar:\n%s", diagnosis.text)
        return None

    rotate_reports(reports_dir, keep)
    return destination
