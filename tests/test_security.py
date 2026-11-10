"""Tokens, PIN y cabecera Host."""

from __future__ import annotations

import time

import pytest

from celldeck.security import PairingLocked, PinGuard, TokenManager, is_loopback, strip_port


def test_token_roundtrip_and_tampering() -> None:
    secret = "a" * 64
    tokens = TokenManager(lambda: secret)
    token = tokens.issue("redmi", ttl_days=1)
    payload = tokens.verify(token)
    assert payload is not None and payload.device == "redmi"

    body, sig = token.split(".")
    assert tokens.verify(body + "." + sig[:-2] + "AA") is None
    assert tokens.verify(body[:-1] + "x." + sig) is None
    assert tokens.verify("") is None
    assert tokens.verify(None) is None
    assert tokens.verify("a.b.c") is None


def test_rotating_secret_revokes_tokens() -> None:
    holder = {"s": "a" * 64}
    tokens = TokenManager(lambda: holder["s"])
    token = tokens.issue("x", 1)
    holder["s"] = "b" * 64
    assert tokens.verify(token) is None


def test_expired_token(monkeypatch: pytest.MonkeyPatch) -> None:
    tokens = TokenManager(lambda: "a" * 64)
    token = tokens.issue("x", ttl_days=1)
    future = time.time() + 2 * 86400
    monkeypatch.setattr(time, "time", lambda: future)
    assert tokens.verify(token) is None


def test_pin_guard_locks_after_failures() -> None:
    guard = PinGuard(max_fails_per_ip=3, lock_seconds=60)
    for _ in range(3):
        assert guard.verify("1.2.3.4", "000000", "123456") is False
    with pytest.raises(PairingLocked):
        guard.verify("1.2.3.4", "123456", "123456")  # bloqueada aunque acierte
    assert guard.verify("5.6.7.8", "123456", "123456") is True  # otra IP no afectada


def test_pin_guard_global_lock() -> None:
    guard = PinGuard(max_fails_per_ip=100, max_fails_global=4)
    for i in range(4):
        guard.verify(f"10.0.0.{i}", "x", "123456")
    with pytest.raises(PairingLocked):
        guard.check("10.0.0.99")


@pytest.mark.parametrize(
    "host,expected",
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("192.168.1.2", False),
        ("testclient", False),
        ("", False),
    ],
)
def test_is_loopback(host: str, expected: bool) -> None:
    assert is_loopback(host) is expected


@pytest.mark.parametrize(
    "header,expected",
    [
        ("127.0.0.1:8765", "127.0.0.1"),
        ("LocalHost", "localhost"),
        ("[::1]:8765", "::1"),
        ("evil.com:80", "evil.com"),
    ],
)
def test_strip_port(header: str, expected: str) -> None:
    assert strip_port(header) == expected
