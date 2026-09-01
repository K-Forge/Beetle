# Detector: máquina de estados de persistencia por clave de señal (tareas
# #174, #176, #177, #178; plan-mvp.md Gate B).
#
# Cada Signal.key vive su propio ciclo independiente:
#   normal -> candidato -> incidente -> resuelto -> normal
# Este módulo es el único que decide si una señal cruzada es un incidente
# real: no recolecta evidencia ni redacta nada (frontera dura,
# CONTEXTO-IA.md §3). El reloj se recibe como parámetro (`now` en evaluate())
# para que la duración de persistencia y de enfriamiento no dependan de
# time.sleep() en los tests.
#
# Decisión de diseño (no fijada por ningún documento, acordada explícitamente
# antes de implementar): un incidente resuelto entra en enfriamiento
# (cooldown_cycles ciclos sanos consecutivos) antes de considerarse
# "normal" otra vez. Mientras dura ese enfriamiento, una señal que vuelve a
# cruzar el umbral arranca un candidato nuevo de inmediato -- igual que si
# viniera de "normal" -- porque la deduplicación (tarea #177) solo bloquea
# mientras el incidente anterior sigue activo (estado "incidente"), no
# mientras se está enfriando.
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Mapping
from uuid import uuid4

from doctorjk.modelos import Incident, IncidentState, Signal, SignalType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Transition:
    """Un cambio de estado real para una clave, en un ciclo de evaluación.

    candidato->normal y enfriamiento->normal no traen `incident`: todavía no
    hay (o ya no hay) un incidente que el resto del pipeline deba atender.
    """

    key: str
    signal_type: SignalType
    previous_state: IncidentState
    new_state: IncidentState
    reason: str
    incident: Incident | None


@dataclass
class _KeyState:
    """Contador y estado por clave. Mutable e interno: `Detector` es dueño
    de esta estructura, ningún otro módulo la lee ni la escribe."""

    state: IncidentState = IncidentState.NORMAL
    # Ciclos consecutivos cruzados (mientras es candidato) o sanos (mientras
    # es incidente o está en enfriamiento). Se reinterpreta según el estado.
    consecutive_count: int = 0
    incident_id: str | None = None
    started_at: datetime | None = None
    confirmed_at: datetime | None = None


