# Pruebas de normalize_snapshot(): SystemSnapshot -> Signal, el contrato de
# la tarea #173, ya corregido por plan-finalizacion-mvp.md Gate 1.3: los
# servicios y puertos vigilados emiten señal sana o cruzada en todos los
# ciclos (defecto 1), y cada puerto trae dos señales independientes --
# port_down (nadie escucha) y port_occupied (alguien escucha, pero no es el
# servicio esperado) -- porque son condiciones distintas (defecto 6).
from __future__ import annotations

from datetime import datetime, timezone

from doctorjk.modelos import (
    DiskUsage,
    ListeningPort,
    LoadAverage,
    MemoryUsage,
    MonitoredPort,
    ServiceState,
    SignalType,
    SystemSnapshot,
)
from doctorjk.monitor import normalize_snapshot

MARCA_DE_TIEMPO = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

UMBRALES = dict(
    disk_pct_threshold=90,
    memory_available_mb_threshold=400,
    monitored_ports=(),
    monitored_mount_points=("/",),
)


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
        service_states=(),
        service_states_available=True,
    )
    base.update(overrides)
    return SystemSnapshot(**base)


# --------------------------------------------------------------------- servicios


def test_servicio_vigilado_inactivo_cruza():
    snapshot = _snapshot(service_states=(ServiceState(name="postgresql.service", active=False),))
    señales = normalize_snapshot(snapshot, **UMBRALES)
    de_servicio = [s for s in señales if s.signal_type is SignalType.SERVICE_FAILED]
    assert len(de_servicio) == 1
    assert de_servicio[0].crossed is True
    assert de_servicio[0].key == "service:postgresql.service"
    assert de_servicio[0].value == "inactive"


def test_servicio_vigilado_activo_no_cruza():
    # El defecto original: un servicio sano nunca aparece en `--failed`, así
    # que antes no se emitía nada. Ahora sí, con crossed=False.
    snapshot = _snapshot(service_states=(ServiceState(name="nginx.service", active=True),))
    señal = next(
        s for s in normalize_snapshot(snapshot, **UMBRALES) if s.signal_type is SignalType.SERVICE_FAILED
    )
    assert señal.crossed is False
    assert señal.key == "service:nginx.service"
    assert señal.value == "active"


def test_sin_servicios_vigilados_no_emite_nada():
    señales = normalize_snapshot(_snapshot(), **UMBRALES)
    assert not [s for s in señales if s.signal_type is SignalType.SERVICE_FAILED]


def test_dos_servicios_vigilados_mantienen_claves_independientes():
    snapshot = _snapshot(
        service_states=(
            ServiceState(name="nginx.service", active=True),
            ServiceState(name="postgresql.service", active=False),
        )
    )
    señales = {s.key: s for s in normalize_snapshot(snapshot, **UMBRALES) if s.signal_type is SignalType.SERVICE_FAILED}
    assert señales["service:nginx.service"].crossed is False
    assert señales["service:postgresql.service"].crossed is True


def test_service_states_no_disponible_no_emite_señal():
    snapshot = _snapshot(
        service_states_available=False,
        service_states=(),
    )
    señales = normalize_snapshot(snapshot, **UMBRALES)
    assert not [s for s in señales if s.signal_type is SignalType.SERVICE_FAILED]


# ------------------------------------------------------------------------ disco


def test_disco_cruzado_y_no_cruzado_en_la_misma_lectura():
    # Ambos mounts vigilados a propósito acá -- lo que se prueba es que las
    # señales de dos mounts distintos no se confunden entre sí, no el
    # filtro de vigilancia (que tiene sus propias pruebas más abajo).
    snapshot = _snapshot(
        disks=(
            DiskUsage(source="/dev/sda1", usage_percent=97, target="/"),
            DiskUsage(source="tmpfs", usage_percent=10, target="/dev/shm"),
        )
    )
    umbrales = dict(UMBRALES, monitored_mount_points=("/", "/dev/shm"))
    señales = {s.key: s for s in normalize_snapshot(snapshot, **umbrales)}
    assert señales["disk:/"].crossed is True
    assert señales["disk:/dev/shm"].crossed is False


def test_categoria_no_disponible_no_emite_señal_sana():
    # Un df que fallo no debe traducirse en "0% de uso, todo bien": debe
    # quedar sin señal, distinto de una lectura que si vino y esta sana.
    snapshot = _snapshot(disk_available=False, disks=())
    señales = normalize_snapshot(snapshot, **UMBRALES)
    assert not [s for s in señales if s.signal_type is SignalType.DISK_FULL]


