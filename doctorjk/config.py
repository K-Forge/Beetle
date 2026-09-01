# Carga y valida config.toml (tarea #175 adelantada por plan-mvp.md bloque B1).
#
# config.toml es interfaz del cliente y sus claves van en español (CONTEXTO-IA.md
# regla cero, punto 2). Este módulo las traduce una sola vez a AppConfig, con
# atributos en inglés, para que el resto del pipeline no dependa del idioma de
# la interfaz de configuración.
#
# Falla rápido: una config con una clave ausente, desconocida, de tipo o rango
# inválido nunca produce un AppConfig a medias — se rechaza acá, antes de que
# el monitor arranque (CONTEXTO-IA.md §8.1, "fail fast").
from __future__ import annotations

import math
import os
import re
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable

from doctorjk.modelos import MonitoredPort


class RemediationMode(str, Enum):
    """Valores permitidos de `modo_remediacion` (plan-mvp.md §3.3)."""

    DIAGNOSTIC = "diagnostico"
    SCRIPTS = "scripts"
    AUTOMATIC = "automatico"


class ConfigError(ValueError):
    """config.toml inválido o incompleto.

    El mensaje siempre nombra la clave en español tal como la ve el cliente
    que edita el archivo, lo que se esperaba y lo que se recibió.
    """


@dataclass(frozen=True)
class AppConfig:
    """Configuración ya validada y tipada.

    Los atributos van en inglés porque cruzan la frontera hacia el resto del
    pipeline; config.toml sigue en español porque es interfaz del cliente.
    """

    monitor_interval_s: float
    persistence_cycles: int
    cooldown_cycles: int
    disk_pct_threshold: int
    memory_available_mb_threshold: int
    port_timeout_s: float
    service_cycles: int
    # Ciclos de persistencia para señales de puerto (port_down y
    # port_occupied), derivados de port_timeout_s -- no viene del TOML, lo
    # calcula load_config() con ceil(port_timeout_s / monitor_interval_s)
    # para que ambos queden expresados en la misma unidad que el resto del
    # detector (plan-finalizacion-mvp.md Gate 1.2).
    port_cycles: int
    monitored_services: tuple[str, ...]
    monitored_ports: tuple[MonitoredPort, ...]
    # Única unidad que fix_memoria.sh (Modo 2, Gate 4) puede reiniciar para
    # liberar memoria. Cadena vacía = ninguna aprobada: el script debe
    # escalar en vez de actuar (plan-finalizacion-mvp.md §4.2 -- "si no hay
    # una unidad aprobada identificable, escalar; no matar procesos
    # arbitrarios ni escribir a drop_caches").
    approved_memory_unit: str
    reports_dir: Path
    remediation_mode: RemediationMode
    auto_fix: bool
    dry_run: bool
    command_timeout_s: float
    llm_url: str
    llm_model: str
    llm_timeout_s: float
    llm_cache: bool
    # La credencial NO viene del TOML: solo del entorno (plan-mvp.md §3.3).
    # Queda vacía si no está definida; llm.py falla con mensaje claro al usarla.
    llm_api_key: str = ""


_Validator = Callable[[object], object]


def _positive_number(key_name: str, types: tuple[type, ...]) -> _Validator:
    def validate(value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, types):
            raise ConfigError(f"'{key_name}' debe ser numérico, se recibió {value!r}")
        if value <= 0:
            raise ConfigError(f"'{key_name}' debe ser mayor que 0, se recibió {value!r}")
        return value

    return validate


def _percentage(key_name: str) -> _Validator:
    def validate(value: object) -> object:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"'{key_name}' debe ser un entero, se recibió {value!r}")
        if not (0 < value <= 100):
            raise ConfigError(f"'{key_name}' debe estar entre 1 y 100, se recibió {value!r}")
        return value

    return validate


def _boolean(key_name: str) -> _Validator:
    def validate(value: object) -> object:
        if not isinstance(value, bool):
            raise ConfigError(f"'{key_name}' debe ser booleano, se recibió {value!r}")
        return value

    return validate


def _absolute_directory(key_name: str) -> _Validator:
    def validate(value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(
                f"'{key_name}' debe ser una ruta no vacía, se recibió {value!r}"
            )
        resolved_path = Path(value)
        if not resolved_path.is_absolute():
            raise ConfigError(
                f"'{key_name}' debe ser una ruta absoluta, se recibió {value!r}"
            )
        return resolved_path

    return validate


def _remediation_mode(key_name: str) -> _Validator:
    def validate(value: object) -> object:
        if not isinstance(value, str):
            raise ConfigError(f"'{key_name}' debe ser texto, se recibió {value!r}")
        try:
            return RemediationMode(value)
        except ValueError:
            options = ", ".join(mode.value for mode in RemediationMode)
            raise ConfigError(
                f"'{key_name}' debe ser uno de: {options}; se recibió {value!r}"
            ) from None

    return validate


# Clave del TOML -> (atributo en AppConfig, validador). Cualquier clave del
# archivo que no esté acá se rechaza como desconocida; cualquier clave de acá
# ausente del archivo se rechaza como faltante. Ninguna clave tiene default
# implícito: una instalación nueva copia config.toml.example completo.
def _non_empty_text(key_name: str) -> _Validator:
    def validate(value: object) -> object:
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"'{key_name}' debe ser un texto no vacío, se recibió {value!r}")
        return value.strip()

    return validate


