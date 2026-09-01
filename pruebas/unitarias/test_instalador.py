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
from pathlib import Path

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
