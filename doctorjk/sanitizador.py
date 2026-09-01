# Sanitizador: enmascara datos sensibles antes de que la evidencia salga del
# servidor (tarea #184, plan-mvp.md Gate C3).
#
# Es la última frontera antes del cliente LLM (Gate D): recibe el texto ya
# ensamblado por el recolector y devuelve una copia enmascarada. Nunca toca
# la entrada -- opera sobre una copia y devuelve una nueva cadena; quien lo
# llama decide qué hacer con la evidencia cruda (que ya quedó guardada sin
# tocar por write_raw_evidence(), Gate C2).
#
# Basado en expresiones regulares (módulo `re` de la librería estándar, sin
# dependencias nuevas). Por diseño, esto NO es exhaustivo: un dato sensible
# con formato inesperado puede escaparse. Las limitaciones conocidas están
# documentadas en docs/sanitizador_limitaciones.md (tarea #185).
from __future__ import annotations

import re

from doctorjk.modelos import Evidence, SanitizedEvidence

# --------------------------------------------------------------------- IPs

_IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")

# Cobertura deliberadamente parcial: no distingue una IPv6 real de una
# dirección MAC (mismo formato de grupos hexadecimales separados por ":").
# Ver docs/sanitizador_limitaciones.md.
_IPV6_RE = re.compile(r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b")


def _looks_like_date_or_time(candidate: str) -> bool:
    """Filtro para el falso positivo más común del patrón IPv6: un timestamp
    de log (p. ej. "2026:12:00:00" dentro de "[25/Aug/2026:12:00:00]" en un
    access log de nginx) calza con la forma de una IPv6 de pocos grupos.

    Heurística, no regla exacta: una IPv6 real casi siempre trae al menos
    una letra hexadecimal (a-f); un timestamp, nunca. Una IPv6 legítima
    escrita enteramente en dígitos decimales con 4 grupos o menos quedaría
    sin redactar -- posible pero muy inusual en la práctica. Documentado en
    docs/sanitizador_limitaciones.md.
    """
    parts = candidate.split(":")
    return len(parts) <= 4 and all(p.isdigit() for p in parts)


def _redact_ips(text: str) -> str:
    """Reemplazo consistente: la misma IP siempre produce el mismo
    placeholder dentro de esta misma llamada (un mismo informe). El contador
    se comparte entre IPv4 e IPv6 para tener una sola numeración por informe.
    """
    placeholders: dict[str, str] = {}

    def _placeholder_for(ip: str) -> str:
        if ip not in placeholders:
            placeholders[ip] = f"[IP_{len(placeholders) + 1}]"
        return placeholders[ip]

    def _replace_ipv6(match: re.Match[str]) -> str:
        candidate = match.group(0)
        if _looks_like_date_or_time(candidate):
            return candidate
        return _placeholder_for(candidate)

    text = _IPV6_RE.sub(_replace_ipv6, text)
    text = _IPV4_RE.sub(lambda m: _placeholder_for(m.group(0)), text)
    return text


# --------------------------------------------------------- credenciales por variable

# Coincide con "NOMBRE = valor" o "export NOMBRE = valor", en cualquier parte
# de la línea (no solo al inicio): cubre tanto un .env de una sola variable
# por línea como una variable embebida a mitad de una línea de log.
_ASSIGNMENT_RE = re.compile(
    r'(?<![\w])((?:export\s+)?)([A-Za-z][A-Za-z0-9_]*)(\s*=\s*)("[^"]*"|\'[^\']*\'|\S+)'
)
_CREDENTIAL_KEYWORDS = frozenset({"PASSWORD", "SECRET", "KEY", "TOKEN"})


def _is_credential_variable(name: str) -> bool:
    """Un componente del nombre (separado por "_") debe COINCIDIR con una de
    las palabras clave, no solo contenerla -- así "MONKEY_ISLAND" no se
    confunde con una variable que contiene "KEY" (sobre-redacción)."""
    return any(part in _CREDENTIAL_KEYWORDS for part in name.upper().split("_"))


def _redact_credential_assignments(text: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        prefix, name, equals, _value = match.groups()
        if not _is_credential_variable(name):
            return match.group(0)
        return f"{prefix}{name}{equals}[REDACTADO]"

    return _ASSIGNMENT_RE.sub(_replace, text)


# ------------------------------------------------- credenciales dentro de URIs

# "esquema://usuario:contrasena@host". Es la forma mas comun en que una
# contrasena real llega al log: cadenas de conexion de PostgreSQL, Redis, AMQP o
# HTTP con auth embebida. No la cubria ningun patron: _redact_ips enmascaraba el
# host y dejaba la credencial intacta.
#
# Se conserva el esquema y el usuario porque son diagnosticos (que servicio y
# que cuenta fallaron); solo se enmascara la contrasena. Exige "@" despues, asi
# que "http://host:8080/ruta" no coincide y no hay sobre-redaccion de puertos.
_URI_CREDENTIAL_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://)([^/\s:@]+):([^@\s/]+)@")


def _redact_uri_credentials(text: str) -> str:
    return _URI_CREDENTIAL_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}:[REDACTADO]@", text)


# --------------------------------------------------------------- tokens Bearer/JWT

_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9\-_.+/=]+")
# Basic transporta "usuario:contrasena" en base64: tan sensible como Bearer,
# y hasta ahora pasaba sin tocar.
_BASIC_RE = re.compile(r"(?i)\bBasic\s+[A-Za-z0-9+/=]{8,}")
# Tres segmentos base64url separados por ".", el formato de un JWT sin el
# prefijo "Bearer " (p. ej. en una cookie o un cuerpo de log).
_JWT_RE = re.compile(r"\b[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")


