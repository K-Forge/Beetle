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
from typing import Iterable
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
class _EstadoClave:
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
    """Máquina de estados con persistencia, una instancia por clave de señal."""

    def __init__(self, persistence_cycles: int, cooldown_cycles: int) -> None:
        if persistence_cycles <= 0:
            raise ValueError("persistence_cycles debe ser mayor que 0")
        if cooldown_cycles <= 0:
            raise ValueError("cooldown_cycles debe ser mayor que 0")
        self._persistence_cycles = persistence_cycles
        self._cooldown_cycles = cooldown_cycles
        self._claves: dict[str, _EstadoClave] = {}

    def evaluate(self, signals: Iterable[Signal], now: datetime) -> tuple[Transition, ...]:
        """Procesa un ciclo de señales y devuelve solo las transiciones que
        cambiaron de estado (una clave ausente este ciclo no se toca: ni
        avanza ni se reinicia su contador, porque no es una lectura sana ni
        cruzada, es una falla de adquisición -- monitor.py ya la excluyó)."""
        transiciones: list[Transition] = []
        for signal in signals:
            estado_clave = self._claves.setdefault(signal.key, _EstadoClave())
            transicion = self._evaluar_una(signal, estado_clave, now)
            if transicion is not None:
                transiciones.append(transicion)
        return tuple(transiciones)

    def _evaluar_una(
        self, signal: Signal, estado_clave: _EstadoClave, now: datetime
    ) -> Transition | None:
        if estado_clave.state in (IncidentState.NORMAL, IncidentState.RESOLVED):
            transicion = self._desde_normal_o_resuelto(signal, estado_clave, now)
        elif estado_clave.state is IncidentState.CANDIDATE:
            transicion = self._desde_candidato(signal, estado_clave, now)
        else:
            transicion = self._desde_incidente(signal, estado_clave, now)

        # Registro de decisión por ciclo (#178): señal, contador y estado
        # resultante, sin evidencia extensa ni valores sensibles.
        logger.debug(
            "clave=%s tipo=%s cruzado=%s contador=%d estado=%s",
            signal.key,
            signal.signal_type.value,
            signal.crossed,
            estado_clave.consecutive_count,
            estado_clave.state.value,
        )
        if transicion is not None:
            logger.info(
                "clave=%s %s -> %s: %s",
                signal.key,
                transicion.previous_state.value,
                transicion.new_state.value,
                transicion.reason,
            )
        return transicion

    def _desde_normal_o_resuelto(
        self, signal: Signal, estado_clave: _EstadoClave, now: datetime
    ) -> Transition | None:
        if not signal.crossed:
            if estado_clave.state is not IncidentState.RESOLVED:
                return None  # normal y sana: nada que hacer

            # En enfriamiento: un ciclo sano más hacia "normal".
            estado_clave.consecutive_count += 1
            if estado_clave.consecutive_count < self._cooldown_cycles:
                return None

            anterior = estado_clave.state
            estado_clave.state = IncidentState.NORMAL
            estado_clave.consecutive_count = 0
            estado_clave.incident_id = None
            estado_clave.started_at = None
            estado_clave.confirmed_at = None
            return Transition(
                key=signal.key,
                signal_type=signal.signal_type,
                previous_state=anterior,
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
        anterior = estado_clave.state
        estado_clave.state = IncidentState.CANDIDATE
        estado_clave.consecutive_count = 1
        estado_clave.started_at = now
        estado_clave.incident_id = None
        estado_clave.confirmed_at = None
        return Transition(
            key=signal.key,
            signal_type=signal.signal_type,
            previous_state=anterior,
            new_state=IncidentState.CANDIDATE,
            reason=f"cruzó el umbral (valor={signal.value}, umbral={signal.threshold})",
            incident=None,
        )

    def _desde_candidato(
        self, signal: Signal, estado_clave: _EstadoClave, now: datetime
    ) -> Transition | None:
        if not signal.crossed:
            # Pico temporal: no llegó a los N ciclos, se descarta sin dejar rastro.
            estado_clave.state = IncidentState.NORMAL
            estado_clave.consecutive_count = 0
            estado_clave.started_at = None
            return Transition(
                key=signal.key,
                signal_type=signal.signal_type,
                previous_state=IncidentState.CANDIDATE,
                new_state=IncidentState.NORMAL,
                reason="volvió a la normalidad antes de confirmarse: pico temporal descartado",
                incident=None,
            )

        estado_clave.consecutive_count += 1
        if estado_clave.consecutive_count < self._persistence_cycles:
            return None  # sigue siendo candidato, todavía no alcanza N

        estado_clave.state = IncidentState.INCIDENT
        estado_clave.consecutive_count = 0  # ahora cuenta ciclos sanos hacia la resolución
        estado_clave.incident_id = uuid4().hex
        estado_clave.confirmed_at = now
        incidente = Incident(
            incident_id=estado_clave.incident_id,
            signal_type=signal.signal_type,
            resource_key=signal.key,
            started_at=estado_clave.started_at or now,
            confirmed_at=now,
            state=IncidentState.INCIDENT,
        )
        return Transition(
            key=signal.key,
            signal_type=signal.signal_type,
            previous_state=IncidentState.CANDIDATE,
            new_state=IncidentState.INCIDENT,
            reason=f"persistió {self._persistence_cycles} ciclos consecutivos, se confirma incidente",
            incident=incidente,
        )

    def _desde_incidente(
        self, signal: Signal, estado_clave: _EstadoClave, now: datetime
    ) -> Transition | None:
        if signal.crossed:
            # Sigue activo: se suprime el re-disparo (tarea #177). El
            # contador de sanidad, si había empezado, se reinicia.
            estado_clave.consecutive_count = 0
            return None

        estado_clave.consecutive_count += 1
        if estado_clave.consecutive_count < self._persistence_cycles:
            return None  # sano, pero todavía no alcanza N para resolver

        estado_clave.state = IncidentState.RESOLVED
        estado_clave.consecutive_count = 0  # ahora cuenta ciclos de enfriamiento
        incidente_resuelto = Incident(
            incident_id=estado_clave.incident_id or "",
            signal_type=signal.signal_type,
            resource_key=signal.key,
            started_at=estado_clave.started_at or now,
            confirmed_at=estado_clave.confirmed_at,
            state=IncidentState.RESOLVED,
        )
        return Transition(
            key=signal.key,
            signal_type=signal.signal_type,
            previous_state=IncidentState.INCIDENT,
            new_state=IncidentState.RESOLVED,
            reason=f"se normalizó durante {self._persistence_cycles} ciclos consecutivos, incidente resuelto",
            incident=incidente_resuelto,
        )
