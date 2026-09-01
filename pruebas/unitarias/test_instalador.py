# Pruebas estáticas del instalador y las unidades de systemd (Gate 4,
# hallazgos de auditoría del 2026-09-01). No requieren root ni una
# instalación real -- verifican el texto fuente para blindar contra una
# regresión de los bloqueantes P0 que ya se corrigieron una vez:
#
#   1. NoNewPrivileges=true en doctorjk.service anularía sudo -n sin importar
#      qué tan exacto sea el sudoers (systemd.exec(5)).
#   2. ProtectSystem=strict deja /var/log de solo lectura incluso para un
#      hijo root vía sudo (namespaces de montaje, no permisos Unix).
#   3. install.sh nunca debe EJECUTAR un fix_*.sh real -- eso dispararía una
#      remediación de verdad como efecto secundario de instalarse.
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from doctorjk.config import load_config

REPO_ROOT = Path(__file__).parent.parent.parent
DOCTORJK_SERVICE = (REPO_ROOT / "instalador" / "doctorjk.service").read_text(encoding="utf-8")
INSTALL_SH = (REPO_ROOT / "instalador" / "install.sh").read_text(encoding="utf-8")


# --------------------------------------------------------- doctorjk.service


def test_no_tiene_nonewprivileges():
    # Con NoNewPrivileges=true, sudo -n nunca escala a root sin importar el
    # sudoers -- Modo 2 fallaría siempre en producción.
    assert not re.search(r"^\s*NoNewPrivileges\s*=\s*true", DOCTORJK_SERVICE, re.MULTILINE)


def test_documenta_por_que_no_tiene_nonewprivileges():
    # Que la ausencia sea una decisión explícita, no un descuido: el
    # trade-off debe quedar legible para quien audite la unidad después.
    assert "NoNewPrivileges" in DOCTORJK_SERVICE
    assert "sudo" in DOCTORJK_SERVICE.lower()


def test_var_log_esta_en_readwritepaths():
    # ProtectSystem=strict deja /var/log de solo lectura incluso para un
    # hijo root vía sudo (namespace de montaje heredado); sin esto,
    # fix_disco.sh fallaría con "Read-only file system".
    match = re.search(r"^\s*ReadWritePaths\s*=\s*(.+)$", DOCTORJK_SERVICE, re.MULTILINE)
    assert match is not None, "doctorjk.service no declara ReadWritePaths"
    paths = match.group(1).split()
    assert "/var/log" in paths
    assert "/var/lib/doctorjk" in paths


def test_protectsystem_sigue_en_strict():
    # El hardening real (no solo sudoers) debe seguir vigente: la ampliación
    # de ReadWritePaths no debe venir acompañada de aflojar esto también.
    assert re.search(r"^\s*ProtectSystem\s*=\s*strict", DOCTORJK_SERVICE, re.MULTILINE)


# -------------------------------------------------------------- install.sh


def test_install_sh_no_ejecuta_scripts_fix_directamente():
    # Cualquier mención a un fix_*.sh que NO sea la plantilla de sudoers ni
    # la copia con install(1) debe pasar por "sudo -n -l" (verificación de
    # autorización) o "visudo -cf" (validación de sintaxis) -- nunca una
    # ejecución real.
    for numero_linea, linea in enumerate(INSTALL_SH.splitlines(), start=1):
        if "fix_" not in linea or ".sh" not in linea:
            continue
        es_plantilla_sudoers = "NOPASSWD:" in linea
        es_copia = re.search(r"\binstall\s+-m\s+0755\b", linea) or "fix_script" in linea
        es_verificacion = "sudo -n -l" in linea
        es_comentario_o_variable = linea.strip().startswith("#") or "$fix_script" in linea
        assert es_plantilla_sudoers or es_copia or es_verificacion or es_comentario_o_variable, (
            f"install.sh:{numero_linea} podría estar ejecutando un fix_*.sh de verdad: {linea!r}"
        )


def test_install_sh_verifica_autorizacion_sin_ejecutar():
    assert "sudo -n -l" in INSTALL_SH


def test_install_sh_valida_sudoers_con_visudo():
    assert re.search(r"\bvisudo\s+-cf\b", INSTALL_SH)


def test_install_sh_chequea_nonewprivileges_de_la_unidad_instalada():
    # Chequeo estático sobre el archivo YA copiado a /etc/systemd/system,
    # para detectar también un despliegue con una unidad vieja o distinta.
    assert "NoNewPrivileges" in INSTALL_SH
    assert re.search(r"grep\s+-qE?\s+.*NoNewPrivileges", INSTALL_SH)


def test_install_sh_reafirma_permisos_de_config_toml_en_cada_corrida():
    # Hallazgo de auditoría (2026-09-01): si config.toml ya existe (una
    # reinstalación), el bloque original lo dejaba intacto sin más --
    # incluidos dueño/permisos. comun.sh ahora falla cerrado si config.toml
    # no es exactamente root:doctorjk 0640 (defensa #1-bis); sin esta
    # reafirmación, unos permisos que quedaron mal en algún momento romperían
    # Modo 2 en silencio hasta que alguien lo notara a mano.
    #
    # Se busca fuera del bloque if/else de creación, igual que ya se hace
    # para .env, para confirmar que corre SIEMPRE, no solo en la rama "recién
    # creado".
    match = re.search(
        r'if \[\[ -f "\$CONFIG_DIR/config\.toml" \]\]; then.*?\nfi\n(.*?)\n\n',
        INSTALL_SH,
        re.DOTALL,
    )
    assert match is not None, "no encontré el bloque de config.toml en install.sh"
    despues_del_bloque = match.group(1)
    assert re.search(r'chown\s+root:"?\$SERVICE_USER"?\s+"\$CONFIG_DIR/config\.toml"', despues_del_bloque)
    assert re.search(r'chmod\s+0640\s+"\$CONFIG_DIR/config\.toml"', despues_del_bloque)