def test_mount_no_vigilado_no_emite_señal():
    # Hallazgo de auditoría (2026-09-01): /boot y /boot/efi cruzando un
    # umbral bajo no deben generar disk_full si nunca se pidió vigilarlos
    # -- el filtro de puntos_montaje_vigilados, con el default ["/"], deja
    # afuera cualquier mount que no sea la raíz.
    snapshot = _snapshot(
        disks=(
            DiskUsage(source="/dev/sda1", usage_percent=3, target="/"),
            DiskUsage(source="/dev/sda16", usage_percent=22, target="/boot"),
            DiskUsage(source="/dev/sda15", usage_percent=7, target="/boot/efi"),
            DiskUsage(source="efivarfs", usage_percent=6, target="/sys/firmware/efi/efivars"),
        )
    )
    señales = {
        s.key: s
        for s in normalize_snapshot(snapshot, **UMBRALES)  # default: solo "/"
        if s.signal_type is SignalType.DISK_FULL
    }
    assert set(señales) == {"disk:/"}
    assert señales["disk:/"].crossed is False


def test_mount_extra_vigilado_si_se_configura():
    # La otra mitad del mismo hallazgo: si el cliente agrega /boot a
    # puntos_montaje_vigilados, Modo 1 sí lo vigila (aunque Modo 2 --
    # fix_disco.sh -- siga acotado a "/", eso es una limitación aparte).
    snapshot = _snapshot(
        disks=(
            DiskUsage(source="/dev/sda1", usage_percent=3, target="/"),
            DiskUsage(source="/dev/sda16", usage_percent=97, target="/boot"),
        )
    )
    umbrales = dict(UMBRALES, monitored_mount_points=("/", "/boot"))
    señales = {
        s.key: s
        for s in normalize_snapshot(snapshot, **umbrales)
        if s.signal_type is SignalType.DISK_FULL
    }
    assert set(señales) == {"disk:/", "disk:/boot"}
    assert señales["disk:/boot"].crossed is True


# ----------------------------------------------------------------------- memoria


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


# ------------------------------------------------------------------------ puertos


def test_puerto_caido_cuando_no_esta_escuchando():
    snapshot = _snapshot(ports=(ListeningPort(address="0.0.0.0", port=22),))
    umbrales = dict(
        UMBRALES,
        monitored_ports=(
            MonitoredPort(port=22, service="sshd.service"),
            MonitoredPort(port=5432, service="postgresql.service"),
        ),
    )
    señales = {s.key: s for s in normalize_snapshot(snapshot, **umbrales)}
    assert señales["port:22:down"].crossed is False
    assert señales["port:5432:down"].crossed is True


def test_puerto_ocupado_por_otro_cuando_el_servicio_esperado_no_esta_activo():
    # Alguien escucha en :5432, pero postgresql.service está caído: no es
    # "sano" (port_down no cruza porque hay listener) ni es postgresql quien
    # lo tiene -- eso es port_occupied, no port_down.
    snapshot = _snapshot(
        ports=(ListeningPort(address="0.0.0.0", port=5432),),
        service_states=(ServiceState(name="postgresql.service", active=False),),
    )
    umbrales = dict(UMBRALES, monitored_ports=(MonitoredPort(port=5432, service="postgresql.service"),))
    señales = {s.key: s for s in normalize_snapshot(snapshot, **umbrales)}
    assert señales["port:5432:down"].crossed is False  # alguien escucha
    assert señales["port:5432:occupied"].crossed is True  # pero no es postgresql


def test_puerto_sano_cuando_el_servicio_esperado_esta_activo():
    snapshot = _snapshot(
        ports=(ListeningPort(address="0.0.0.0", port=5432),),
        service_states=(ServiceState(name="postgresql.service", active=True),),
    )
    umbrales = dict(UMBRALES, monitored_ports=(MonitoredPort(port=5432, service="postgresql.service"),))
    señales = {s.key: s for s in normalize_snapshot(snapshot, **umbrales)}
    assert señales["port:5432:down"].crossed is False
    assert señales["port:5432:occupied"].crossed is False


def test_puerto_ocupado_no_se_declara_sin_estado_del_servicio():
    # El puerto tiene listener, pero el servicio esperado no está en
    # service_states (no vigilado, o la consulta falló): sin esa base no se
    # declara ocupación indebida.
    snapshot = _snapshot(ports=(ListeningPort(address="0.0.0.0", port=5432),))
    umbrales = dict(UMBRALES, monitored_ports=(MonitoredPort(port=5432, service="postgresql.service"),))
    señales = {s.key: s for s in normalize_snapshot(snapshot, **umbrales)}
    assert señales["port:5432:occupied"].crossed is False


# ------------------------------------------------------------------------- carga


def test_carga_nunca_se_convierte_en_señal():
    señales = normalize_snapshot(_snapshot(), **UMBRALES)
    assert not [s for s in señales if s.signal_type is SignalType.HIGH_LOAD]
