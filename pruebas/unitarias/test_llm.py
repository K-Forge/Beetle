"""Pruebas del cliente LLM (bloque D1 del plan).

Ninguna hace red: la sesión HTTP se inyecta como doble, según §3.4 del plan.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from doctorjk.llm import (
    BACKOFF_SECONDS,
    LLMConfig,
    build_fallback,
    diagnose,
)
from doctorjk.modelos import SanitizedEvidence


# ------------------------------------------------------------------ dobles

class RespuestaFalsa:
    def __init__(self, status_code: int, cuerpo: object = None, rompe_json: bool = False):
        self.status_code = status_code
        self._cuerpo = cuerpo
        self._rompe_json = rompe_json

    def json(self) -> object:
        if self._rompe_json:
            raise ValueError("Expecting value: line 1 column 1")
        return self._cuerpo


class SesionFalsa:
    """Devuelve respuestas en orden; si se acaban, repite la última."""

    def __init__(self, *respuestas: object):
        self._respuestas = list(respuestas)
        self.llamadas: list[dict] = []

    def post(self, url, *, json, headers, timeout):
        self.llamadas.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        elemento = self._respuestas[min(len(self.llamadas) - 1, len(self._respuestas) - 1)]
        if isinstance(elemento, Exception):
            raise elemento
        return elemento


def _respuesta_ok(texto: str = "## Diagnóstico\n\nPostgreSQL se detuvo.") -> RespuestaFalsa:
    return RespuestaFalsa(200, {"choices": [{"message": {"content": texto}}]})


@pytest.fixture
def evidencia() -> SanitizedEvidence:
    return SanitizedEvidence(
        incident_id="inc-1",
        generated_at=datetime(2026, 8, 26, 4, 0, tzinfo=timezone.utc),
        text="servicio postgresql falló; disco en [IP_1]",
        partial_errors=(),
    )


@pytest.fixture
def config() -> LLMConfig:
    return LLMConfig(
        base_url="https://api.cloudflare.com/v1/chat/completions",
        model="gpt-oss-120b",
        api_key="secreto-de-prueba",
    )


def _esperas() -> tuple[list[float], object]:
    registradas: list[float] = []
    return registradas, registradas.append


# ------------------------------------------------------------------ camino feliz

def test_respuesta_valida_devuelve_diagnostico(evidencia, config):
    sesion = SesionFalsa(_respuesta_ok())
    _, dormir = _esperas()

    resultado = diagnose(evidencia, "prompt", config, sesion, sleep=dormir)

    assert "PostgreSQL se detuvo" in resultado.text
    assert resultado.from_fallback is False
    assert resultado.model == "gpt-oss-120b"


def test_solo_se_envia_la_evidencia_sanitizada(evidencia, config):
    sesion = SesionFalsa(_respuesta_ok())
    _, dormir = _esperas()

    diagnose(evidencia, "prompt del sistema", config, sesion, sleep=dormir)

    mensajes = sesion.llamadas[0]["json"]["messages"]
    assert mensajes[1]["content"] == evidencia.text
    assert sesion.llamadas[0]["timeout"] == 30.0


def test_deepseek_solo_cambia_configuracion(evidencia):
    # Mismo formato OpenAI-compatible: cambiar de proveedor no toca el código.
    config = LLMConfig(
        base_url="https://api.deepseek.com/chat/completions",
        model="deepseek-v4-flash",
        api_key="otra-credencial",
    )
    sesion = SesionFalsa(_respuesta_ok("Diagnóstico desde DeepSeek"))
    _, dormir = _esperas()

    resultado = diagnose(evidencia, "prompt", config, sesion, sleep=dormir)

    assert resultado.model == "deepseek-v4-flash"
    assert "deepseek.com" in sesion.llamadas[0]["url"]


# ------------------------------------------------------------------ no reintentables

@pytest.mark.parametrize("estado", [401, 403])
def test_credencial_invalida_no_reintenta_y_cae_al_fallback(evidencia, config, estado):
    # Defecto 11: una credencial mala no debe dejar al agente sin informe --
    # tiene que degradar a fallback como cualquier otra falla permanente.
    sesion = SesionFalsa(RespuestaFalsa(estado))
    esperas, dormir = _esperas()

    resultado = diagnose(evidencia, "prompt", config, sesion, sleep=dormir)

    assert resultado.from_fallback is True
    assert len(sesion.llamadas) == 1, "un 401 no debe consumir reintentos"
    assert esperas == []


def test_peticion_invalida_no_reintenta_y_cae_al_fallback(evidencia, config):
    sesion = SesionFalsa(RespuestaFalsa(400))
    esperas, dormir = _esperas()

    resultado = diagnose(evidencia, "prompt", config, sesion, sleep=dormir)

    assert resultado.from_fallback is True
    assert len(sesion.llamadas) == 1
    assert esperas == []


# ------------------------------------------------------------------ reintentables

@pytest.mark.parametrize("estado", [429, 500, 502, 503])
def test_estados_reintentables_agotan_intentos_y_caen_al_fallback(evidencia, config, estado):
    sesion = SesionFalsa(RespuestaFalsa(estado))
    esperas, dormir = _esperas()

    resultado = diagnose(evidencia, "prompt", config, sesion, sleep=dormir)

    assert resultado.from_fallback is True
    assert len(sesion.llamadas) == len(BACKOFF_SECONDS) + 1


def test_secuencia_de_backoff_es_1_2_4(evidencia, config):
    sesion = SesionFalsa(RespuestaFalsa(500))
    esperas, dormir = _esperas()

    diagnose(evidencia, "prompt", config, sesion, sleep=dormir)

    assert esperas == [1.0, 2.0, 4.0]


def test_timeout_de_red_se_reintenta(evidencia, config):
    # requests.exceptions.Timeout es lo que lanza un requests.Session real
    # (el `_Session` inyectado en producción); diagnose() ahora captura esa
    # jerarquía concreta, no Exception a secas (defecto 10).
    sesion = SesionFalsa(requests.exceptions.Timeout("se agotó el tiempo"))
    _, dormir = _esperas()

    resultado = diagnose(evidencia, "prompt", config, sesion, sleep=dormir)

    assert resultado.from_fallback is True
    assert len(sesion.llamadas) == len(BACKOFF_SECONDS) + 1


def test_error_de_red_no_relacionado_con_requests_no_se_captura(evidencia, config):
    # Si el cliente HTTP inyectado lanza algo fuera de la jerarquía de
    # requests, no es un fallo de red esperado -- debe propagarse, no
    # tratarse en silencio como "reintentable" (defecto 10: nada de
    # `except Exception` genérico).
    sesion = SesionFalsa(ValueError("esto no es un error de requests"))
    _, dormir = _esperas()

    with pytest.raises(ValueError):
        diagnose(evidencia, "prompt", config, sesion, sleep=dormir)


def test_se_recupera_si_un_reintento_tiene_exito(evidencia, config):
    sesion = SesionFalsa(RespuestaFalsa(503), _respuesta_ok("Recuperado"))
    esperas, dormir = _esperas()

    resultado = diagnose(evidencia, "prompt", config, sesion, sleep=dormir)

    assert resultado.from_fallback is False
    assert "Recuperado" in resultado.text
    assert esperas == [1.0], "solo debe esperar una vez antes del reintento exitoso"


# ------------------------------------------------------- respuestas malformadas

def test_json_roto_se_trata_como_error_reintentable(evidencia, config):
    sesion = SesionFalsa(RespuestaFalsa(200, rompe_json=True))
    _, dormir = _esperas()

    resultado = diagnose(evidencia, "prompt", config, sesion, sleep=dormir)

    assert resultado.from_fallback is True


@pytest.mark.parametrize(
    "cuerpo",
    [
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": "   "}}]},
    ],
)
def test_respuesta_200_pero_inservible_cae_al_fallback(evidencia, config, cuerpo):
    # Un 200 con cuerpo vacío o incompleto es tan inútil como un 500.
    sesion = SesionFalsa(RespuestaFalsa(200, cuerpo))
    _, dormir = _esperas()

    assert diagnose(evidencia, "prompt", config, sesion, sleep=dormir).from_fallback is True


# ------------------------------------------------------------------ fallback

def test_el_fallback_no_inventa_causa_raiz(evidencia):
    resultado = build_fallback(evidencia, "HTTP 500")

    assert resultado.from_fallback is True
    assert "no contiene análisis de causa raíz" in resultado.text
    assert evidencia.text in resultado.text, "la evidencia debe quedar para revisión manual"


def test_el_fallback_reporta_secciones_incompletas():
    evidencia = SanitizedEvidence(
        incident_id="inc-2",
        generated_at=datetime(2026, 8, 26, tzinfo=timezone.utc),
        text="evidencia parcial",
        partial_errors=("journal: timeout",),
    )

    assert "journal: timeout" in build_fallback(evidencia, "timeout").text


# ------------------------------------------------------------------ caché

def test_cache_evita_la_segunda_llamada(evidencia, config, tmp_path: Path):
    con_cache = LLMConfig(
        base_url=config.base_url,
        model=config.model,
        api_key=config.api_key,
        cache_enabled=True,
        cache_dir=tmp_path,
    )
    sesion = SesionFalsa(_respuesta_ok("Cacheable"))
    _, dormir = _esperas()

    primero = diagnose(evidencia, "prompt", con_cache, sesion, sleep=dormir)
    segundo = diagnose(evidencia, "prompt", con_cache, sesion, sleep=dormir)

    assert primero.text == segundo.text
    assert len(sesion.llamadas) == 1, "la segunda vez debe salir de la caché"


def test_la_cache_no_guarda_la_credencial(evidencia, config, tmp_path: Path):
    con_cache = LLMConfig(
        base_url=config.base_url,
        model=config.model,
        api_key="CREDENCIAL-SUPER-SECRETA",
        cache_enabled=True,
        cache_dir=tmp_path,
    )
    sesion = SesionFalsa(_respuesta_ok())
    _, dormir = _esperas()

    diagnose(evidencia, "prompt", con_cache, sesion, sleep=dormir)

    for archivo in tmp_path.iterdir():
        assert "CREDENCIAL-SUPER-SECRETA" not in archivo.read_text(encoding="utf-8")
        assert "CREDENCIAL-SUPER-SECRETA" not in archivo.name


def test_sin_opt_in_no_se_usa_cache(evidencia, config, tmp_path: Path):
    # La caché es solo-desarrollo: sin activarla explícitamente no debe existir.
    sesion = SesionFalsa(_respuesta_ok())
    _, dormir = _esperas()

    diagnose(evidencia, "prompt", config, sesion, sleep=dormir)
    diagnose(evidencia, "prompt", config, sesion, sleep=dormir)

    assert len(sesion.llamadas) == 2
    assert list(tmp_path.iterdir()) == []