# ------------------------------------------- migración aditiva de config.toml
#
# Hallazgo de auditoría (2026-09-01): install.sh preserva config.toml
# existente sin tocarlo ("se conserva sin cambios"), pero Gate 4 agregó
# claves nuevas al esquema (unidad_memoria_aprobada, luego
# ocupantes_puerto_aprobados) que un config.toml de antes de Gate 4 no
# tiene -- verificado en git log (1cb7698 agrega servicios_vigilados/
# puertos_vigilados sin ninguna de las dos; 0f333f8, el commit siguiente,
# agrega recién unidad_memoria_aprobada). Sin migración, reinstalar Gate 4
# sobre esa config deja el archivo intacto y el primer restart de
# doctorjk.service revienta con ConfigError -- load_config() es estricto,
# cualquier clave del esquema ausente se rechaza.
#
# Estas pruebas ejecutan la función de migración REAL extraída de
# install.sh (no una reimplementación de prueba) contra un fixture con el
# esquema real de Gate 3 -- config.toml sin ninguna de las dos claves --
# y validan el resultado con el parser real (doctorjk.config.load_config).

_GATE3_FIXTURE_TOML = """\
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
# A propósito, SIN unidad_memoria_aprobada ni ocupantes_puerto_aprobados:
# así era el esquema real de Gate 3, antes de que Gate 4 agregara Modo 2.


def _extraer_funcion_migracion() -> str:
    match = re.search(
        r"_migrar_clave_config_faltante\(\) \{.*?\n\}\n",
        INSTALL_SH,
        re.DOTALL,
    )
    assert match is not None, "no encontré _migrar_clave_config_faltante en install.sh"
    return match.group(0)


def _extraer_llamadas_migracion() -> str:
    llamadas = re.findall(r"^_migrar_clave_config_faltante .*$", INSTALL_SH, re.MULTILINE)
    assert len(llamadas) == 2, f"esperaba 2 llamadas de migración, encontré {len(llamadas)}"
    return "\n".join(llamadas)


def _correr_migracion(config_path: Path) -> subprocess.CompletedProcess[str]:
    # info()/step() son no-op: install.sh real las usa solo para mensajes
    # de progreso, no afectan el resultado que se está probando.
    script = f"""#!/usr/bin/env bash
set -euo pipefail
CONFIG_DIR="{config_path.parent}"
info() {{ :; }}
step() {{ :; }}
{_extraer_funcion_migracion()}
{_extraer_llamadas_migracion()}
"""
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=10
    )


def test_migracion_agrega_claves_gate4_faltantes_a_config_gate3(tmp_path: Path):
    ruta = tmp_path / "config.toml"
    ruta.write_text(_GATE3_FIXTURE_TOML, encoding="utf-8")
    contenido_original = ruta.read_text(encoding="utf-8")

    resultado = _correr_migracion(ruta)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr

    contenido_migrado = ruta.read_text(encoding="utf-8")
    assert contenido_original in contenido_migrado, "no debe tocar ninguna línea existente"
    assert 'unidad_memoria_aprobada = ""' in contenido_migrado
    assert "ocupantes_puerto_aprobados = []" in contenido_migrado

    config = load_config(ruta)
    assert config.approved_memory_unit == ""
    assert config.approved_port_occupants == ()


def test_migracion_es_idempotente_no_duplica_en_dos_corridas(tmp_path: Path):
    ruta = tmp_path / "config.toml"
    ruta.write_text(_GATE3_FIXTURE_TOML, encoding="utf-8")

    primera = _correr_migracion(ruta)
    assert primera.returncode == 0, primera.stdout + primera.stderr
    tras_primera = ruta.read_text(encoding="utf-8")

    segunda = _correr_migracion(ruta)
    assert segunda.returncode == 0, segunda.stdout + segunda.stderr
    tras_segunda = ruta.read_text(encoding="utf-8")

    assert tras_primera == tras_segunda, "una segunda corrida no debe cambiar nada más"
    assert tras_segunda.count("unidad_memoria_aprobada") == 1
    assert tras_segunda.count("ocupantes_puerto_aprobados") == 1

    config = load_config(ruta)
    assert config.approved_memory_unit == ""
    assert config.approved_port_occupants == ()


def test_migracion_no_toca_una_config_que_ya_tiene_ambas_claves(tmp_path: Path):
    # Con valores no-default a propósito: si la migración las pisara con
    # el default, este test lo detectaría.
    contenido = _GATE3_FIXTURE_TOML + (
        'unidad_memoria_aprobada = "appcarga.service"\n'
        'ocupantes_puerto_aprobados = ["appcarga.service"]\n'
    )
    ruta = tmp_path / "config.toml"
    ruta.write_text(contenido, encoding="utf-8")

    resultado = _correr_migracion(ruta)
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert ruta.read_text(encoding="utf-8") == contenido, "no debe agregar ni pisar nada"

    config = load_config(ruta)
    assert config.approved_memory_unit == "appcarga.service"
    assert config.approved_port_occupants == ("appcarga.service",)
