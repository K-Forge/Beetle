# Pruebas de config.py (tarea #175 adelantada, plan-mvp.md bloque B1): una
# config válida produce un AppConfig tipado; cualquier desvío (clave ausente,
# desconocida, tipo o rango inválido, combinación de modo contradictoria)
# falla al cargar, con un mensaje que nombra la clave en español.
from __future__ import annotations

import pytest

from doctorjk.config import AppConfig, ConfigError, RemediationMode, load_config
from doctorjk.modelos import MonitoredPort

TOML_VALIDO = """
intervalo_monitor_s = 30
ciclos_persistencia = 2
enfriamiento_ciclos = 2
disco_pct = 90
memoria_disponible_mb = 512
puerto_timeout_s = 60
servicio_ciclos = 2
servicios_vigilados = ["nginx.service", "postgresql.service"]
puertos_vigilados = [
  { puerto = 80, servicio = "nginx.service" },
  { puerto = 5432, servicio = "postgresql.service" },
]
unidad_memoria_aprobada = ""
ocupantes_puerto_aprobados = []
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
    assert config.port_cycles == 2  # ceil(60 / 30)
    assert config.monitored_services == ("nginx.service", "postgresql.service")
    assert config.monitored_ports == (
        MonitoredPort(port=80, service="nginx.service"),
        MonitoredPort(port=5432, service="postgresql.service"),
    )
    assert config.approved_memory_unit == ""
    assert config.approved_port_occupants == ()
    assert str(config.reports_dir) == "/var/lib/doctorjk/informes"
    assert config.remediation_mode is RemediationMode.DIAGNOSTIC
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


# --------------------------------------------------- servicios_vigilados / puertos_vigilados


def test_port_cycles_redondea_hacia_arriba(tmp_path):
    # 60s de timeout sobre un intervalo de 30s exige exactamente 2 ciclos; un
    # intervalo que no divide justo debe redondear hacia arriba, nunca hacia
    # abajo (nunca confirmar con menos tiempo del pedido).
    contenido = TOML_VALIDO.replace("intervalo_monitor_s = 30", "intervalo_monitor_s = 25")
    ruta = _escribir(tmp_path, contenido)
    config = load_config(ruta)
    assert config.port_cycles == 3  # ceil(60 / 25) = 3


def test_servicios_vigilados_vacio_falla(tmp_path):
    contenido = TOML_VALIDO.replace(
        'servicios_vigilados = ["nginx.service", "postgresql.service"]',
        "servicios_vigilados = []",
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="servicios_vigilados"):
        load_config(ruta)


def test_servicios_vigilados_duplicado_falla(tmp_path):
    contenido = TOML_VALIDO.replace(
        'servicios_vigilados = ["nginx.service", "postgresql.service"]',
        'servicios_vigilados = ["nginx.service", "nginx.service"]',
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="servicios_vigilados"):
        load_config(ruta)


@pytest.mark.parametrize("unidad", ["nginx service", "../nginx.service", "a/b.service", "$(rm)"])
def test_servicios_vigilados_con_metacaracteres_falla(tmp_path, unidad):
    contenido = TOML_VALIDO.replace(
        'servicios_vigilados = ["nginx.service", "postgresql.service"]',
        f'servicios_vigilados = ["{unidad}"]',
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="servicios_vigilados"):
        load_config(ruta)


def test_puertos_vigilados_fuera_de_rango_falla(tmp_path):
    contenido = TOML_VALIDO.replace(
        '{ puerto = 80, servicio = "nginx.service" },',
        '{ puerto = 70000, servicio = "nginx.service" },',
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="puertos_vigilados"):
        load_config(ruta)


def test_puertos_vigilados_duplicado_falla(tmp_path):
    contenido = TOML_VALIDO.replace(
        '{ puerto = 5432, servicio = "postgresql.service" },',
        '{ puerto = 80, servicio = "postgresql.service" },',
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="puertos_vigilados"):
        load_config(ruta)


def test_unidad_memoria_aprobada_vacia_es_valida(tmp_path):
    ruta = _escribir(tmp_path, TOML_VALIDO)
    assert load_config(ruta).approved_memory_unit == ""


def test_unidad_memoria_aprobada_con_nombre_valido(tmp_path):
    contenido = TOML_VALIDO.replace(
        'unidad_memoria_aprobada = ""', 'unidad_memoria_aprobada = "appcarga.service"'
    )
    ruta = _escribir(tmp_path, contenido)
    assert load_config(ruta).approved_memory_unit == "appcarga.service"


def test_unidad_memoria_aprobada_con_metacaracteres_falla(tmp_path):
    contenido = TOML_VALIDO.replace(
        'unidad_memoria_aprobada = ""', 'unidad_memoria_aprobada = "../etc/passwd"'
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="unidad_memoria_aprobada"):
        load_config(ruta)


def test_puertos_vigilados_sin_servicio_falla(tmp_path):
    contenido = TOML_VALIDO.replace(
        '{ puerto = 80, servicio = "nginx.service" },',
        "{ puerto = 80 },",
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="puertos_vigilados"):
        load_config(ruta)


# ------------------------------------------------------- ocupantes_puerto_aprobados


def test_ocupantes_puerto_aprobados_vacio_es_valido(tmp_path):
    # Default seguro: sin nada aprobado, fix_puerto.sh escala en vez de
    # detener cualquier cosa (a diferencia de servicios_vigilados, acá una
    # lista vacía NO es un error).
    ruta = _escribir(tmp_path, TOML_VALIDO)
    assert load_config(ruta).approved_port_occupants == ()


def test_ocupantes_puerto_aprobados_con_nombres_validos(tmp_path):
    contenido = TOML_VALIDO.replace(
        "ocupantes_puerto_aprobados = []",
        'ocupantes_puerto_aprobados = ["appcarga.service", "doctorjk-test-occupier.service"]',
    )
    ruta = _escribir(tmp_path, contenido)
    assert load_config(ruta).approved_port_occupants == (
        "appcarga.service",
        "doctorjk-test-occupier.service",
    )


def test_ocupantes_puerto_aprobados_duplicado_falla(tmp_path):
    contenido = TOML_VALIDO.replace(
        "ocupantes_puerto_aprobados = []",
        'ocupantes_puerto_aprobados = ["appcarga.service", "appcarga.service"]',
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="ocupantes_puerto_aprobados"):
        load_config(ruta)


@pytest.mark.parametrize("unidad", ["nginx service", "../nginx.service", "a/b.service", "$(rm)"])
def test_ocupantes_puerto_aprobados_con_metacaracteres_falla(tmp_path, unidad):
    contenido = TOML_VALIDO.replace(
        "ocupantes_puerto_aprobados = []",
        f'ocupantes_puerto_aprobados = ["{unidad}"]',
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="ocupantes_puerto_aprobados"):
        load_config(ruta)


def test_ocupantes_puerto_aprobados_no_es_lista_falla(tmp_path):
    contenido = TOML_VALIDO.replace(
        "ocupantes_puerto_aprobados = []",
        'ocupantes_puerto_aprobados = "appcarga.service"',
    )
    ruta = _escribir(tmp_path, contenido)
    with pytest.raises(ConfigError, match="ocupantes_puerto_aprobados"):
        load_config(ruta)


def test_ocupantes_puerto_aprobados_independiente_de_servicios_vigilados(tmp_path):
    # El punto del hallazgo P0: una unidad puede estar en una lista sin
    # estar en la otra. Acá está aprobada para detenerse pero NO vigilada.
    contenido = TOML_VALIDO.replace(
        "ocupantes_puerto_aprobados = []",
        'ocupantes_puerto_aprobados = ["doctorjk-test-occupier.service"]',
    )
    ruta = _escribir(tmp_path, contenido)
    config = load_config(ruta)
    assert "doctorjk-test-occupier.service" in config.approved_port_occupants
    assert "doctorjk-test-occupier.service" not in config.monitored_services
