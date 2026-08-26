# Contratos de datos compartidos entre etapas del pipeline (monitor, detector,
# recolector...). Son dataclasses inmutables y sin lógica de negocio: cada
# módulo los recibe y los devuelve, nunca lee atributos internos de otro
# componente (frontera dura, CONTEXTO-IA.md §3 y plan-mvp.md §3.2).
#
# Este archivo crece por bloque del plan MVP. Hoy solo trae lo que el monitor
# y el orquestador (Gate A) ya usan: SystemSnapshot, sus piezas y Signal.
# Incident, CorrectionStep, CorrectionPlan y ExecutionResult se agregan cuando
# el detector y el remediador (Gates B y H) los necesiten de verdad.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


@dataclass(frozen=True)
class FailedService:
    name: str


@dataclass(frozen=True)
class DiskUsage:
    source: str
    usage_percent: int
    target: str


@dataclass(frozen=True)
class MemoryUsage:
    total_mb: int
    used_mb: int
    free_mb: int
    available_mb: int


@dataclass(frozen=True)
class ListeningPort:
    address: str
    port: int


@dataclass(frozen=True)
class LoadAverage:
    load_1m: float
    load_5m: float
    load_15m: float


@dataclass(frozen=True)
class SystemSnapshot:
    """Una lectura del estado del servidor en un instante dado.

    Cada categoría trae su propio flag `*_available`: si el comando de origen
    falló (ausente, timeout, código distinto de 0), la categoría queda vacía
    y el flag en False. Eso es una falla de adquisición, no un valor sano;
    normalize_snapshot() en monitor.py no debe emitir una señal sana para
    disfrazarla.
    """

    captured_at: datetime
    failed_services: tuple[FailedService, ...]
    services_available: bool
    disks: tuple[DiskUsage, ...]
    disk_available: bool
    memory: MemoryUsage | None
    memory_available: bool
    ports: tuple[ListeningPort, ...]
    ports_available: bool
    load: LoadAverage | None
    load_available: bool


class SignalType(str, Enum):
    """Nombres fijados por la tarea #173; no se inventan variantes nuevas."""

    SERVICE_FAILED = "service_failed"
    DISK_FULL = "disk_full"
    MEMORY_LOW = "memory_low"
    PORT_DOWN = "port_down"
    # HIGH_LOAD está declarado porque la tarea #173 ya fija el nombre, pero
    # normalize_snapshot() todavía no lo emite: plan-mvp.md bloque A4 deja la
    # carga como informativa hasta que exista un criterio de incidente
    # aprobado para ella.
    HIGH_LOAD = "high_load"


@dataclass(frozen=True)
class Signal:
    """Formato único al que se convierte toda señal, sin importar su origen."""

    timestamp: datetime
    signal_type: SignalType
    value: str
    threshold: str
    crossed: bool
    key: str


@dataclass(frozen=True)
class TriggerEvent:
    """Evento local emitido por trigger.sh. El mensaje del journal que lo
    disparó no viaja acá adentro a propósito (plan-mvp.md §3.1, punto 3): si
    hace falta, el orquestador lo recupera del journal, no del trigger."""

    occurred_at: datetime
    source: str


class IncidentState(str, Enum):
    """Ciclo de vida de un incidente por clave de señal (tarea #176).

    normal -> candidato -> incidente -> resuelto -> normal. `detector.py`
    (Gate B) es el único que decide estas transiciones.
    """

    NORMAL = "normal"
    CANDIDATE = "candidate"
    INCIDENT = "incident"
    RESOLVED = "resolved"


@dataclass(frozen=True)
class Incident:
    """Un incidente confirmado (o ya resuelto) para una clave de señal."""

    incident_id: str
    signal_type: SignalType
    resource_key: str
    started_at: datetime
    confirmed_at: datetime | None
    state: IncidentState


@dataclass(frozen=True)
class Evidence:
    """Evidencia ensamblada para un incidente confirmado (tareas #179-181).

    Cada sección de texto puede quedar vacía o parcial si su recolección
    falló; en ese caso el motivo queda en `partial_errors`, nunca se descarta
    la evidencia completa por la falla de una sola sección (plan-mvp.md
    bloque C1: "evidencia parcial sigue siendo utilizable").
    """

    incident: Incident
    generated_at: datetime
    metadata_text: str
    logs_text: str
    snapshot_text: str
    changes_text: str
    history_text: str
    raw_text: str
    partial_errors: tuple[str, ...]