class Detector:
    """Máquina de estados con persistencia, una instancia por clave de señal.

    `persistence_cycles` es un mapeo SignalType -> ciclos, no un único número
    global (plan-finalizacion-mvp.md Gate 1.3, defecto 5): un servicio caído
    y un puerto ocupado no deberían confirmarse con la misma cantidad de
    ciclos, porque `servicio_ciclos` y `puerto_timeout_s` son parámetros
    independientes en config.toml. Cada tipo de señal que el detector reciba
    en evaluate() debe estar en el mapeo -- fail fast, no hay valor por
    defecto implícito que pueda esconder un tipo sin configurar.
    """

    def __init__(self, persistence_cycles: Mapping[SignalType, int], cooldown_cycles: int) -> None:
        if not persistence_cycles:
            raise ValueError("persistence_cycles no puede estar vacío")
        for signal_type, cycles in persistence_cycles.items():
            if cycles <= 0:
                raise ValueError(
                    f"persistence_cycles[{signal_type.value}] debe ser mayor que 0, se recibió {cycles!r}"
                )
        if cooldown_cycles <= 0:
            raise ValueError("cooldown_cycles debe ser mayor que 0")
        self._persistence_cycles = dict(persistence_cycles)
        self._cooldown_cycles = cooldown_cycles
        self._keys: dict[str, _KeyState] = {}

    def _persistence_for(self, signal_type: SignalType) -> int:
        try:
            return self._persistence_cycles[signal_type]
        except KeyError:
            raise ValueError(
                f"no hay ciclos de persistencia configurados para el tipo de señal "
                f"{signal_type.value!r}"
            ) from None

    def evaluate(self, signals: Iterable[Signal], now: datetime) -> tuple[Transition, ...]:
        """Procesa un ciclo de señales y devuelve solo las transiciones que
        cambiaron de estado (una clave ausente este ciclo no se toca: ni
        avanza ni se reinicia su contador, porque no es una lectura sana ni
        cruzada, es una falla de adquisición -- monitor.py ya la excluyó)."""
        transitions: list[Transition] = []
        for signal in signals:
            key_state = self._keys.setdefault(signal.key, _KeyState())
            transition = self._evaluate_one(signal, key_state, now)
            if transition is not None:
                transitions.append(transition)
        return tuple(transitions)

    def _evaluate_one(
        self, signal: Signal, key_state: _KeyState, now: datetime
    ) -> Transition | None:
        if key_state.state in (IncidentState.NORMAL, IncidentState.RESOLVED):
            transition = self._from_normal_or_resolved(signal, key_state, now)
        elif key_state.state is IncidentState.CANDIDATE:
            transition = self._from_candidate(signal, key_state, now)
        else:
            transition = self._from_incident(signal, key_state, now)

        # Registro de decisión por ciclo (#178): señal, contador y estado
        # resultante, sin evidencia extensa ni valores sensibles.
        logger.debug(
            "clave=%s tipo=%s cruzado=%s contador=%d estado=%s",
            signal.key,
            signal.signal_type.value,
            signal.crossed,
            key_state.consecutive_count,
            key_state.state.value,
        )
        if transition is not None:
            logger.info(
                "clave=%s %s -> %s: %s",
                signal.key,
                transition.previous_state.value,
                transition.new_state.value,
                transition.reason,
            )
        return transition

    def _from_normal_or_resolved(
        self, signal: Signal, key_state: _KeyState, now: datetime
    ) -> Transition | None:
        if not signal.crossed:
            if key_state.state is not IncidentState.RESOLVED:
                return None  # normal y sana: nada que hacer

            # En enfriamiento: un ciclo sano más hacia "normal".
            key_state.consecutive_count += 1
            if key_state.consecutive_count < self._cooldown_cycles:
                return None

            previous = key_state.state
            key_state.state = IncidentState.NORMAL
            key_state.consecutive_count = 0
            key_state.incident_id = None
            key_state.started_at = None
            key_state.confirmed_at = None
            return Transition(
                key=signal.key,
                signal_type=signal.signal_type,
                previous_state=previous,
                new_state=IncidentState.NORMAL,
                reason=(
                    f"se mantuvo sana {self._cooldown_cycles} ciclos tras resolverse, "
                    "enfriamiento completo"
                ),
                incident=None,
            )

        # Cruzada desde normal o desde en pleno enfriamiento: arranca un
        # candidato nuevo (tarea #177: dedup solo bloquea mientras el
        # incidente anterior sigue activo, no durante el enfriamiento).
        # Se valida acá, en el primer cruce, que el tipo tenga ciclos
        # configurados -- fail fast, no esperar al segundo ciclo para
        # descubrir que falta el mapeo (CONTEXTO-IA.md §8.1).
        self._persistence_for(signal.signal_type)
        previous = key_state.state
        key_state.state = IncidentState.CANDIDATE
        key_state.consecutive_count = 1
        key_state.started_at = now
        key_state.incident_id = None
        key_state.confirmed_at = None
        return Transition(
            key=signal.key,
            signal_type=signal.signal_type,
            previous_state=previous,
            new_state=IncidentState.CANDIDATE,
            reason=f"cruzó el umbral (valor={signal.value}, umbral={signal.threshold})",
            incident=None,
        )

    def _from_candidate(
        self, signal: Signal, key_state: _KeyState, now: datetime
    ) -> Transition | None:
        if not signal.crossed:
            # Pico temporal: no llegó a los N ciclos, se descarta sin dejar rastro.
            key_state.state = IncidentState.NORMAL
            key_state.consecutive_count = 0
            key_state.started_at = None
            return Transition(
                key=signal.key,
                signal_type=signal.signal_type,
                previous_state=IncidentState.CANDIDATE,
                new_state=IncidentState.NORMAL,
                reason="volvió a la normalidad antes de confirmarse: pico temporal descartado",
                incident=None,
            )

        required_cycles = self._persistence_for(signal.signal_type)
        key_state.consecutive_count += 1
        if key_state.consecutive_count < required_cycles:
            return None  # sigue siendo candidato, todavía no alcanza N

        key_state.state = IncidentState.INCIDENT
        key_state.consecutive_count = 0  # ahora cuenta ciclos sanos hacia la resolución
        key_state.incident_id = uuid4().hex
        key_state.confirmed_at = now
        incident = Incident(
            incident_id=key_state.incident_id,
            signal_type=signal.signal_type,
            resource_key=signal.key,
            started_at=key_state.started_at or now,
            confirmed_at=now,
            state=IncidentState.INCIDENT,
        )
        return Transition(
            key=signal.key,
            signal_type=signal.signal_type,
            previous_state=IncidentState.CANDIDATE,
            new_state=IncidentState.INCIDENT,
            reason=f"persistió {required_cycles} ciclos consecutivos, se confirma incidente",
            incident=incident,
        )

    def _from_incident(
        self, signal: Signal, key_state: _KeyState, now: datetime
    ) -> Transition | None:
        if signal.crossed:
            # Sigue activo: se suprime el re-disparo (tarea #177). El
            # contador de sanidad, si había empezado, se reinicia.
            key_state.consecutive_count = 0
            return None

        required_cycles = self._persistence_for(signal.signal_type)
        key_state.consecutive_count += 1
        if key_state.consecutive_count < required_cycles:
            return None  # sano, pero todavía no alcanza N para resolver

        key_state.state = IncidentState.RESOLVED
        key_state.consecutive_count = 0  # ahora cuenta ciclos de enfriamiento
        resolved_incident = Incident(
            incident_id=key_state.incident_id or "",
            signal_type=signal.signal_type,
            resource_key=signal.key,
            started_at=key_state.started_at or now,
            confirmed_at=key_state.confirmed_at,
            state=IncidentState.RESOLVED,
        )
        return Transition(
            key=signal.key,
            signal_type=signal.signal_type,
            previous_state=IncidentState.INCIDENT,
            new_state=IncidentState.RESOLVED,
            reason=f"se normalizó durante {required_cycles} ciclos consecutivos, incidente resuelto",
            incident=resolved_incident,
        )
