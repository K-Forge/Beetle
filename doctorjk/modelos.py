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
class ServiceState:
    """Estado consultado explícitamente para un servicio de `servicios_vigilados`
    (plan-finalizacion-mvp.md Gate 1.3, defecto 1). A diferencia de
    `FailedService` -- que solo lista lo que ya está fallido -- este tipo
    también trae los servicios sanos, porque sin ellos el detector no puede
    distinguir "se recuperó" de "nunca se consultó"."""

    name: str
    active: bool


@dataclass(frozen=True)
class MonitoredPort:
    """Puerto vigilado y el servicio que se espera que lo posea (tarea #175,
    clave `puertos_vigilados`). El servicio esperado es lo que permite
    distinguir `port_down` (nadie escucha) de `port_occupied` (alguien
    escucha, pero no es el servicio dueño)."""

    port: int
    service: str


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
    # Estado de los servicios explícitamente vigilados (config.py,
    # `servicios_vigilados`), consultado aparte de `failed_services` porque
    # `systemctl --failed` nunca informa de un servicio sano (defecto 1).
    # Vacío y disponible=True cuando no hay nada vigilado: no es una falla de
    # adquisición, es que no se pidió nada.
    service_states: tuple[ServiceState, ...] = ()
    service_states_available: bool = True


class SignalType(str, Enum):
    """Nombres fijados por la tarea #173; no se inventan variantes nuevas."""

    SERVICE_FAILED = "service_failed"
    DISK_FULL = "disk_full"
    MEMORY_LOW = "memory_low"
    PORT_DOWN = "port_down"
    # PORT_OCCUPIED no estaba en la tarea #173: se agrega en
    # plan-finalizacion-mvp.md Gate 1.3 (defecto 6) porque port_down no puede
    # representar "el puerto esperado está tomado por otro proceso mientras
    # el servicio dueño no está activo" sin mentir sobre su semántica
    # original. El nombre va en inglés (regla cero); el mapeo hacia
    # `puerto_ocupado` en clasificador.py (Gate 4) documenta la
    # inconsistencia histórica con la tarea #200, no la resuelve por
    # renombrado silencioso.
    PORT_OCCUPIED = "port_occupied"
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
class SanitizedEvidence:
    """Evidencia que YA pasó por el sanitizador y puede salir del servidor.

    Existe como tipo propio, y no como un `str` cualquiera, para que la
    frontera de privacidad sea imposible de saltar por descuido: `llm.py`
    acepta únicamente este contrato, así que no hay forma de pasarle
    `Evidence.raw_text` sin que salte en revisión o en el type checker.
    Solo `sanitizador.sanitize_evidence()` la construye.
    """

    incident_id: str
    generated_at: datetime
    text: str
    partial_errors: tuple[str, ...]


@dataclass(frozen=True)
class Diagnosis:
    """Resultado del diagnóstico, venga del modelo o del fallback local."""

    incident_id: str
    text: str
    model: str
    from_fallback: bool


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


class RemediationOutcome(str, Enum):
    """Resultado de intentar corregir un incidente en Modo 2 (tareas #201, #202).

    `remediador.py` es el único que decide este valor; ni el script bash ni
    el clasificador lo asignan. NOT_MAPPED y NOT_ENABLED no ejecutan ningún
    comando -- se distinguen de FAILED porque ninguno es un intento fallido,
    es que el intento nunca correspondía.
    """

    RESOLVED = "resolved"  # el script corrió y su propia verificación pasó
    FAILED = "failed"  # el script corrió pero no verificó resuelto: escalar
    NOT_MAPPED = "not_mapped"  # el tipo de incidente no tiene script (#200)
    NOT_ENABLED = "not_enabled"  # modo_remediacion != "scripts"


@dataclass(frozen=True)
class RemediationResult:
    """Bitácora de auditoría de un intento de corrección Modo 2 (tarea #201).

    Todo lo que un administrador necesita para reconstruir qué se ejecutó,
    cuándo, y qué devolvió -- stdout/stderr ya vienen sanitizados por quien
    construye este resultado, nunca crudos (CONTEXTO-IA.md §8.5).
    """

    incident_id: str
    signal_type: SignalType
    script: str | None
    argv: tuple[str, ...]
    started_at: datetime
    finished_at: datetime
    exit_code: int | None
    stdout: str
    stderr: str
    outcome: RemediationOutcome
