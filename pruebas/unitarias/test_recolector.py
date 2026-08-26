# Pruebas del recolector (tareas #179-181, plan-mvp.md bloque C1).
#
# Los parsers puros (truncate_oldest_lines, parse_dpkg_log, render_snapshot_text)
# se prueban con datos sintéticos, igual que test_monitor.py. El ensamblado
# completo (collect_evidence) se prueba con doctorjk.recolector.run_command y
# take_snapshot reemplazados: journalctl/find/systemctl reales dependen del
# sistema donde corran los tests y no son deterministas.
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import doctorjk.recolector as recolector
from doctorjk.modelos import Incident, IncidentState, SignalType, SystemSnapshot
from doctorjk.monitor import CommandResult

CONFIRMADO_EN = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _incidente(signal_type=SignalType.DISK_FULL, resource_key="disk:/") -> Incident:
    return Incident(
        incident_id="abc123",
        signal_type=signal_type,
        resource_key=resource_key,
        started_at=CONFIRMADO_EN,
        confirmed_at=CONFIRMADO_EN,
        state=IncidentState.INCIDENT,
    )


def _snapshot_vacio() -> SystemSnapshot:
    return SystemSnapshot(
        captured_at=CONFIRMADO_EN,
        failed_services=(),
        services_available=True,
        disks=(),
        disk_available=True,
        memory=None,
        memory_available=False,
        ports=(),
        ports_available=True,
        load=None,
        load_available=False,
    )


# --------------------------------------------------------- truncate_oldest_lines


def test_truncate_no_recorta_si_entra_en_el_limite():
    texto = "a\nb\nc"
    resultado, recortadas = recolector.truncate_oldest_lines(texto, max_lines=5)
    assert resultado == texto
    assert recortadas == 0


def test_truncate_recorta_las_lineas_mas_antiguas():
    texto = "\n".join(str(n) for n in range(10))
    resultado, recortadas = recolector.truncate_oldest_lines(texto, max_lines=3)
    assert resultado == "7\n8\n9"
    assert recortadas == 7


# --------------------------------------------------------------- parse_dpkg_log


def test_parse_dpkg_log_filtra_por_fecha_y_accion():
    texto = (
        "2026-08-20 10:00:00 status half-installed algo:amd64 1.0\n"
        "2026-08-24 09:00:00 install nginx:amd64 <none> 1.2\n"
        "2026-08-24 09:00:01 upgrade postgresql:amd64 1.0 1.1\n"
        "2026-08-01 00:00:00 install viejo:amd64 <none> 1.0\n"
    )
    since = datetime(2026, 8, 23, 0, 0, tzinfo=timezone.utc)
    resultado = recolector.parse_dpkg_log(texto, since)
    assert len(resultado) == 2
    assert "nginx" in resultado[0]
    assert "postgresql" in resultado[1]


def test_parse_dpkg_log_sin_coincidencias():
    since = datetime(2026, 8, 24, 0, 0, tzinfo=timezone.utc)
    assert recolector.parse_dpkg_log("2020-01-01 00:00:00 install x:amd64 1.0\n", since) == ()


# ------------------------------------------------------------- render_snapshot_text


def test_render_snapshot_text_marca_categorias_no_disponibles():
    texto = recolector.render_snapshot_text(_snapshot_vacio())
    assert "servicios fallidos: ninguno" in texto
    assert "memoria: no disponible" in texto
    assert "carga: no disponible" in texto


# --------------------------------------------------- _run_find_tolerando_permisos


def test_run_find_tolera_codigo_1_con_salida_parcial():
    # find real bajo /etc como usuario sin privilegios termina en 1 en cuanto
    # topa con un subdirectorio sin permiso, aunque haya listado bien el
    # resto (comprobado contra /etc en este mismo entorno).
    resultado = recolector._run_find_tolerando_permisos(
        ["bash", "-c", "echo /etc/algo; exit 1"], timeout_s=2.0
    )
    assert resultado.success is True
    assert resultado.stdout.strip() == "/etc/algo"


def test_run_find_codigo_distinto_de_cero_y_uno_es_fallo():
    resultado = recolector._run_find_tolerando_permisos(["bash", "-c", "exit 2"], timeout_s=2.0)
    assert resultado.success is False


def test_run_find_timeout():
    resultado = recolector._run_find_tolerando_permisos(["sleep", "5"], timeout_s=0.05)
    assert resultado.success is False
    assert "tiempo agotado" in resultado.error


# ----------------------------------------------------------------- collect_evidence


def test_collect_evidence_incidente_sin_confirmed_at_falla():
    incidente_sin_confirmar = Incident(
        incident_id="x",
        signal_type=SignalType.DISK_FULL,
        resource_key="disk:/",
        started_at=CONFIRMADO_EN,
        confirmed_at=None,
        state=IncidentState.CANDIDATE,
    )
    with pytest.raises(ValueError, match="confirmed_at"):
        recolector.collect_evidence(incidente_sin_confirmar, Path("/no/importa"), now=CONFIRMADO_EN)


