"""Temporizador Pomodoro. Vive en la PC: el celular solo lo muestra y le envía órdenes.

Así sobrevive a recargas de la página y a la pantalla apagada (Android frena los
temporizadores en segundo plano), y varios celulares ven siempre lo mismo.

No hay ningún bucle de sondeo: el servicio duerme hasta el instante en que termina el periodo
(ver ``phonedeck.services.pomodoro``). Las duraciones se guardan en ``pomodoro.json`` y no en
``config.json``, porque por WiFi la edición de ``config.json`` está desactivada por defecto.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from phonedeck.fileutil import atomic_write_text

log = logging.getLogger(__name__)

CYCLE_LENGTH = 4  # periodos de trabajo antes del descanso largo
MAX_MINUTES = 180


class Phase(StrEnum):
    WORK = "work"
    SHORT_BREAK = "short_break"
    LONG_BREAK = "long_break"


class Status(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"


class Durations(BaseModel):
    """Duración de cada periodo, en minutos."""

    model_config = ConfigDict(extra="ignore")

    work: int = Field(default=25, ge=1, le=MAX_MINUTES)
    short_break: int = Field(default=5, ge=1, le=MAX_MINUTES)
    long_break: int = Field(default=15, ge=1, le=MAX_MINUTES)

    def seconds(self, phase: Phase) -> float:
        minutes: int = getattr(self, phase.value)
        return minutes * 60.0


@dataclass(frozen=True, slots=True)
class Transition:
    """Un periodo terminó y empezó el siguiente."""

    finished: Phase
    started: Phase


class PomodoroTimer:
    def __init__(self, path: Path, clock: Callable[[], float] = time.monotonic) -> None:
        self.path = path
        self._clock = clock
        self.durations = self._load()
        self.phase = Phase.WORK
        self.status = Status.IDLE
        self.completed = 0  # periodos de trabajo terminados en este ciclo
        self._period_s = self.durations.seconds(Phase.WORK)
        self._remaining_s = self._period_s  # vale cuando no está en marcha
        self._ends_at = 0.0  # vale cuando está en marcha
        self._changed = asyncio.Event()

    # -------------------------------------------------------------- persistencia
    def _load(self) -> Durations:
        try:
            return Durations.model_validate(json.loads(self.path.read_text(encoding="utf-8")))
        except FileNotFoundError:
            return Durations()
        except (OSError, ValueError, ValidationError) as exc:
            log.warning("%s inválido (%s): se usan las duraciones por defecto", self.path.name, exc)
            return Durations()

    # ---------------------------------------------------------------- consultas
    def remaining(self) -> float:
        if self.status is Status.RUNNING:
            return max(0.0, self._ends_at - self._clock())
        return self._remaining_s

    def seconds_until_due(self) -> float | None:
        """Cuánto dormir hasta que termine el periodo; ``None`` si no hay nada en marcha."""
        return self.remaining() if self.status is Status.RUNNING else None

    def payload(self) -> dict[str, Any]:
        """Estado para el celular. Lleva el tiempo restante y no la hora de fin, porque los
        relojes de la PC y del celular pueden diferir."""
        return {
            "phase": self.phase.value,
            "status": self.status.value,
            "remaining_ms": round(self.remaining() * 1000),
            "period_ms": round(self._period_s * 1000),
            "completed": self.completed,
            "cycle_length": CYCLE_LENGTH,
            "durations": self.durations.model_dump(),
        }

    # ------------------------------------------------------------------ órdenes
    def _begin(self, phase: Phase, status: Status) -> None:
        self.phase = phase
        self.status = status
        self._period_s = self.durations.seconds(phase)
        self._remaining_s = self._period_s
        self._ends_at = self._clock() + self._period_s

    def start(self) -> None:
        if self.status is Status.IDLE:
            self._begin(self.phase, Status.RUNNING)
            self._changed.set()

    def pause(self) -> None:
        if self.status is Status.RUNNING:
            self._remaining_s = self.remaining()
            self.status = Status.PAUSED
            self._changed.set()

    def resume(self) -> None:
        if self.status is Status.PAUSED:
            self._ends_at = self._clock() + self._remaining_s
            self.status = Status.RUNNING
            self._changed.set()

    def reset(self) -> None:
        """Vuelve al inicio del periodo; si ya estaba ahí, al inicio del ciclo completo."""
        if self.status is Status.IDLE:
            self.stop()
        else:
            self._begin(self.phase, Status.IDLE)
            self._changed.set()

    def stop(self) -> None:
        """Deja el temporizador como recién abierto."""
        self.completed = 0
        self._begin(Phase.WORK, Status.IDLE)
        self._changed.set()

    def configure(self, durations: Durations) -> None:
        """Guarda las duraciones. Un periodo ya empezado conserva la suya hasta terminar."""
        text = json.dumps(durations.model_dump(), indent=2) + "\n"
        atomic_write_text(self.path, text)
        self.durations = durations
        if self.status is Status.IDLE:
            self._begin(self.phase, Status.IDLE)

    def expire(self) -> Transition | None:
        """Si el periodo terminó, pasa al siguiente y lo arranca."""
        if self.status is not Status.RUNNING or self.remaining() > 0:
            return None
        finished = self.phase
        if finished is Phase.WORK:
            self.completed += 1
            started = Phase.LONG_BREAK if self.completed >= CYCLE_LENGTH else Phase.SHORT_BREAK
        else:
            started = Phase.WORK
            if finished is Phase.LONG_BREAK:
                self.completed = 0
        self._begin(started, Status.RUNNING)
        return Transition(finished, started)

    async def wait_for_change(self) -> None:
        """Duerme hasta que termine el periodo o llegue una orden."""
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(self.seconds_until_due()):
                await self._changed.wait()
        self._changed.clear()
