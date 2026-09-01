# Pruebas del remediador (tareas #199-202, plan-finalizacion-mvp.md Gate 4.3).
# Los scripts son dobles de bash escritos a tmp_path: lo que se prueba es la
# orquestación (opt-in, mapeo, timeout, saneo de salida), no scripts-fix/ en
# sí, que tiene sus propias pruebas de shellcheck/bash -n.
from __future__ import annotations

import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest

from doctorjk.config import AppConfig, RemediationMode
from doctorjk.modelos import Incident, IncidentState, RemediationOutcome, SignalType
from doctorjk.remediador import remediate

AHORA = datetime(2026, 8, 26, tzinfo=timezone.utc)


def _config(tmp_path: Path, **overrides) -> AppConfig:
    base = dict(
        monitor_interval_s=30.0,
        persistence_cycles=2,
        cooldown_cycles=2,
        disk_pct_threshold=90,
        memory_available_mb_threshold=512,
        port_timeout_s=60.0,
        service_cycles=2,
        port_cycles=2,
        monitored_services=("postgresql.service",),
        monitored_ports=(),
        approved_memory_unit="",
        reports_dir=tmp_path,
        remediation_mode=RemediationMode.SCRIPTS,
        auto_fix=True,
        dry_run=False,
        command_timeout_s=5.0,
        llm_url="https://proveedor/v1",
        llm_model="gpt-oss-120b",
        llm_timeout_s=5.0,
        llm_cache=False,
        llm_api_key="k",
    )
    base.update(overrides)
    return AppConfig(**base)


def _incidente(signal_type: SignalType, resource_key: str) -> Incident:
    return Incident(
        incident_id="inc-remediar",
        signal_type=signal_type,
        resource_key=resource_key,
        started_at=AHORA,
        confirmed_at=AHORA,
        state=IncidentState.INCIDENT,
    )


def _instalar_script(scripts_dir: Path, nombre: str, contenido: str) -> None:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    ruta = scripts_dir / nombre
    ruta.write_text(contenido, encoding="utf-8")
    ruta.chmod(ruta.stat().st_mode | stat.S_IEXEC)


# --------------------------------------------------------- salvaguardas de opt-in


def test_sin_modo_scripts_no_ejecuta_nada(tmp_path):
    config = _config(tmp_path, remediation_mode=RemediationMode.DIAGNOSTIC)
    resultado = remediate(_incidente(SignalType.DISK_FULL, "disk:/"), config, tmp_path)
    assert resultado.outcome is RemediationOutcome.NOT_ENABLED
    assert resultado.script is None


def test_sin_auto_fix_no_ejecuta_nada(tmp_path):
    config = _config(tmp_path, auto_fix=False, dry_run=True)
    resultado = remediate(_incidente(SignalType.DISK_FULL, "disk:/"), config, tmp_path)
    assert resultado.outcome is RemediationOutcome.NOT_ENABLED


def test_tipo_sin_script_no_ejecuta_nada(tmp_path):
    config = _config(tmp_path)
    resultado = remediate(_incidente(SignalType.PORT_DOWN, "port:22:down"), config, tmp_path)
    assert resultado.outcome is RemediationOutcome.NOT_MAPPED
    assert resultado.script is None


# ------------------------------------------------------------------- ejecución


def test_script_exitoso_se_marca_resuelto(tmp_path):
    _instalar_script(
        tmp_path,
        "fix_disco.sh",
        "#!/usr/bin/env bash\necho \"limpiando $1\"\nexit 0\n",
    )
    config = _config(tmp_path)
    resultado = remediate(_incidente(SignalType.DISK_FULL, "disk:/var"), config, tmp_path)

    assert resultado.outcome is RemediationOutcome.RESOLVED
    assert resultado.exit_code == 0
    assert resultado.script == "fix_disco.sh"
    assert resultado.argv == (str(tmp_path / "fix_disco.sh"), "/var")
    assert "limpiando /var" in resultado.stdout


def test_script_con_codigo_distinto_de_cero_se_marca_fallido(tmp_path):
    _instalar_script(
        tmp_path,
        "fix_servicio.sh",
        "#!/usr/bin/env bash\necho 'no arrancó' >&2\nexit 1\n",
    )
    config = _config(tmp_path)
    resultado = remediate(
        _incidente(SignalType.SERVICE_FAILED, "service:postgresql.service"), config, tmp_path
    )

    assert resultado.outcome is RemediationOutcome.FAILED
    assert resultado.exit_code == 1
    assert "no arrancó" in resultado.stderr


def test_script_ausente_se_marca_fallido_sin_lanzar(tmp_path):
    config = _config(tmp_path)
    resultado = remediate(
        _incidente(SignalType.SERVICE_FAILED, "service:postgresql.service"), config, tmp_path
    )
    assert resultado.outcome is RemediationOutcome.FAILED
    assert resultado.exit_code is None


def test_script_colgado_agota_el_timeout_y_se_marca_fallido(tmp_path):
    _instalar_script(tmp_path, "fix_disco.sh", "#!/usr/bin/env bash\nsleep 5\n")
    config = _config(tmp_path)
    resultado = remediate(
        _incidente(SignalType.DISK_FULL, "disk:/"), config, tmp_path, timeout_s=0.2
    )
    assert resultado.outcome is RemediationOutcome.FAILED
    assert "tiempo agotado" in resultado.stderr


# ----------------------------------------------------------------- saneo y entorno


