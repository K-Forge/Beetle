"""Pruebas de escritura y rotación de informes (bloque D3 del plan)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from doctorjk.informe import (
    EVIDENCE_SUFFIX,
    render_report,
    rotate_reports,
    save_and_rotate,
    write_report,
)
from doctorjk.modelos import Diagnosis, Incident, IncidentState, SignalType

AHORA = datetime(2026, 8, 26, 4, 15, 0, tzinfo=timezone.utc)


def _incidente(momento: datetime = AHORA, sufijo: str = "1") -> Incident:
    return Incident(
        incident_id=f"inc-{sufijo}",
        signal_type=SignalType.SERVICE_FAILED,
        resource_key="postgresql@16-main.service",
        started_at=momento - timedelta(minutes=1),
        confirmed_at=momento,
        state=IncidentState.INCIDENT,
    )


def _diagnostico(texto: str = "## DIAGNÓSTICO\n\nSe cayó PostgreSQL.") -> Diagnosis:
    return Diagnosis("inc-1", texto, "gpt-oss-120b", from_fallback=False)


# ------------------------------------------------------------------ escritura

def test_escribe_informe_con_nombre_derivado_del_incidente(tmp_path: Path):
    destino = write_report(_diagnostico(), _incidente(), tmp_path, AHORA)

    assert destino.name == "20260826_041500_service_failed.md"
    assert "Se cayó PostgreSQL" in destino.read_text(encoding="utf-8")


def test_el_informe_incluye_trazabilidad(tmp_path: Path):
    contenido = render_report(_diagnostico(), _incidente(), AHORA)

    assert "inc-1" in contenido
    assert "postgresql@16-main.service" in contenido
    assert "gpt-oss-120b" in contenido


def test_el_informe_avisa_cuando_vino_del_fallback(tmp_path: Path):
    fallback = Diagnosis("inc-1", "sin análisis", "fallback-local", from_fallback=True)

    contenido = render_report(fallback, _incidente(), AHORA)

    # Quien lo lea debe saber que ningún modelo analizó esto.
    assert "fallback local" in contenido


def test_dos_incidentes_en_el_mismo_segundo_no_se_pisan(tmp_path: Path):
    primero = write_report(_diagnostico(), _incidente(), tmp_path, AHORA)
    segundo = write_report(_diagnostico("otro"), _incidente(), tmp_path, AHORA)

    assert primero != segundo
    assert primero.exists() and segundo.exists()


def test_no_deja_archivos_temporales(tmp_path: Path):
    write_report(_diagnostico(), _incidente(), tmp_path, AHORA)

    assert list(tmp_path.glob("*.tmp")) == []


def test_incidente_sin_confirmar_no_produce_informe(tmp_path: Path):
    sin_confirmar = Incident(
        incident_id="inc-x",
        signal_type=SignalType.SERVICE_FAILED,
        resource_key="x",
        started_at=AHORA,
        confirmed_at=None,
        state=IncidentState.CANDIDATE,
    )

    with pytest.raises(ValueError):
        write_report(_diagnostico(), sin_confirmar, tmp_path, AHORA)


# ------------------------------------------------------------------ rotación

def _crear_par(directorio: Path, indice: int) -> tuple[Path, Path]:
    momento = AHORA + timedelta(minutes=indice)
    incidente = _incidente(momento, sufijo=str(indice))
    informe = write_report(_diagnostico(), incidente, directorio, momento)
    evidencia = directorio / f"{informe.stem}{EVIDENCE_SUFFIX}"
    evidencia.write_text("evidencia cruda", encoding="utf-8")
    return informe, evidencia


def test_conserva_los_mas_recientes_y_borra_los_viejos(tmp_path: Path):
    pares = [_crear_par(tmp_path, i) for i in range(35)]

    rotate_reports(tmp_path, keep=30)

    assert len(list(tmp_path.glob("*.md"))) == 30
    # Los cinco primeros (más antiguos) desaparecieron.
    for informe, _ in pares[:5]:
        assert not informe.exists()
    for informe, _ in pares[5:]:
        assert informe.exists()


def test_la_evidencia_se_borra_junto_con_su_informe(tmp_path: Path):
    pares = [_crear_par(tmp_path, i) for i in range(32)]

    rotate_reports(tmp_path, keep=30)

    # Nunca debe quedar evidencia huérfana: son datos crudos sin nada que
    # explique por qué están en disco.
    for informe, evidencia in pares[:2]:
        assert not informe.exists()
        assert not evidencia.exists()


def test_no_borra_nada_si_no_se_supera_el_limite(tmp_path: Path):
    for i in range(10):
        _crear_par(tmp_path, i)

    assert rotate_reports(tmp_path, keep=30) == []
    assert len(list(tmp_path.glob("*.md"))) == 10


def test_un_informe_sin_evidencia_no_rompe_la_rotacion(tmp_path: Path):
    for i in range(3):
        _crear_par(tmp_path, i)
    huerfano = write_report(_diagnostico(), _incidente(AHORA + timedelta(hours=1), "z"), tmp_path, AHORA)

    rotate_reports(tmp_path, keep=1)

    assert huerfano.exists(), "el más reciente se conserva aunque no tenga evidencia"


def test_keep_negativo_es_error(tmp_path: Path):
    with pytest.raises(ValueError):
        rotate_reports(tmp_path, keep=-1)


# ------------------------------------------------------------ fallo de disco

def test_si_no_se_puede_escribir_el_diagnostico_queda_en_el_log(tmp_path: Path, caplog):
    archivo = tmp_path / "no-es-directorio"
    archivo.write_text("x", encoding="utf-8")

    with caplog.at_level("ERROR"):
        resultado = save_and_rotate(_diagnostico("texto valioso"), _incidente(), archivo, AHORA)

    assert resultado is None
    # El diagnóstico no se pierde aunque el disco falle.
    assert "texto valioso" in caplog.text
