# Pruebas de normalize_snapshot(): SystemSnapshot -> Signal, el contrato de
# la tarea #173. Cubren las cuatro senales que ya se emiten (servicio, disco,
# memoria, puerto) y las dos reglas que no son obvias del nombre de la
# funcion: una categoria no disponible no debe verse como "sana", y la carga
# todavia no se convierte en Signal.
from __future__ import annotations

from datetime import datetime, timezone

from doctorjk.modelos import (
    DiskUsage,
    FailedService,
    ListeningPort,
    LoadAverage,
    MemoryUsage,
    SignalType,
    SystemSnapshot,
)
from doctorjk.monitor import normalize_snapshot

MARCA_DE_TIEMPO = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

UMBRALES = dict(disk_pct_threshold=90, memory_available_mb_threshold=400, monitored_ports=frozenset())


def _snapshot(**overrides) -> SystemSnapshot:
    base = dict(
        captured_at=MARCA_DE_TIEMPO,
        failed_services=(),
        services_available=True,
        disks=(),
        disk_available=True,
        memory=MemoryUsage(total_mb=3900, used_mb=1200, free_mb=800, available_mb=2400),
        memory_available=True,
        ports=(),
        ports_available=True,
        load=LoadAverage(load_1m=0.1, load_5m=0.1, load_15m=0.1),
        load_available=True,
    )
    base.update(overrides)
    return SystemSnapshot(**base)


def test_servicio_fallido_cruza():
    snapshot = _snapshot(failed_services=(FailedService(name="postgresql.service"),))
    señales = normalize_snapshot(snapshot, **UMBRALES)
    de_servicio = [s for s in señales if s.signal_type is SignalType.SERVICE_FAILED]
    assert len(de_servicio) == 1
    assert de_servicio[0].crossed is True
    assert de_servicio[0].key == "service:postgresql.service"
    assert de_servicio[0].value == "postgresql.service"


def test_sin_servicios_fallidos_no_emite_nada():
    señales = normalize_snapshot(_snapshot(), **UMBRALES)
    assert not [s for s in señales if s.signal_type is SignalType.SERVICE_FAILED]


def test_disco_cruzado_y_no_cruzado_en_la_misma_lectura():
    snapshot = _snapshot(
        disks=(
            DiskUsage(source="/dev/sda1", usage_percent=97, target="/"),
            DiskUsage(source="tmpfs", usage_percent=10, target="/dev/shm"),
        )
    )
    señales = {s.key: s for s in normalize_snapshot(snapshot, **UMBRALES)}
    assert señales["disk:/"].crossed is True
    assert señales["disk:/dev/shm"].crossed is False


def test_memoria_baja_cruza():
    snapshot = _snapshot(
        memory=MemoryUsage(total_mb=3900, used_mb=3700, free_mb=100, available_mb=180)
    )
    señal = next(
        s for s in normalize_snapshot(snapshot, **UMBRALES) if s.signal_type is SignalType.MEMORY_LOW
    )
    assert señal.crossed is True
    assert señal.key == "memory"


def test_memoria_suficiente_no_cruza():
    señal = next(
        s
        for s in normalize_snapshot(_snapshot(), **UMBRALES)
        if s.signal_type is SignalType.MEMORY_LOW
    )
    assert señal.crossed is False


def test_puerto_caido_cuando_no_esta_escuchando():
    snapshot = _snapshot(ports=(ListeningPort(address="0.0.0.0", port=22),))
    umbrales = dict(UMBRALES, monitored_ports=frozenset({22, 5432}))
    señales = {s.key: s for s in normalize_snapshot(snapshot, **umbrales)}
    assert señales["port:22"].crossed is False
    assert señales["port:5432"].crossed is True


def test_categoria_no_disponible_no_emite_señal_sana():
    # Un df que fallo no debe traducirse en "0% de uso, todo bien": debe
    # quedar sin señal, distinto de una lectura que si vino y esta sana.
    snapshot = _snapshot(disk_available=False, disks=())
    señales = normalize_snapshot(snapshot, **UMBRALES)
    assert not [s for s in señales if s.signal_type is SignalType.DISK_FULL]


def test_servicios_no_disponibles_no_emite_señal():
    snapshot = _snapshot(services_available=False, failed_services=())
    señales = normalize_snapshot(snapshot, **UMBRALES)
    assert not [s for s in señales if s.signal_type is SignalType.SERVICE_FAILED]


def test_carga_nunca_se_convierte_en_señal():
    señales = normalize_snapshot(_snapshot(), **UMBRALES)
    assert not [s for s in señales if s.signal_type is SignalType.HIGH_LOAD]