def test_collect_evidence_ensambla_las_cinco_secciones(monkeypatch, tmp_path):
    monkeypatch.setattr(
        recolector,
        "run_command",
        lambda argv, timeout_s: CommandResult(stdout="linea de log\n", success=True, error=None),
    )
    monkeypatch.setattr(
        recolector,
        "_run_find_tolerando_permisos",
        lambda argv, timeout_s: CommandResult(stdout="", success=True, error=None),
    )
    monkeypatch.setattr(recolector, "take_snapshot", lambda timeout_s: _snapshot_vacio())
    monkeypatch.setattr(
        recolector,
        "read_dpkg_log",
        lambda path: CommandResult(stdout="", success=True, error=None),
    )

    evidencia = recolector.collect_evidence(
        _incidente(), reports_dir=tmp_path, now=CONFIRMADO_EN
    )

    assert "METADATOS" in evidencia.raw_text
    assert "LOGS" in evidencia.raw_text
    assert "SNAPSHOT" in evidencia.raw_text
    assert "CAMBIOS RECIENTES" in evidencia.raw_text
    assert "HISTORIAL" in evidencia.raw_text
    assert evidencia.partial_errors == ()
    assert "sin incidentes previos registrados" in evidencia.history_text


def test_collect_evidence_seccion_fallida_no_descarta_las_demas(monkeypatch, tmp_path):
    def run_command_falla_journal(argv, timeout_s):
        if argv[0] == "journalctl":
            return CommandResult(stdout="", success=False, error="comando no encontrado")
        return CommandResult(stdout="", success=True, error=None)

    monkeypatch.setattr(recolector, "run_command", run_command_falla_journal)
    monkeypatch.setattr(
        recolector,
        "_run_find_tolerando_permisos",
        lambda argv, timeout_s: CommandResult(stdout="", success=True, error=None),
    )
    monkeypatch.setattr(recolector, "take_snapshot", lambda timeout_s: _snapshot_vacio())
    monkeypatch.setattr(
        recolector,
        "read_dpkg_log",
        lambda path: CommandResult(stdout="", success=True, error=None),
    )

    evidencia = recolector.collect_evidence(_incidente(), reports_dir=tmp_path, now=CONFIRMADO_EN)

    assert len(evidencia.partial_errors) == 1
    assert "logs" in evidencia.partial_errors[0]
    # Las demás secciones se recolectaron igual.
    assert "no disponible" in evidencia.logs_text
    assert "SNAPSHOT" in evidencia.raw_text
    assert "sin incidentes previos registrados" in evidencia.history_text


def test_collect_evidence_service_failed_consulta_tambien_la_unidad(monkeypatch, tmp_path):
    comandos_ejecutados: list[list[str]] = []

    def run_command_falso(argv, timeout_s):
        comandos_ejecutados.append(list(argv))
        return CommandResult(stdout="linea\n", success=True, error=None)

    monkeypatch.setattr(recolector, "run_command", run_command_falso)
    monkeypatch.setattr(
        recolector,
        "_run_find_tolerando_permisos",
        lambda argv, timeout_s: CommandResult(stdout="", success=True, error=None),
    )
    monkeypatch.setattr(recolector, "take_snapshot", lambda timeout_s: _snapshot_vacio())
    monkeypatch.setattr(
        recolector,
        "read_dpkg_log",
        lambda path: CommandResult(stdout="", success=True, error=None),
    )

    incidente = _incidente(signal_type=SignalType.SERVICE_FAILED, resource_key="service:postgresql.service")
    recolector.collect_evidence(incidente, reports_dir=tmp_path, now=CONFIRMADO_EN)

    llamadas_unidad = [c for c in comandos_ejecutados if "-u" in c]
    assert len(llamadas_unidad) == 1
    assert "postgresql.service" in llamadas_unidad[0]


def test_collect_evidence_historial_lista_informes_previos_mas_recientes_primero(monkeypatch, tmp_path):
    monkeypatch.setattr(
        recolector,
        "run_command",
        lambda argv, timeout_s: CommandResult(stdout="", success=True, error=None),
    )
    monkeypatch.setattr(
        recolector,
        "_run_find_tolerando_permisos",
        lambda argv, timeout_s: CommandResult(stdout="", success=True, error=None),
    )
    monkeypatch.setattr(recolector, "take_snapshot", lambda timeout_s: _snapshot_vacio())
    monkeypatch.setattr(
        recolector,
        "read_dpkg_log",
        lambda path: CommandResult(stdout="", success=True, error=None),
    )

    viejo = tmp_path / "20260101_disk_full.md"
    viejo.write_text("viejo", encoding="utf-8")
    nuevo = tmp_path / "20260824_disk_full.md"
    nuevo.write_text("nuevo", encoding="utf-8")
    import os
    import time

    os.utime(viejo, (time.time() - 100, time.time() - 100))

    evidencia = recolector.collect_evidence(_incidente(), reports_dir=tmp_path, now=CONFIRMADO_EN)

    lineas = evidencia.history_text.splitlines()
    assert lineas[0] == nuevo.name
    assert lineas[1] == viejo.name
