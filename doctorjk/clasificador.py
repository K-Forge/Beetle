# Clasificador: mapea el tipo de incidente detectado al script de corrección
# de scripts-fix/ (tarea #200, plan-finalizacion-mvp.md Gate 4.1).
#
# El mapeo mezcla nombres en inglés (SignalType, ya fijado por la tarea #173)
# con los nombres históricos en español de la tarea #200 y con el nombre del
# script. Es la inconsistencia que documenta CONTEXTO-IA.md regla cero: las
# claves de estructuras ya fijadas en tareas anteriores se respetan tal como
# están, no se inventa una convención nueva ni se "arregla" por cuenta propia.
#
#   SignalType.DISK_FULL      -> disco_lleno       -> fix_disco.sh
#   SignalType.SERVICE_FAILED -> servicio_caido    -> fix_servicio.sh
#   SignalType.MEMORY_LOW     -> memoria_agotada   -> fix_memoria.sh
#   SignalType.PORT_OCCUPIED  -> puerto_ocupado    -> fix_puerto.sh
#
# SignalType.PORT_DOWN queda deliberadamente sin script: "nadie escucha en
# el puerto" no tiene todavía una corrección determinista segura (§4.1 del
# plan de finalización) -- reiniciar el servicio esperado a ciegas podría no
# ser la causa real, y el clasificador no improvisa una.
from __future__ import annotations

from doctorjk.modelos import SignalType

# SignalType -> nombre del script en scripts-fix/. Un tipo sin entrada acá no
# tiene corrección determinista: se diagnostica, nunca se corrige (Modo 1
# sigue funcionando igual; Modo 2 simplemente no actúa).
_SCRIPT_BY_SIGNAL_TYPE: dict[SignalType, str] = {
    SignalType.DISK_FULL: "fix_disco.sh",
    SignalType.SERVICE_FAILED: "fix_servicio.sh",
    SignalType.MEMORY_LOW: "fix_memoria.sh",
    SignalType.PORT_OCCUPIED: "fix_puerto.sh",
}


def classify(signal_type: SignalType) -> str | None:
    """Devuelve el nombre del script de corrección para `signal_type`, o
    `None` si no hay uno mapeado.

    Tarea #200: "un tipo sin script registra el caso y no ejecuta
    corrección" -- por eso esta función nunca lanza ni inventa un script por
    defecto; `remediador.py` decide qué hacer con `None`.
    """
    return _SCRIPT_BY_SIGNAL_TYPE.get(signal_type)
