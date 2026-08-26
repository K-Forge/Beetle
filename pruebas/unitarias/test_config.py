# Pruebas de config.py (tarea #175 adelantada, plan-mvp.md bloque B1): una
# config válida produce un AppConfig tipado; cualquier desvío (clave ausente,
# desconocida, tipo o rango inválido, combinación de modo contradictoria)
# falla al cargar, con un mensaje que nombra la clave en español.
from __future__ import annotations

import pytest

from doctorjk.config import AppConfig, ConfigError, RemediationMode, load_config

TOML_VALIDO = """
intervalo_monitor_s = 30
ciclos_persistencia = 2
enfriamiento_ciclos = 2
disco_pct = 90
memoria_disponible_mb = 512
puerto_timeout_s = 60
servicio_ciclos = 2
directorio_informes = "/var/lib/doctorjk/informes"
modo_remediacion = "diagnostico"
auto_fix = false
dry_run = true
timeout_comando_s = 30
llm_url = "https://proveedor.example/v1/chat/completions"
llm_modelo = "gpt-oss-120b"
llm_timeout_s = 30
llm_cache = false
"""


def _escribir(tmp_path, contenido: str):
    ruta = tmp_path / "config.toml"
    ruta.write_text(contenido, encoding="utf-8")
    return ruta


def test_config_valida_produce_appconfig_tipado(tmp_path):
    ruta = _escribir(tmp_path, TOML_VALIDO)
    config = load_config(ruta)
    assert isinstance(config, AppConfig)
    assert config.monitor_interval_s == 30
    assert config.persistence_cycles == 2
    assert config.cooldown_cycles == 2
    assert config.disk_pct_threshold == 90
    assert config.memory_available_mb_threshold == 512
    assert config.port_timeout_s == 60
    assert config.service_cycles == 2
    assert str(config.reports_dir) == "/var/lib/doctorjk/informes"
    assert config.remediation_mode is RemediationMode.DIAGNOSTICO
    assert config.auto_fix is False
    assert config.dry_run is True
    assert config.command_timeout_s == 30


def test_archivo_ausente_falla(tmp_path):
    with pytest.raises(ConfigError, match="no se pudo leer"):
        load_config(tmp_path / "no-existe.toml")


def test_toml_mal_formado_falla(tmp_path):
    ruta = _escribir(tmp_path, "esto no es = = toml valido [[[")
    with pytest.raises(ConfigError, match="no es TOML válido"):
        load_config(ruta)


def test_clave_desconocida_falla(tmp_path):
    ruta = _escribir(tmp_path, TOML_VALIDO + "\nclave_inventada = 1\n")
    with pytest.raises(ConfigError, match="clave_inventada"):
        load_config(ruta)


def test_clave_faltante_falla(tmp_path):
    sin_disco_pct = TOML_VALIDO.replace("disco_pct = 90\n", "")
    ruta = _escribir(tmp_path, sin_disco_pct)
    with pytest.raises(ConfigError, match="disco_pct"):
        load_config(ruta)


@pytest.mark.parametrize(
    "reemplazo",
    [
        "disco_pct = 0",
        "disco_pct = 101",
        'disco_pct = "90"',
    ],
)
def test_disco_pct_fuera_de_rango_o_tipo_invalido_falla(tmp_path, reemplazo):
    contenido = TOML_VALIDO.replace("disco_pct = 90", reemplazo)
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="disco_pct"):
        load_config(ruta)


def test_intervalo_monitor_negativo_falla(tmp_path):
    contenido = TOML_VALIDO.replace("intervalo_monitor_s = 30", "intervalo_monitor_s = -1")
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="intervalo_monitor_s"):
        load_config(ruta)


def test_directorio_informes_relativo_falla(tmp_path):
    contenido = TOML_VALIDO.replace(
        'directorio_informes = "/var/lib/doctorjk/informes"',
        'directorio_informes = "informes"',
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="directorio_informes"):
        load_config(ruta)


def test_modo_remediacion_invalido_falla(tmp_path):
    contenido = TOML_VALIDO.replace(
        'modo_remediacion = "diagnostico"', 'modo_remediacion = "destruir_todo"'
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="modo_remediacion"):
        load_config(ruta)


def test_auto_fix_y_dry_run_ambos_true_falla(tmp_path):
    contenido = TOML_VALIDO.replace("auto_fix = false", "auto_fix = true")
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="auto_fix"):
        load_config(ruta)


def test_auto_fix_true_con_dry_run_false_es_valido(tmp_path):
    contenido = TOML_VALIDO.replace("auto_fix = false", "auto_fix = true").replace(
        "dry_run = true", "dry_run = false"
    )
    ruta = _escribir(tmp_path, contenido)
    config = load_config(ruta)
    assert config.auto_fix is True
    assert config.dry_run is False
