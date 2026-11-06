"""Pomodoro: secuencia de periodos, pausa, reinicio, persistencia y comandos en vivo."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from phonedeck.pomodoro import CYCLE_LENGTH, Durations, Phase, PomodoroTimer, Status, Transition
from phonedeck.services.pomodoro import announce, pomodoro_service
from phonedeck.state import AppState
from tests.conftest import auth, local_token
from tests.test_live import WS_URL, receive_until
from tests.test_services import spy_broadcasts


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def timer(tmp_path: Path, clock: Clock) -> PomodoroTimer:
    return PomodoroTimer(tmp_path / "pomodoro.json", clock)


def finish_period(timer: PomodoroTimer, clock: Clock) -> Transition:
    clock.now += timer.remaining()
    transition = timer.expire()
    assert transition is not None
    return transition


def test_starts_idle_with_default_durations(timer: PomodoroTimer) -> None:
    data = timer.payload()
    assert (data["phase"], data["status"], data["completed"]) == ("work", "idle", 0)
    assert data["remaining_ms"] == data["period_ms"] == 25 * 60 * 1000
    assert data["durations"] == {"work": 25, "short_break": 5, "long_break": 15}


def test_countdown_and_nothing_due_while_idle(timer: PomodoroTimer, clock: Clock) -> None:
    assert timer.seconds_until_due() is None
    timer.start()
    clock.now += 60
    assert timer.seconds_until_due() == 24 * 60
    assert timer.expire() is None


def test_pause_freezes_time_and_resume_continues(timer: PomodoroTimer, clock: Clock) -> None:
    timer.start()
    clock.now += 100
    timer.pause()
    clock.now += 5000
    assert timer.status is Status.PAUSED
    assert timer.remaining() == 25 * 60 - 100
    assert timer.seconds_until_due() is None
    assert timer.expire() is None

    timer.resume()
    assert timer.remaining() == 25 * 60 - 100
    clock.now += 25 * 60 - 100
    assert timer.expire() == Transition(Phase.WORK, Phase.SHORT_BREAK)


def test_full_cycle_sequence(timer: PomodoroTimer, clock: Clock) -> None:
    timer.start()
    sequence = [finish_period(timer, clock).started for _ in range(2 * CYCLE_LENGTH)]
    assert sequence == [
        Phase.SHORT_BREAK,
        Phase.WORK,
        Phase.SHORT_BREAK,
        Phase.WORK,
        Phase.SHORT_BREAK,
        Phase.WORK,
        Phase.LONG_BREAK,
        Phase.WORK,
    ]
    assert timer.completed == 0  # el descanso largo cierra el ciclo
    assert timer.status is Status.RUNNING  # sigue solo


def test_completed_counts_work_periods(timer: PomodoroTimer, clock: Clock) -> None:
    timer.start()
    finish_period(timer, clock)
    assert timer.completed == 1
    finish_period(timer, clock)
    assert timer.completed == 1


def test_next_period_uses_its_own_duration(timer: PomodoroTimer, clock: Clock) -> None:
    timer.start()
    finish_period(timer, clock)
    assert timer.remaining() == 5 * 60
    assert timer.payload()["period_ms"] == 5 * 60 * 1000


def test_late_wakeup_starts_next_period_from_now(timer: PomodoroTimer, clock: Clock) -> None:
    """Si la PC estuvo suspendida, el siguiente periodo no se pierde."""
    timer.start()
    clock.now += 10 * 3600
    assert timer.expire() == Transition(Phase.WORK, Phase.SHORT_BREAK)
    assert timer.remaining() == 5 * 60


def test_reset_restarts_period_then_cycle(timer: PomodoroTimer, clock: Clock) -> None:
    timer.start()
    finish_period(timer, clock)  # ahora en descanso corto, 1 completado
    clock.now += 30

    timer.reset()
    assert (timer.phase, timer.status, timer.completed) == (Phase.SHORT_BREAK, Status.IDLE, 1)
    assert timer.remaining() == 5 * 60

    timer.reset()  # ya estaba al inicio: se reinicia todo el ciclo
    assert (timer.phase, timer.status, timer.completed) == (Phase.WORK, Status.IDLE, 0)


def test_orders_out_of_place_are_ignored(timer: PomodoroTimer, clock: Clock) -> None:
    timer.pause()
    timer.resume()
    assert timer.status is Status.IDLE
    timer.start()
    clock.now += 10
    timer.start()  # no reinicia un periodo en marcha
    assert timer.remaining() == 25 * 60 - 10


def test_durations_persist(tmp_path: Path, timer: PomodoroTimer) -> None:
    timer.configure(Durations(work=50, short_break=10, long_break=30))
    assert timer.remaining() == 50 * 60  # en reposo se ve al momento

    reloaded = PomodoroTimer(tmp_path / "pomodoro.json")
    assert reloaded.durations == Durations(work=50, short_break=10, long_break=30)
    assert reloaded.remaining() == 50 * 60


def test_new_durations_wait_for_next_period(timer: PomodoroTimer, clock: Clock) -> None:
    timer.start()
    clock.now += 60
    timer.configure(Durations(work=50, short_break=10, long_break=30))
    assert timer.remaining() == 24 * 60
    finish_period(timer, clock)
    assert timer.remaining() == 10 * 60


@pytest.mark.parametrize("content", ["no es json", '{"work": 0}', '{"work": "x"}'])
def test_corrupt_file_falls_back_to_defaults(tmp_path: Path, content: str) -> None:
    path = tmp_path / "pomodoro.json"
    path.write_text(content, encoding="utf-8")
    assert PomodoroTimer(path).durations == Durations()


async def test_service_wakes_exactly_at_the_end(state: AppState) -> None:
    state.pomodoro.durations = Durations(work=1)
    state.pomodoro.reset()
    state.pomodoro._begin(Phase.WORK, Status.RUNNING)
    state.pomodoro._ends_at = state.pomodoro._clock() + 0.05
    sent = spy_broadcasts(state)
    task = asyncio.create_task(pomodoro_service(state))
    await asyncio.sleep(0.2)
    task.cancel()
    assert state.pomodoro.phase is Phase.SHORT_BREAK
    assert [t for t, _ in sent] == ["pomodoro", "pomodoro.alert"]


async def test_announce_notifies_windows_and_survives_failure(state: AppState) -> None:
    shown: list[tuple[str, str]] = []
    state.notifier = lambda message, title: shown.append((message, title))
    await announce(state, Transition(Phase.WORK, Phase.LONG_BREAK))
    assert shown == [("Ciclo completado: toca un descanso largo", "Pomodoro")]

    def broken(_message: str, _title: str) -> None:
        raise OSError("sin bandeja")

    state.notifier = broken
    await announce(state, Transition(Phase.WORK, Phase.SHORT_BREAK))


def test_alert_reaches_clients_on_other_pages(client: TestClient, state: AppState) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "subscribe", "topics": ["stats"]})
        ws.send_json({"type": "ping"})
        receive_until(ws, "pong")
        client.portal.call(announce, state, Transition(Phase.WORK, Phase.SHORT_BREAK))
        alert = receive_until(ws, "pomodoro.alert")
    assert alert["data"]["started"] == "short_break"


def test_controls_and_config_from_the_phone(client: TestClient, state: AppState) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "pomodoro.control", "action": "start"})
        assert receive_until(ws, "pomodoro")["data"]["status"] == "running"
        ws.send_json({"type": "pomodoro.control", "action": "pause"})
        ws.send_json({"type": "pomodoro.config", "work": 40, "short_break": 8, "long_break": 20})
        ws.send_json({"type": "ping"})
        receive_until(ws, "pong")
    assert state.pomodoro.status is Status.PAUSED
    assert state.pomodoro.durations == Durations(work=40, short_break=8, long_break=20)


def test_config_works_without_remote_edit(tmp_path: Path, state: AppState) -> None:
    """Las duraciones se editan por WiFi aunque la edición de config.json esté desactivada."""
    from phonedeck.server import create_app
    from tests.conftest import LAN_HOST

    state.mode = "wifi"
    state.settings_store.update(extra_allowed_hosts=[LAN_HOST])
    state.allowed_hosts.extra = [LAN_HOST]
    token = state.tokens.issue("celular", 1)
    app = create_app(state)
    with (
        TestClient(app, base_url=f"http://{LAN_HOST}:8765", client=("192.168.1.50", 1)) as lan,
        lan.websocket_connect(f"ws://{LAN_HOST}:8765/ws?token={token}") as ws,
    ):
        assert lan.get("/api/config", headers=auth(token)).status_code == 200
        ws.send_json({"type": "pomodoro.config", "work": 30, "short_break": 6, "long_break": 12})
        ws.send_json({"type": "ping"})
        receive_until(ws, "pong")
    assert state.pomodoro.durations.work == 30


def test_invalid_commands(client: TestClient, state: AppState) -> None:
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "pomodoro.control", "action": "expire"})
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
        ws.send_json({"type": "pomodoro.config", "work": 0, "short_break": 5, "long_break": 15})
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
        ws.send_json({"type": "pomodoro.config", "work": 181, "short_break": 5, "long_break": 15})
        assert receive_until(ws, "error")["data"]["message"] == "Comando inválido"
    assert state.pomodoro.durations == Durations()


def test_pomodoro_requires_its_widget(client: TestClient, state: AppState) -> None:
    h = auth(local_token(client))
    current = client.get("/api/config", headers=h).json()
    for page in current["config"]["pages"]:
        page["items"] = [i for i in page["items"] if i.get("widget") != "pomodoro"]
    assert client.put("/api/config", json=current, headers=h).status_code == 200

    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "pomodoro.control", "action": "start"})
        assert "no hay widget 'pomodoro'" in receive_until(ws, "error")["data"]["message"]
    assert state.pomodoro.status is Status.IDLE


def test_new_client_gets_fresh_remaining_time(client: TestClient, state: AppState) -> None:
    state.pomodoro.start()
    state.pomodoro._ends_at -= 60  # pasó un minuto desde el último mensaje
    with client.websocket_connect(f"{WS_URL}?token={local_token(client)}") as ws:
        ws.send_json({"type": "subscribe", "topics": ["pomodoro"]})
        data = receive_until(ws, "pomodoro")["data"]
    assert data["status"] == "running"
    assert data["remaining_ms"] <= 24 * 60 * 1000
