# Pruebas del detector (tareas #174, #176, #177, #178; plan-mvp.md bloque B2/B3).
# Usa un reloj inyectado (una lista de datetimes fijos) para no depender de
# time.sleep(): cada llamada a evaluate() representa un ciclo de polling.
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from doctorjk.detector import Detector
from doctorjk.modelos import IncidentState, Signal, SignalType

T0 = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _tick(n: int) -> datetime:
    return T0 + timedelta(seconds=30 * n)


def _señal(crossed: bool, key: str = "disk:/", value: str = "95", tipo: SignalType = SignalType.DISK_FULL) -> Signal:
    return Signal(
        timestamp=T0,
        signal_type=tipo,
        value=value,
        threshold="90",
        crossed=crossed,
        key=key,
    )


def _detector(persistence_cycles: int, cooldown_cycles: int, tipo: SignalType = SignalType.DISK_FULL) -> Detector:
    """La mayoría de estos tests solo ejercitan un tipo de señal a la vez;
    este helper arma el mapeo SignalType -> ciclos que exige el constructor
    real sin repetirlo en cada test."""
    return Detector(persistence_cycles={tipo: persistence_cycles}, cooldown_cycles=cooldown_cycles)


def test_pico_de_n_menos_uno_no_dispara():
    detector = _detector(persistence_cycles=3, cooldown_cycles=2)

    t1 = detector.evaluate([_señal(True)], _tick(1))
    t2 = detector.evaluate([_señal(True)], _tick(2))
    t3 = detector.evaluate([_señal(False)], _tick(3))  # vuelve a sano antes de N=3

    assert [t.new_state for t in t1] == [IncidentState.CANDIDATE]
    assert t2 == ()  # sigue candidato, no llegó a N
    assert [t.new_state for t in t3] == [IncidentState.NORMAL]
    assert t3[0].incident is None


def test_n_ciclos_confirma_incidente_una_sola_vez():
    detector = _detector(persistence_cycles=2, cooldown_cycles=2)

    t1 = detector.evaluate([_señal(True)], _tick(1))
    t2 = detector.evaluate([_señal(True)], _tick(2))
    t3 = detector.evaluate([_señal(True)], _tick(3))  # sigue activo: no se re-emite

    assert [t.new_state for t in t1] == [IncidentState.CANDIDATE]
    assert [t.new_state for t in t2] == [IncidentState.INCIDENT]
    assert t2[0].incident is not None
    assert t2[0].incident.state is IncidentState.INCIDENT
    assert t3 == ()  # dedup: el incidente ya está activo, no se dispara de nuevo


def test_intermitencia_reinicia_el_candidato():
    detector = _detector(persistence_cycles=3, cooldown_cycles=2)

    detector.evaluate([_señal(True)], _tick(1))
    detector.evaluate([_señal(False)], _tick(2))  # reinicia
    t3 = detector.evaluate([_señal(True)], _tick(3))
    t4 = detector.evaluate([_señal(True)], _tick(4))

    # Tras el reinicio hace falta empezar de cero: dos cruces consecutivos
    # (t3, t4) no alcanzan todavía N=3.
    assert [t.new_state for t in t3] == [IncidentState.CANDIDATE]
    assert t4 == ()


def test_recuperacion_resuelve_tras_n_ciclos_sanos():
    detector = _detector(persistence_cycles=2, cooldown_cycles=2)

    detector.evaluate([_señal(True)], _tick(1))
    detector.evaluate([_señal(True)], _tick(2))  # confirmado incidente

    t3 = detector.evaluate([_señal(False)], _tick(3))
    t4 = detector.evaluate([_señal(False)], _tick(4))

    assert t3 == ()  # una sola lectura sana no alcanza, sigue "incidente"
    assert [t.new_state for t in t4] == [IncidentState.RESOLVED]
    assert t4[0].incident.state is IncidentState.RESOLVED


def test_dos_recursos_del_mismo_tipo_tienen_contadores_independientes():
    detector = _detector(persistence_cycles=2, cooldown_cycles=2)

    t1 = detector.evaluate(
        [_señal(True, key="disk:/"), _señal(True, key="disk:/var")], _tick(1)
    )
    t2 = detector.evaluate(
        [_señal(False, key="disk:/"), _señal(True, key="disk:/var")], _tick(2)
    )

    assert {t.key for t in t1} == {"disk:/", "disk:/var"}
    # disk:/ se sanó antes de N=2 y vuelve a normal; disk:/var confirma incidente.
    claves_por_estado = {t.key: t.new_state for t in t2}
    assert claves_por_estado["disk:/"] is IncidentState.NORMAL
    assert claves_por_estado["disk:/var"] is IncidentState.INCIDENT


def test_lectura_ausente_no_avanza_ni_reinicia_el_contador():
    detector = _detector(persistence_cycles=3, cooldown_cycles=2)

    detector.evaluate([_señal(True)], _tick(1))
    detector.evaluate([], _tick(2))  # lectura ausente: la clave no aparece este ciclo
    t3 = detector.evaluate([_señal(True)], _tick(3))
    t4 = detector.evaluate([_señal(True)], _tick(4))

    assert t3 == ()  # todavía en 2 cruces consecutivos "reales", no llegó a N=3
    assert [t.new_state for t in t4] == [IncidentState.INCIDENT]


