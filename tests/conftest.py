"""Fixtures comunes. Todo usa ``FakeBackend``: los tests no tocan Windows."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from phonedeck.config.settings import Settings
from phonedeck.platform.fake import FakeBackend
from phonedeck.plugins import PluginRegistry, build_default_registry
from phonedeck.plugins.base import PluginContext
from phonedeck.plugins.runner import ActionRunner
from phonedeck.server import create_app
from phonedeck.state import AppState, build_state

LOCAL = "http://127.0.0.1:8765"
LAN_HOST = "192.168.1.10"


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def registry() -> PluginRegistry:
    return build_default_registry()


@pytest.fixture
def settings() -> Settings:
    return Settings()


@pytest.fixture
def runner(registry: PluginRegistry, backend: FakeBackend, settings: Settings) -> ActionRunner:
    return ActionRunner(registry, backend, lambda: settings)


@pytest.fixture
def ctx(backend: FakeBackend, settings: Settings, runner: ActionRunner) -> PluginContext:
    import logging

    async def nested(params: Any) -> Any:
        return await runner._run(params, depth=1)

    return PluginContext(backend, settings, logging.getLogger("test"), nested)


def make_state(
    tmp_path: Path, backend: FakeBackend, mode: str = "usb", **settings: Any
) -> AppState:
    state = build_state(tmp_path, backend=backend, mode_override=mode)
    if settings or mode == "wifi":
        state.settings_store.update(extra_allowed_hosts=[LAN_HOST], **settings)
        state.allowed_hosts.extra = [LAN_HOST]
    return state


@pytest.fixture
def state(tmp_path: Path, backend: FakeBackend) -> AppState:
    return make_state(tmp_path, backend)


@pytest.fixture
def client(state: AppState) -> Iterator[TestClient]:
    """Cliente que simula el celular por USB (llega como 127.0.0.1)."""
    with TestClient(create_app(state), base_url=LOCAL, client=("127.0.0.1", 50000)) as c:
        yield c


def local_token(client: TestClient) -> str:
    token: str = client.get("/api/session").json()["token"]
    return token


def auth(token: str) -> dict[str, str]:
    return {"X-PhoneDeck-Token": token}