# Nombre de unidad systemd: sin espacios, '/', '..' ni otros metacaracteres
# (plan-finalizacion-mvp.md Gate 1.2). El conjunto permitido ya excluye '/' y
# '..' por construcción, no hace falta una regla aparte para ellos.
_SYSTEMD_UNIT_PATTERN = re.compile(r"^[A-Za-z0-9@_.\-]+$")


def _is_valid_unit(value: object) -> bool:
    return isinstance(value, str) and bool(value) and _SYSTEMD_UNIT_PATTERN.fullmatch(value) is not None


def _monitored_services_list(key_name: str) -> _Validator:
    def validate(value: object) -> object:
        if not isinstance(value, list) or not value:
            raise ConfigError(
                f"'{key_name}' debe ser una lista no vacía de unidades systemd, "
                f"se recibió {value!r}"
            )
        seen: set[str] = set()
        services: list[str] = []
        for unit in value:
            if not _is_valid_unit(unit):
                raise ConfigError(
                    f"'{key_name}' contiene una unidad inválida: {unit!r} "
                    "(sin espacios, '/', '..' ni metacaracteres)"
                )
            if unit in seen:
                raise ConfigError(f"'{key_name}' tiene la unidad duplicada: {unit!r}")
            seen.add(unit)
            services.append(unit)
        return tuple(services)

    return validate


def _approved_memory_unit(key_name: str) -> _Validator:
    def validate(value: object) -> object:
        if not isinstance(value, str):
            raise ConfigError(f"'{key_name}' debe ser texto, se recibió {value!r}")
        if value == "":
            return value  # explícitamente ninguna: fix_memoria.sh debe escalar
        if not _is_valid_unit(value):
            raise ConfigError(
                f"'{key_name}' debe ser \"\" o una unidad systemd válida, se recibió {value!r}"
            )
        return value

    return validate


def _monitored_ports_list(key_name: str) -> _Validator:
    def validate(value: object) -> object:
        if not isinstance(value, list) or not value:
            raise ConfigError(
                f"'{key_name}' debe ser una lista no vacía de tablas "
                f"{{puerto, servicio}}, se recibió {value!r}"
            )
        seen: set[int] = set()
        ports: list[MonitoredPort] = []
        for entry in value:
            if not isinstance(entry, dict):
                raise ConfigError(
                    f"'{key_name}' debe contener tablas {{puerto, servicio}}, "
                    f"se recibió {entry!r}"
                )
            port = entry.get("puerto")
            service = entry.get("servicio")
            if isinstance(port, bool) or not isinstance(port, int) or not (1 <= port <= 65535):
                raise ConfigError(
                    f"'{key_name}': 'puerto' debe ser un entero entre 1 y 65535, "
                    f"se recibió {port!r}"
                )
            if not _is_valid_unit(service):
                raise ConfigError(
                    f"'{key_name}': 'servicio' inválido para el puerto {port}: {service!r} "
                    "(sin espacios, '/', '..' ni metacaracteres)"
                )
            if port in seen:
                raise ConfigError(f"'{key_name}' tiene el puerto duplicado: {port}")
            seen.add(port)
            ports.append(MonitoredPort(port=port, service=service))
        return tuple(ports)

    return validate