def _redact_tokens(text: str) -> str:
    text = _BASIC_RE.sub("Basic [REDACTADO]", text)
    text = _BEARER_RE.sub("Bearer [TOKEN_REDACTADO]", text)
    text = _JWT_RE.sub("[TOKEN_REDACTADO]", text)
    return text


# ------------------------------------------------------------------ claves SSH

_SSH_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:OPENSSH|RSA|DSA|EC|PGP) PRIVATE KEY-----.*?"
    r"-----END (?:OPENSSH|RSA|DSA|EC|PGP) PRIVATE KEY-----",
    re.DOTALL,
)
_SSH_PUBLIC_KEY_RE = re.compile(r"\b(ssh-(?:rsa|ed25519|dss)|ecdsa-sha2-\S+)\s+[A-Za-z0-9+/=]+")


def _redact_ssh_keys(text: str) -> str:
    text = _SSH_PRIVATE_KEY_RE.sub("[REDACTADO]", text)
    text = _SSH_PUBLIC_KEY_RE.sub(lambda m: f"{m.group(1)} [REDACTADO]", text)
    return text


# --------------------------------------------------------------- rutas de home

_HOME_PATH_RE = re.compile(r"/home/([^/\s]+)")


def _redact_home_paths(text: str) -> str:
    return _HOME_PATH_RE.sub("/home/[USUARIO]", text)


# --------------------------------------------------------------------- fachada


def sanitize(text: str) -> str:
    """Devuelve una copia de `text` con datos sensibles enmascarados.

    Orden deliberado: claves SSH y tokens primero (bloques largos y con
    formato reconocible), después variables de credenciales y rutas de home
    (más acotadas), y las IPs al final. Ningún paso depende de que otro haya
    corrido antes; el orden solo evita que una sustitución corte a la mitad
    algo que otro patrón todavía no procesó.
    """
    result = _redact_ssh_keys(text)
    result = _redact_tokens(result)
    result = _redact_uri_credentials(result)
    result = _redact_credential_assignments(result)
    result = _redact_home_paths(result)
    result = _redact_ips(result)
    return result


def sanitize_evidence(evidence: Evidence) -> SanitizedEvidence:
    """Convierte `Evidence` cruda en `SanitizedEvidence`, lista para el LLM.

    Es el único punto que produce el tipo que acepta `llm.py`. Trabaja sobre
    una copia del texto: la evidencia cruda queda intacta en disco y en
    memoria, porque es la que sirve para auditar después qué se vio de verdad
    (plan-mvp.md bloque C3, paso 3).
    """
    return SanitizedEvidence(
        incident_id=evidence.incident.incident_id,
        generated_at=evidence.generated_at,
        text=sanitize(evidence.raw_text),
        partial_errors=evidence.partial_errors,
    )