def test_enfriamiento_permite_incidente_nuevo_antes_de_llegar_a_normal():
    detector = _detector(persistence_cycles=2, cooldown_cycles=3)

    detector.evaluate([_señal(True)], _tick(1))
    detector.evaluate([_señal(True)], _tick(2))  # incidente confirmado
    detector.evaluate([_señal(False)], _tick(3))
    t4 = detector.evaluate([_señal(False)], _tick(4))  # resuelto, entra en enfriamiento

    assert [t.new_state for t in t4] == [IncidentState.RESOLVED]

    # Cruza de nuevo en pleno enfriamiento: no hace falta esperar a "normal".
    t5 = detector.evaluate([_señal(True)], _tick(5))
    t6 = detector.evaluate([_señal(True)], _tick(6))

    assert [t.new_state for t in t5] == [IncidentState.CANDIDATE]
    assert [t.new_state for t in t6] == [IncidentState.INCIDENT]
    assert t6[0].incident.incident_id != ""


def test_enfriamiento_completo_vuelve_a_normal_sin_mas_cruces():
    detector = _detector(persistence_cycles=2, cooldown_cycles=1)

    detector.evaluate([_señal(True)], _tick(1))
    detector.evaluate([_señal(True)], _tick(2))  # incidente
    detector.evaluate([_señal(False)], _tick(3))
    detector.evaluate([_señal(False)], _tick(4))  # resuelto, enfriamiento arranca
    t5 = detector.evaluate([_señal(False)], _tick(5))  # único ciclo sano que pide cooldown_cycles=1

    assert [t.new_state for t in t5] == [IncidentState.NORMAL]
    assert t5[0].incident is None


@pytest.mark.parametrize("persistence_cycles,cooldown_cycles", [(0, 1), (1, 0), (-1, 1)])
def test_umbrales_invalidos_se_rechazan(persistence_cycles, cooldown_cycles):
    with pytest.raises(ValueError):
        _detector(persistence_cycles=persistence_cycles, cooldown_cycles=cooldown_cycles)


def test_persistence_cycles_vacio_se_rechaza():
    with pytest.raises(ValueError, match="vacío"):
        Detector(persistence_cycles={}, cooldown_cycles=1)


# ------------------------------------------------- persistencia por tipo de señal


def test_tipos_distintos_confirman_con_su_propio_numero_de_ciclos():
    # service_failed confirma en 2 ciclos; disk_full necesita 4. Un mismo
    # ciclo de evaluate() con ambos tipos no debe mezclar sus contadores.
    detector = Detector(
        persistence_cycles={SignalType.SERVICE_FAILED: 2, SignalType.DISK_FULL: 4},
        cooldown_cycles=2,
    )
    servicio = lambda crossed: _señal(crossed, key="service:nginx.service", tipo=SignalType.SERVICE_FAILED)
    disco = lambda crossed: _señal(crossed, key="disk:/", tipo=SignalType.DISK_FULL)

    t1 = detector.evaluate([servicio(True), disco(True)], _tick(1))
    t2 = detector.evaluate([servicio(True), disco(True)], _tick(2))
    t3 = detector.evaluate([servicio(True), disco(True)], _tick(3))
    t4 = detector.evaluate([servicio(True), disco(True)], _tick(4))

    # El servicio confirma en el ciclo 2 (N=2); el disco recién en el 4 (N=4).
    assert {t.key: t.new_state for t in t2}["service:nginx.service"] is IncidentState.INCIDENT
    assert "disk:/" not in {t.key for t in t2}
    assert {t.key: t.new_state for t in t4}["disk:/"] is IncidentState.INCIDENT
    assert t3 == ()


def test_tipo_de_señal_sin_ciclos_configurados_falla_rapido():
    detector = Detector(persistence_cycles={SignalType.DISK_FULL: 2}, cooldown_cycles=2)
    señal_sin_mapear = _señal(True, key="port:80:down", tipo=SignalType.PORT_DOWN)
    with pytest.raises(ValueError, match="port_down"):
        detector.evaluate([señal_sin_mapear], _tick(1))


def test_servicio_falla_confirma_se_recupera_y_resuelve():
    # Congela el flujo completo que expone el defecto 1 de la auditoría:
    # un servicio vigilado cruza N ciclos, confirma, se recupera N ciclos
    # sanos y resuelve -- ya no se queda incidente activo para siempre.
    detector = _detector(persistence_cycles=2, cooldown_cycles=2, tipo=SignalType.SERVICE_FAILED)
    clave = "service:postgresql.service"
    caido = lambda: _señal(True, key=clave, tipo=SignalType.SERVICE_FAILED)
    sano = lambda: _señal(False, key=clave, tipo=SignalType.SERVICE_FAILED, value="active")

    t1 = detector.evaluate([caido()], _tick(1))
    t2 = detector.evaluate([caido()], _tick(2))
    t3 = detector.evaluate([sano()], _tick(3))
    t4 = detector.evaluate([sano()], _tick(4))

    assert [t.new_state for t in t1] == [IncidentState.CANDIDATE]
    assert [t.new_state for t in t2] == [IncidentState.INCIDENT]
    assert t3 == ()  # una sola lectura sana no alcanza a resolver todavía
    assert [t.new_state for t in t4] == [IncidentState.RESOLVED]