_SCHEMA: dict[str, tuple[str, _Validator]] = {
    "intervalo_monitor_s": (
        "monitor_interval_s",
        _positive_number("intervalo_monitor_s", (int, float)),
    ),
    "ciclos_persistencia": (
        "persistence_cycles",
        _positive_number("ciclos_persistencia", (int,)),
    ),
    "enfriamiento_ciclos": (
        "cooldown_cycles",
        _positive_number("enfriamiento_ciclos", (int,)),
    ),
    "disco_pct": ("disk_pct_threshold", _percentage("disco_pct")),
    "memoria_disponible_mb": (
        "memory_available_mb_threshold",
        _positive_number("memoria_disponible_mb", (int,)),
    ),
    "puerto_timeout_s": (
        "port_timeout_s",
        _positive_number("puerto_timeout_s", (int, float)),
    ),
    "servicio_ciclos": ("service_cycles", _positive_number("servicio_ciclos", (int,))),
    "servicios_vigilados": (
        "monitored_services",
        _monitored_services_list("servicios_vigilados"),
    ),
    "puertos_vigilados": (
        "monitored_ports",
        _monitored_ports_list("puertos_vigilados"),
    ),
    "unidad_memoria_aprobada": (
        "approved_memory_unit",
        _approved_memory_unit("unidad_memoria_aprobada"),
    ),
    "directorio_informes": ("reports_dir", _absolute_directory("directorio_informes")),
    "modo_remediacion": ("remediation_mode", _remediation_mode("modo_remediacion")),
    "auto_fix": ("auto_fix", _boolean("auto_fix")),
    "dry_run": ("dry_run", _boolean("dry_run")),
    "timeout_comando_s": (
        "command_timeout_s",
        _positive_number("timeout_comando_s", (int, float)),
    ),
    "llm_url": ("llm_url", _non_empty_text("llm_url")),
    "llm_modelo": ("llm_model", _non_empty_text("llm_modelo")),
    "llm_timeout_s": ("llm_timeout_s", _positive_number("llm_timeout_s", (int, float))),
    "llm_cache": ("llm_cache", _boolean("llm_cache")),
}

# Variable de entorno que trae la credencial del proveedor. Se lee aparte del
# TOML a propósito: config.toml lo edita el cliente y puede terminar en un
# backup o en un repo; la credencial no debe estar ahí.
LLM_API_KEY_ENV = "DOCTORJK_LLM_API_KEY"


def load_config(path: Path) -> AppConfig:
    """Lee y valida config.toml. Lanza ConfigError con un mensaje accionable
    ante archivo ilegible, TOML mal formado, clave ausente o desconocida, o
    valor de tipo/rango inválido.
    """
    try:
        raw_content = path.read_bytes()
    except OSError as error:
        raise ConfigError(f"no se pudo leer {path}: {error}") from error

    try:
        data = tomllib.loads(raw_content.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ConfigError(f"{path} no es TOML válido: {error}") from error

    unknown_keys = set(data) - set(_SCHEMA)
    if unknown_keys:
        raise ConfigError(
            f"clave(s) desconocida(s) en {path}: {', '.join(sorted(unknown_keys))}"
        )

    missing_keys = set(_SCHEMA) - set(data)
    if missing_keys:
        raise ConfigError(
            f"falta(n) clave(s) obligatoria(s) en {path}: {', '.join(sorted(missing_keys))}"
        )

    values: dict[str, object] = {}
    for toml_key, (attribute, validate) in _SCHEMA.items():
        values[attribute] = validate(data[toml_key])

    # auto_fix ejecuta correcciones de verdad; dry_run las simula sin tocar el
    # servidor. Que ambas sean true a la vez es la misma incompatibilidad que
    # main.py ya rechaza entre --auto-fix y --dry-run (tarea #210).
    values["llm_api_key"] = os.environ.get(LLM_API_KEY_ENV, "")

    if values["auto_fix"] and values["dry_run"]:
        raise ConfigError(
            f"{path}: 'auto_fix' y 'dry_run' no pueden ser true a la vez — uno ejecuta "
            "correcciones, el otro las simula sin tocar el servidor"
        )

    # port_timeout_s es un tiempo, no un número de ciclos; el detector solo
    # entiende ciclos. Redondeando hacia arriba, un puerto nunca se confirma
    # con menos tiempo del que pidió el cliente en config.toml.
    computed_port_cycles = math.ceil(values["port_timeout_s"] / values["monitor_interval_s"])

    return AppConfig(
        monitor_interval_s=values["monitor_interval_s"],
        persistence_cycles=values["persistence_cycles"],
        cooldown_cycles=values["cooldown_cycles"],
        disk_pct_threshold=values["disk_pct_threshold"],
        memory_available_mb_threshold=values["memory_available_mb_threshold"],
        port_timeout_s=values["port_timeout_s"],
        service_cycles=values["service_cycles"],
        port_cycles=max(computed_port_cycles, 1),
        monitored_services=values["monitored_services"],
        monitored_ports=values["monitored_ports"],
        approved_memory_unit=values["approved_memory_unit"],
        reports_dir=values["reports_dir"],
        remediation_mode=values["remediation_mode"],
        auto_fix=values["auto_fix"],
        dry_run=values["dry_run"],
        command_timeout_s=values["command_timeout_s"],
        llm_url=values["llm_url"],
        llm_model=values["llm_model"],
        llm_timeout_s=values["llm_timeout_s"],
        llm_cache=values["llm_cache"],
        llm_api_key=values["llm_api_key"],
    )
