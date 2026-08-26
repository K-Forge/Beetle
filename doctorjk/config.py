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

import os
import tomllib
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class RemediationMode(str, Enum):
    """Valores permitidos de `modo_remediacion` (plan-mvp.md §3.3)."""

    DIAGNOSTICO = "diagnostico"
    SCRIPTS = "scripts"
    AUTOMATICO = "automatico"


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


_Validador = Callable[[object], object]


def _numero_positivo(nombre_clave: str, tipos: tuple[type, ...]) -> _Validador:
    def validar(valor: object) -> object:
        if isinstance(valor, bool) or not isinstance(valor, tipos):
            raise ConfigError(f"'{nombre_clave}' debe ser numérico, se recibió {valor!r}")
        if valor <= 0:
            raise ConfigError(f"'{nombre_clave}' debe ser mayor que 0, se recibió {valor!r}")
        return valor

    return validar


def _porcentaje(nombre_clave: str) -> _Validador:
    def validar(valor: object) -> object:
        if isinstance(valor, bool) or not isinstance(valor, int):
            raise ConfigError(f"'{nombre_clave}' debe ser un entero, se recibió {valor!r}")
        if not (0 < valor <= 100):
            raise ConfigError(f"'{nombre_clave}' debe estar entre 1 y 100, se recibió {valor!r}")
        return valor

    return validar


def _booleano(nombre_clave: str) -> _Validador:
    def validar(valor: object) -> object:
        if not isinstance(valor, bool):
            raise ConfigError(f"'{nombre_clave}' debe ser booleano, se recibió {valor!r}")
        return valor

    return validar


def _directorio_absoluto(nombre_clave: str) -> _Validador:
    def validar(valor: object) -> object:
        if not isinstance(valor, str) or not valor.strip():
            raise ConfigError(
                f"'{nombre_clave}' debe ser una ruta no vacía, se recibió {valor!r}"
            )
        ruta = Path(valor)
        if not ruta.is_absolute():
            raise ConfigError(
                f"'{nombre_clave}' debe ser una ruta absoluta, se recibió {valor!r}"
            )
        return ruta

    return validar


def _modo_remediacion(nombre_clave: str) -> _Validador:
    def validar(valor: object) -> object:
        if not isinstance(valor, str):
            raise ConfigError(f"'{nombre_clave}' debe ser texto, se recibió {valor!r}")
        try:
            return RemediationMode(valor)
        except ValueError:
            opciones = ", ".join(modo.value for modo in RemediationMode)
            raise ConfigError(
                f"'{nombre_clave}' debe ser uno de: {opciones}; se recibió {valor!r}"
            ) from None

    return validar


# Clave del TOML -> (atributo en AppConfig, validador). Cualquier clave del
# archivo que no esté acá se rechaza como desconocida; cualquier clave de acá
# ausente del archivo se rechaza como faltante. Ninguna clave tiene default
# implícito: una instalación nueva copia config.toml.example completo.
def _texto_no_vacio(nombre_clave: str) -> _Validador:
    def validar(valor: object) -> object:
        if not isinstance(valor, str) or not valor.strip():
            raise ConfigError(f"'{nombre_clave}' debe ser un texto no vacío, se recibió {valor!r}")
        return valor.strip()

    return validar


_ESQUEMA: dict[str, tuple[str, _Validador]] = {
    "intervalo_monitor_s": (
        "monitor_interval_s",
        _numero_positivo("intervalo_monitor_s", (int, float)),
    ),
    "ciclos_persistencia": (
        "persistence_cycles",
        _numero_positivo("ciclos_persistencia", (int,)),
    ),
    "enfriamiento_ciclos": (
        "cooldown_cycles",
        _numero_positivo("enfriamiento_ciclos", (int,)),
    ),
    "disco_pct": ("disk_pct_threshold", _porcentaje("disco_pct")),
    "memoria_disponible_mb": (
        "memory_available_mb_threshold",
        _numero_positivo("memoria_disponible_mb", (int,)),
    ),
    "puerto_timeout_s": (
        "port_timeout_s",
        _numero_positivo("puerto_timeout_s", (int, float)),
    ),
    "servicio_ciclos": ("service_cycles", _numero_positivo("servicio_ciclos", (int,))),
    "directorio_informes": ("reports_dir", _directorio_absoluto("directorio_informes")),
    "modo_remediacion": ("remediation_mode", _modo_remediacion("modo_remediacion")),
    "auto_fix": ("auto_fix", _booleano("auto_fix")),
    "dry_run": ("dry_run", _booleano("dry_run")),
    "timeout_comando_s": (
        "command_timeout_s",
        _numero_positivo("timeout_comando_s", (int, float)),
    ),
    "llm_url": ("llm_url", _texto_no_vacio("llm_url")),
    "llm_modelo": ("llm_model", _texto_no_vacio("llm_modelo")),
    "llm_timeout_s": ("llm_timeout_s", _numero_positivo("llm_timeout_s", (int, float))),
    "llm_cache": ("llm_cache", _booleano("llm_cache")),
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
        contenido_crudo = path.read_bytes()
    except OSError as error:
        raise ConfigError(f"no se pudo leer {path}: {error}") from error

    try:
        datos = tomllib.loads(contenido_crudo.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise ConfigError(f"{path} no es TOML válido: {error}") from error

    claves_desconocidas = set(datos) - set(_ESQUEMA)
    if claves_desconocidas:
        raise ConfigError(
            f"clave(s) desconocida(s) en {path}: {', '.join(sorted(claves_desconocidas))}"
        )

    claves_faltantes = set(_ESQUEMA) - set(datos)
    if claves_faltantes:
        raise ConfigError(
            f"falta(n) clave(s) obligatoria(s) en {path}: {', '.join(sorted(claves_faltantes))}"
        )

    valores: dict[str, object] = {}
    for clave_toml, (atributo, validar) in _ESQUEMA.items():
        valores[atributo] = validar(datos[clave_toml])

    # auto_fix ejecuta correcciones de verdad; dry_run las simula sin tocar el
    # servidor. Que ambas sean true a la vez es la misma incompatibilidad que
    # main.py ya rechaza entre --auto-fix y --dry-run (tarea #210).
    valores["llm_api_key"] = os.environ.get(LLM_API_KEY_ENV, "")

    if valores["auto_fix"] and valores["dry_run"]:
        raise ConfigError(
            f"{path}: 'auto_fix' y 'dry_run' no pueden ser true a la vez — uno ejecuta "
            "correcciones, el otro las simula sin tocar el servidor"
        )

    return AppConfig(
        monitor_interval_s=valores["monitor_interval_s"],
        persistence_cycles=valores["persistence_cycles"],
        cooldown_cycles=valores["cooldown_cycles"],
        disk_pct_threshold=valores["disk_pct_threshold"],
        memory_available_mb_threshold=valores["memory_available_mb_threshold"],
        port_timeout_s=valores["port_timeout_s"],
        service_cycles=valores["service_cycles"],
        reports_dir=valores["reports_dir"],
        remediation_mode=valores["remediation_mode"],
        auto_fix=valores["auto_fix"],
        dry_run=valores["dry_run"],
        command_timeout_s=valores["command_timeout_s"],
        llm_url=valores["llm_url"],
        llm_model=valores["llm_model"],
        llm_timeout_s=valores["llm_timeout_s"],
        llm_cache=valores["llm_cache"],
        llm_api_key=valores["llm_api_key"],
    )