def test_stdout_stderr_se_sanitizan(tmp_path):
    _instalar_script(
        tmp_path,
        "fix_servicio.sh",
        "#!/usr/bin/env bash\necho 'conectando a 10.0.0.5' \nexit 0\n",
    )
    config = _config(tmp_path)
    resultado = remediate(
        _incidente(SignalType.SERVICE_FAILED, "service:postgresql.service"), config, tmp_path
    )
    assert "10.0.0.5" not in resultado.stdout
    assert "[IP_1]" in resultado.stdout


def test_no_se_pasa_politica_por_variables_de_entorno(tmp_path):
    # Hallazgo de auditoría #1 (2026-09-01): en producción el script corre
    # vía "sudo -n" y env_reset elimina cualquier DOCTORJK_* -- este módulo
    # ya no debe intentar pasar política por ahí ni por argv más allá del
    # recurso objetivo. El script relee su propia política de config.toml.
    _instalar_script(
        tmp_path,
        "fix_puerto.sh",
        "#!/usr/bin/env bash\n"
        "env | grep -c '^DOCTORJK_' || true\n"
        "exit 0\n",
    )
    config = _config(tmp_path, monitored_services=("nginx.service",))
    resultado = remediate(
        _incidente(SignalType.PORT_OCCUPIED, "port:80:occupied"), config, tmp_path
    )
    assert resultado.stdout.strip() == "0"
    assert len(resultado.argv) == 2  # script + recurso, nada de config_path


def test_dry_run_no_se_reporta_como_resuelto(tmp_path):
    # Hallazgo de auditoría #5: un script en dry-run sale 0 sin haber
    # verificado nada real. remediate() decide el outcome por config.dry_run
    # ANTES de mirar el código de salida, nunca confía en que el script se
    # auto-reporte como resuelto.
    _instalar_script(
        tmp_path,
        "fix_disco.sh",
        "#!/usr/bin/env bash\necho '[DRY-RUN] no ejecutado'\nexit 0\n",
    )
    # dry_run=True junto con auto_fix=True normalmente lo rechaza
    # config.load_config(), pero remediate() no debe confiar en esa
    # invariante ajena -- debe comportarse bien incluso si algo más arriba
    # construyó un AppConfig así (defensa en profundidad).
    config = _config(tmp_path, dry_run=True)
    resultado = remediate(_incidente(SignalType.DISK_FULL, "disk:/"), config, tmp_path)

    assert resultado.outcome is RemediationOutcome.DRY_RUN
    assert resultado.exit_code == 0  # el script sí corrió y salió 0...
    # ... pero eso nunca se reporta como una corrección real:
    assert resultado.outcome is not RemediationOutcome.RESOLVED


def test_dry_run_con_fallo_real_sigue_siendo_failed(tmp_path):
    # Revisión post-commit (2026-09-01): dry_run=True NO debe poder esconder
    # un fallo real detrás de un DRY_RUN que "suena a que estuvo bien". Si
    # el script sale con código distinto de 0 en dry-run, sigue siendo
    # FAILED -- DRY_RUN solo aplica cuando el script corrió y salió 0.
    _instalar_script(
        tmp_path,
        "fix_disco.sh",
        "#!/usr/bin/env bash\necho 'no pude ni simular' >&2\nexit 1\n",
    )
    config = _config(tmp_path, dry_run=True)
    resultado = remediate(_incidente(SignalType.DISK_FULL, "disk:/"), config, tmp_path)

    assert resultado.outcome is RemediationOutcome.FAILED
    assert resultado.outcome is not RemediationOutcome.DRY_RUN
    assert resultado.exit_code == 1


def test_dry_run_con_script_ausente_sigue_siendo_failed(tmp_path):
    config = _config(tmp_path, dry_run=True)
    resultado = remediate(
        _incidente(SignalType.SERVICE_FAILED, "service:postgresql.service"), config, tmp_path
    )
    assert resultado.outcome is RemediationOutcome.FAILED
    assert resultado.outcome is not RemediationOutcome.DRY_RUN
    assert resultado.exit_code is None


def test_dry_run_con_timeout_sigue_siendo_failed(tmp_path):
    _instalar_script(tmp_path, "fix_disco.sh", "#!/usr/bin/env bash\nsleep 5\n")
    config = _config(tmp_path, dry_run=True)
    resultado = remediate(
        _incidente(SignalType.DISK_FULL, "disk:/"), config, tmp_path, timeout_s=0.2
    )
    assert resultado.outcome is RemediationOutcome.FAILED
    assert resultado.outcome is not RemediationOutcome.DRY_RUN
    assert "tiempo agotado" in resultado.stderr


def test_timeout_por_default_usa_command_timeout_s(tmp_path):
    # Hallazgo de auditoría #9: el timeout de remediación no debe ignorar
    # timeout_comando_s -- mismo contrato que el resto de comandos externos.
    _instalar_script(tmp_path, "fix_disco.sh", "#!/usr/bin/env bash\nsleep 5\n")
    config = _config(tmp_path, command_timeout_s=0.2)
    resultado = remediate(_incidente(SignalType.DISK_FULL, "disk:/"), config, tmp_path)
    assert resultado.outcome is RemediationOutcome.FAILED
    assert "tiempo agotado" in resultado.stderr


def test_target_argument_extrae_el_recurso_del_resource_key(tmp_path):
    _instalar_script(tmp_path, "fix_puerto.sh", "#!/usr/bin/env bash\nexit 0\n")
    config = _config(tmp_path)
    resultado = remediate(
        _incidente(SignalType.PORT_OCCUPIED, "port:5432:occupied"), config, tmp_path
    )
    assert resultado.argv[1] == "5432"
