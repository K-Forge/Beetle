"""Cliente del modelo de diagnóstico, en formato OpenAI-compatible.

Frontera de privacidad: esta es la única parte del agente que habla con un
servicio externo, y acepta **únicamente** `SanitizedEvidence`. No recibe
`Evidence` cruda ni un `str` suelto, para que no exista forma accidental de
enviar evidencia sin sanitizar (plan-mvp.md bloque D1, paso 1).

El proveedor se cambia por configuración: Cloudflare Workers AI y DeepSeek
hablan el mismo formato, así que solo cambian URL, modelo y credencial.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from doctorjk.modelos import Diagnosis, SanitizedEvidence

log = logging.getLogger("doctorjk.llm")

# Espera entre reintentos, en segundos. Progresión fijada por el plan (D1.3).
BACKOFF_SECONDS: tuple[float, ...] = (1.0, 2.0, 4.0)

DEFAULT_TIMEOUT_S = 30.0

# Códigos que justifican reintentar: el problema es del otro lado y puede pasar.
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class LLMError(Exception):
    """Falla al obtener un diagnóstico del proveedor."""


class LLMConfigError(LLMError):
    """Credencial inválida o configuración incorrecta: reintentar no ayuda."""


class _Response(Protocol):
    """Lo mínimo que el cliente necesita de una respuesta HTTP.

    Se declara como Protocol para poder inyectar dobles en los tests sin
    depender de `requests` ni hacer red (plan-mvp.md §3.4).
    """

    status_code: int

    def json(self) -> Any: ...


class _Session(Protocol):
    def post(self, url: str, *, json: Any, headers: dict[str, str], timeout: float) -> _Response: ...


@dataclass(frozen=True)
class LLMConfig:
    """Configuración del proveedor. La credencial nunca sale del entorno."""

    base_url: str
    model: str
    api_key: str
    timeout_s: float = DEFAULT_TIMEOUT_S
    cache_enabled: bool = False
    cache_dir: Path | None = None


# ------------------------------------------------------------------ caché

def _cache_key(config: LLMConfig, prompt: str, evidence: SanitizedEvidence) -> str:
    """Hash de modelo + prompt + evidencia sanitizada.

    La credencial NO entra en el hash ni se guarda: el archivo de caché queda
    en disco y no debe contener secretos (plan-mvp.md D1, paso 6).
    """
    material = f"{config.model}\x00{prompt}\x00{evidence.text}".encode()
    return hashlib.sha256(material).hexdigest()


def _cache_read(config: LLMConfig, key: str) -> str | None:
    if not config.cache_enabled or config.cache_dir is None:
        return None
    archivo = config.cache_dir / f"{key}.txt"
    try:
        return archivo.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as error:
        # La caché es una comodidad de desarrollo: si falla se sigue sin ella.
        log.warning("no pude leer la caché: %s", error)
        return None


def _cache_write(config: LLMConfig, key: str, contenido: str) -> None:
    if not config.cache_enabled or config.cache_dir is None:
        return
    try:
        config.cache_dir.mkdir(parents=True, exist_ok=True)
        (config.cache_dir / f"{key}.txt").write_text(contenido, encoding="utf-8")
    except OSError as error:
        log.warning("no pude escribir la caché: %s", error)


# ------------------------------------------------------- validación de respuesta

def _extraer_contenido(respuesta: _Response) -> str:
    """Valida la forma de la respuesta y devuelve el texto del mensaje.

    Una respuesta con 200 pero cuerpo roto, vacío o sin `content` es tan
    inservible como un 500, así que se trata como error reintentable.
    """
    try:
        cuerpo = respuesta.json()
    except (ValueError, json.JSONDecodeError) as error:
        raise LLMError(f"respuesta no es JSON válido: {error}") from error

    if not isinstance(cuerpo, dict):
        raise LLMError("respuesta JSON no es un objeto")

    opciones = cuerpo.get("choices")
    if not isinstance(opciones, list) or not opciones:
        raise LLMError("respuesta sin 'choices'")

    mensaje = opciones[0].get("message") if isinstance(opciones[0], dict) else None
    if not isinstance(mensaje, dict):
        raise LLMError("respuesta sin 'message'")

    contenido = mensaje.get("content")
    if not isinstance(contenido, str) or not contenido.strip():
        raise LLMError("respuesta con contenido vacío")

    return contenido.strip()


# ------------------------------------------------------------------ fallback

def build_fallback(evidence: SanitizedEvidence, motivo: str) -> Diagnosis:
    """Informe mínimo con los hechos disponibles cuando el proveedor no responde.

    No inventa causa raíz: dice qué se sabe y qué no. Es preferible a no
    entregar nada, porque la evidencia recolectada sigue siendo útil para
    quien opera el servidor (plan-mvp.md D1, paso 7).
    """
    lineas = [
        "# Diagnóstico no disponible",
        "",
        f"No se pudo obtener un diagnóstico del modelo: {motivo}.",
        "",
        "Este informe se generó localmente y **no contiene análisis de causa raíz**.",
        "La evidencia recolectada se incluye abajo para revisión manual.",
        "",
        f"- Incidente: `{evidence.incident_id}`",
        f"- Evidencia recolectada: {evidence.generated_at.isoformat()}",
    ]
    if evidence.partial_errors:
        lineas.append("- Secciones incompletas: " + ", ".join(evidence.partial_errors))
    lineas += ["", "## Evidencia sanitizada", "", "```", evidence.text, "```"]

    return Diagnosis(
        incident_id=evidence.incident_id,
        text="\n".join(lineas),
        model="fallback-local",
        from_fallback=True,
    )


# ------------------------------------------------------------------ fachada

def diagnose(
    evidence: SanitizedEvidence,
    prompt: str,
    config: LLMConfig,
    session: _Session,
    sleep: Callable[[float], None] = time.sleep,
) -> Diagnosis:
    """Pide un diagnóstico al proveedor; degrada a fallback si no se logra.

    Nunca propaga la falla hacia arriba: el agente debe entregar un informe
    aunque el proveedor esté caído. La distinción queda en `from_fallback`.
    """
    clave = _cache_key(config, prompt, evidence)
    cacheado = _cache_read(config, clave)
    if cacheado is not None:
        log.info("usando respuesta cacheada (%s)", clave[:12])
        return Diagnosis(evidence.incident_id, cacheado, config.model, from_fallback=False)

    payload = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": evidence.text},
        ],
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }

    ultimo_motivo = "sin intentos"
    # Un intento inicial más un reintento por cada espera del backoff.
    for intento in range(len(BACKOFF_SECONDS) + 1):
        try:
            respuesta = session.post(
                config.base_url, json=payload, headers=headers, timeout=config.timeout_s
            )
        except Exception as error:  # noqa: BLE001 -- el timeout concreto lo define la sesión inyectada
            # Se captura amplio a propósito: el tipo de excepción depende del
            # cliente HTTP inyectado, y para el agente cualquier fallo de red
            # es lo mismo (reintentable). El motivo queda registrado.
            ultimo_motivo = f"error de red: {type(error).__name__}"
            log.warning("intento %s falló: %s", intento + 1, ultimo_motivo)
        else:
            estado = respuesta.status_code
            if estado in (401, 403):
                # Credencial mala: reintentar solo gasta cuota y tiempo.
                raise LLMConfigError(f"el proveedor rechazó la credencial (HTTP {estado})")
            if 400 <= estado < 500 and estado not in _RETRYABLE_STATUS:
                raise LLMConfigError(f"petición inválida (HTTP {estado})")
            if estado in _RETRYABLE_STATUS:
                ultimo_motivo = f"HTTP {estado}"
                log.warning("intento %s falló: %s", intento + 1, ultimo_motivo)
            else:
                try:
                    contenido = _extraer_contenido(respuesta)
                except LLMError as error:
                    ultimo_motivo = str(error)
                    log.warning("intento %s falló: %s", intento + 1, ultimo_motivo)
                else:
                    _cache_write(config, clave, contenido)
                    return Diagnosis(
                        evidence.incident_id, contenido, config.model, from_fallback=False
                    )

        if intento < len(BACKOFF_SECONDS):
            sleep(BACKOFF_SECONDS[intento])

    log.error("agotados los intentos contra el proveedor: %s", ultimo_motivo)
    return build_fallback(evidence, ultimo_motivo)
