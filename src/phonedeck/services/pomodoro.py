"""Servicio del Pomodoro: encadena los periodos y avisa en la PC y en el celular."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from phonedeck.pomodoro import Phase, Transition

if TYPE_CHECKING:
    from phonedeck.state import AppState

log = logging.getLogger(__name__)

NOTIFICATION_TITLE = "Pomodoro"
NEXT_PERIOD = {
    Phase.WORK: "Se acabó el descanso: a trabajar",
    Phase.SHORT_BREAK: "Periodo terminado: toca un descanso corto",
    Phase.LONG_BREAK: "Ciclo completado: toca un descanso largo",
}


async def publish(state: AppState) -> None:
    """Envía el estado a quien mira la sección. No se guarda copia: el tiempo caduca."""
    await state.hub.broadcast("pomodoro", state.pomodoro.payload(), cache=False)


async def announce(state: AppState, transition: Transition) -> None:
    """Avisa del cambio de periodo.

    ``pomodoro.alert`` no es un tema filtrable: llega a todos los celulares, estén en la
    página que estén.
    """
    message = NEXT_PERIOD[transition.started]
    await publish(state)
    await state.hub.broadcast(
        "pomodoro.alert",
        {"finished": transition.finished.value, "started": transition.started.value,
         "message": message},
        cache=False,
    )  # fmt: skip
    if state.notifier is not None:
        try:
            await asyncio.to_thread(state.notifier, message, NOTIFICATION_TITLE)
        except Exception:
            log.exception("No se pudo mostrar la notificación del Pomodoro")


async def pomodoro_service(state: AppState) -> None:
    timer = state.pomodoro
    while True:
        await timer.wait_for_change()
        try:
            transition = timer.expire()
            if transition is None:
                continue
            if state.config_store.config.has_widget("pomodoro"):
                await announce(state, transition)
            else:
                # Sin el widget ya nadie podría pararlo: no se encadena otro periodo.
                timer.stop()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Error en el Pomodoro")
