"""Información de red: IPs locales para el modo WiFi y la lista de Hosts permitidos."""

from __future__ import annotations

import ipaddress
import logging
import socket
import time

import psutil

log = logging.getLogger(__name__)

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def local_ipv4_addresses() -> list[str]:
    """IPv4 privadas de las interfaces activas (WiFi, Ethernet, anclaje USB...)."""
    result: list[str] = []
    try:
        stats = psutil.net_if_stats()
        for name, addrs in psutil.net_if_addrs().items():
            if name in stats and not stats[name].isup:
                continue
            for addr in addrs:
                if addr.family != socket.AF_INET:
                    continue
                ip = ipaddress.ip_address(addr.address)
                if ip.is_private and not ip.is_loopback and not ip.is_link_local:
                    result.append(addr.address)
    except Exception:
        log.exception("No se pudieron listar las interfaces de red")
    return sorted(set(result))


class AllowedHosts:
    """Calcula (con caché) los valores de ``Host`` aceptados."""

    def __init__(self, wifi_enabled: bool, extra: list[str], ttl: float = 15.0) -> None:
        self.wifi_enabled = wifi_enabled
        self.extra = extra
        self._ttl = ttl
        self._cache: set[str] = set()
        self._expires = 0.0

    def __call__(self) -> set[str]:
        now = time.monotonic()
        if now >= self._expires:
            hosts = set(LOOPBACK_HOSTS) | set(self.extra)
            if self.wifi_enabled:
                hosts |= set(local_ipv4_addresses())
                hostname = socket.gethostname().lower()
                hosts |= {hostname, f"{hostname}.local"}
            self._cache = hosts
            self._expires = now + self._ttl
        return self._cache
