"""Integración vertical del Modo 1 (bloque D4 del plan).

Prueba el orden real de las etapas y la frontera de privacidad. La red y los
subprocess están simulados: lo que se verifica es el cableado, no las
implementaciones, que ya tienen sus propias pruebas.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import requests

from doctorjk.informe import save_and_rotate
from doctorjk.llm import LLMConfig, diagnose
from doctorjk.modelos import (
    Diagnosis,
    Evidence,
    Incident,
    IncidentState,
    SanitizedEvidence,
    SignalType,
)
from doctorjk.pipeline import PipelineDeps, handle_incident
from doctorjk.sanitizador import sanitize_evidence

AHORA = datetime(2026, 8, 26, 4, 15, 0, tzinfo=timezone.utc)

# Evidencia con datos sensibles reales: una IP y una contraseña dentro de una
# cadena de conexión, que es como llega de verdad desde el journal.
CRUDO = (
    "servicio postgresql@16-main.service falló\n"
    "conexión rechazada desde 10.0.0.85\n"
    "connecting to postgresql://app:cambia_esto@10.0.0.85:5432/cargatest\n"
)


def _incidente() -> Incident:
    return Incident(
        incident_id="inc-vertical",
        signal_type=SignalType.SERVICE_FAILED,
        resource_key="postgresql@16-main.service",
        started_at=AHORA - timedelta(minutes=1),
        confirmed_at=AHORA,
        state=IncidentState.INCIDENT,
    )


def _evidencia(incidente: Incident) -> Evidence:
    return Evidence(
        incident=incidente,
        generated_at=AHORA,
        metadata_text="metadatos",
        logs_text=CRUDO,
        snapshot_text="snapshot",
        changes_text="",
        history_text="",
        raw_text=CRUDO,
        partial_errors=(),
    )


class RespuestaFalsa:
    def __init__(self, status_code: int, cuerpo: object = None):
        self.status_code = status_code
        self._cuerpo = cuerpo

    def json(self) -> object:
        return self._cuerpo


class SesionFalsa:
    """Registra exactamente qué texto se envió al proveedor."""

    def __init__(self, respuesta: object):
        self._respuesta = respuesta
        self.enviado: list[str] = []

    def post(self, url, *, json, headers, timeout):
        self.enviado.append(json["messages"][1]["content"])
        if isinstance(self._respuesta, Exception):
            raise self._respuesta
        return self._respuesta


def _deps_reales(sesion: SesionFalsa, orden: list[str]) -> PipelineDeps:
    """Usa las implementaciones reales de sanitizador, llm e informe;
    solo recolector y red están simulados."""
    config = LLMConfig(base_url="https://proveedor/v1", model="gpt-oss-120b", api_key="k")

    def recolectar(incidente, directorio, ahora):
        orden.append("recolectar")
        return _evidencia(incidente)

    def guardar_cruda(evidencia, directorio):
        orden.append("guardar_cruda")
        destino = Path(directorio) / "evidencia.txt"
        destino.write_text(evidencia.raw_text, encoding="utf-8")
        return destino

    def sanitizar(evidencia):
        orden.append("sanitizar")
        return sanitize_evidence(evidencia)

    def diagnosticar(sanitizada, prompt):
        orden.append("diagnosticar")
        return diagnose(sanitizada, prompt, config, sesion, sleep=lambda _s: None)

    def guardar_informe(diagnostico, incidente, directorio, ahora):
        orden.append("guardar_informe")
        return save_and_rotate(diagnostico, incidente, directorio, ahora)

    return PipelineDeps(recolectar, guardar_cruda, sanitizar, diagnosticar, guardar_informe)


# ------------------------------------------------------------------ camino feliz

def test_incidente_produce_informe_en_disco(tmp_path: Path):
    sesion = SesionFalsa(
        RespuestaFalsa(200, {"choices": [{"message": {"content": "## DIAGNÓSTICO\n\nSe cayó."}}]})
    )
    deps = _deps_reales(sesion, [])

    destino = handle_incident(_incidente(), "prompt", tmp_path, AHORA, deps)

    assert destino is not None and destino.exists()
    assert "Se cayó" in destino.read_text(encoding="utf-8")


def test_el_orden_de_las_etapas_es_el_del_plan(tmp_path: Path):
    sesion = SesionFalsa(
        RespuestaFalsa(200, {"choices": [{"message": {"content": "ok"}}]})
    )
    orden: list[str] = []
    deps = _deps_reales(sesion, orden)

    handle_incident(_incidente(), "prompt", tmp_path, AHORA, deps)

    # La evidencia cruda se guarda ANTES de diagnosticar: si el proveedor falla
    # o el proceso muere, la evidencia del incidente ya está en disco.
    assert orden == [
        "recolectar",
        "guardar_cruda",
        "sanitizar",
        "diagnosticar",
        "guardar_informe",
    ]


# ------------------------------------------------- frontera de privacidad

def test_al_proveedor_solo_llega_texto_sanitizado(tmp_path: Path):
    sesion = SesionFalsa(
        RespuestaFalsa(200, {"choices": [{"message": {"content": "ok"}}]})
    )
    deps = _deps_reales(sesion, [])

    handle_incident(_incidente(), "prompt", tmp_path, AHORA, deps)

    enviado = sesion.enviado[0]
    assert "10.0.0.85" not in enviado, "una IP real salió del servidor"
    assert "cambia_esto" not in enviado, "una contraseña real salió del servidor"
    assert "[IP_1]" in enviado, "la IP debería estar enmascarada, no eliminada"


def test_la_evidencia_cruda_en_disco_conserva_los_datos_reales(tmp_path: Path):
    # La copia local es la de auditoría: sirve justamente para comparar contra
    # lo que sí viajó, así que NO debe estar sanitizada.
    sesion = SesionFalsa(
        RespuestaFalsa(200, {"choices": [{"message": {"content": "ok"}}]})
    )
    deps = _deps_reales(sesion, [])

    handle_incident(_incidente(), "prompt", tmp_path, AHORA, deps)

    cruda = (tmp_path / "evidencia.txt").read_text(encoding="utf-8")
    assert "10.0.0.85" in cruda
    assert "cambia_esto" in cruda


def test_el_tipo_impide_pasar_evidencia_cruda_al_cliente():
    # La frontera es estructural, no una convención: diagnose() acepta
    # SanitizedEvidence, que solo construye el sanitizador.
    incidente = _incidente()
    sanitizada = sanitize_evidence(_evidencia(incidente))

    assert isinstance(sanitizada, SanitizedEvidence)
    assert "cambia_esto" not in sanitizada.text


# ------------------------------------------------------------ proveedor caído

def test_proveedor_caido_igual_escribe_informe_con_fallback(tmp_path: Path):
    # requests.exceptions.Timeout: la jerarquía concreta que lanza el
    # requests.Session real que main.py inyecta en producción (defecto 10).
    sesion = SesionFalsa(requests.exceptions.Timeout("sin respuesta"))
    deps = _deps_reales(sesion, [])

    destino = handle_incident(_incidente(), "prompt", tmp_path, AHORA, deps)

    assert destino is not None and destino.exists()
    contenido = destino.read_text(encoding="utf-8")
    assert "fallback local" in contenido
    assert "no contiene análisis de causa raíz" in contenido


def test_el_fallback_no_filtra_datos_sensibles(tmp_path: Path):
    # El fallback incluye la evidencia en el informe: debe ser la sanitizada.
    sesion = SesionFalsa(RespuestaFalsa(500))
    deps = _deps_reales(sesion, [])

    destino = handle_incident(_incidente(), "prompt", tmp_path, AHORA, deps)

    contenido = destino.read_text(encoding="utf-8")
    assert "cambia_esto" not in contenido
    assert "10.0.0.85" not in contenido


# ------------------------------------------------------------ fallos parciales

def test_si_falla_guardar_la_evidencia_cruda_igual_se_diagnostica(tmp_path: Path):
    sesion = SesionFalsa(
        RespuestaFalsa(200, {"choices": [{"message": {"content": "diagnóstico igual"}}]})
    )
    orden: list[str] = []
    deps = _deps_reales(sesion, orden)

    def guardar_cruda_falla(evidencia, directorio):
        orden.append("guardar_cruda")
        raise OSError("disco lleno")

    deps = PipelineDeps(
        deps.collect_evidence,
        guardar_cruda_falla,
        deps.sanitize_evidence,
        deps.diagnose,
        deps.save_report,
    )

    destino = handle_incident(_incidente(), "prompt", tmp_path, AHORA, deps)

    # Se pierde la copia de auditoría, no el diagnóstico.
    assert destino is not None
    assert "diagnóstico igual" in destino.read_text(encoding="utf-8")


def test_si_falla_la_recoleccion_no_se_llama_al_proveedor(tmp_path: Path):
    sesion = SesionFalsa(RespuestaFalsa(200, {"choices": [{"message": {"content": "x"}}]}))
    deps = _deps_reales(sesion, [])

    def recolectar_falla(incidente, directorio, ahora):
        raise OSError("journalctl no disponible")

    deps = PipelineDeps(
        recolectar_falla,
        deps.write_raw_evidence,
        deps.sanitize_evidence,
        deps.diagnose,
        deps.save_report,
    )

    assert handle_incident(_incidente(), "prompt", tmp_path, AHORA, deps) is None


def test_si_falla_escribir_el_informe_no_se_propaga(tmp_path: Path):
    # Defecto 10: el punto de entrada ya no atrapa Exception a secas, así que
    # el propio pipeline debe garantizar que un fallo de disco al guardar el
    # informe no se escape -- no debe tumbar el bucle del agente.
    sesion = SesionFalsa(RespuestaFalsa(200, {"choices": [{"message": {"content": "x"}}]}))
    deps = _deps_reales(sesion, [])

    def guardar_informe_falla(diagnostico, incidente, directorio, ahora):
        raise OSError("disco lleno")

    deps = PipelineDeps(
        deps.collect_evidence,
        deps.write_raw_evidence,
        deps.sanitize_evidence,
        deps.diagnose,
        guardar_informe_falla,
    )

    assert handle_incident(_incidente(), "prompt", tmp_path, AHORA, deps) is None
