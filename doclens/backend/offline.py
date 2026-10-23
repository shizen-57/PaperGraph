"""Air-gapped mode. OFFLINE=1 means: only local models, and no network except this machine and the private LAN.

    OFFLINE=1 LLM_BASE_URL=http://127.0.0.1:8001/v1 LLM_MODEL=qwen2.5-3b-instruct uvicorn backend.app:app

What it does:
  - refuses every outbound connection whose address is not loopback or private (socket.connect), and every
    DNS lookup except `localhost` and IP literals, so nothing leaks even as a hostname;
  - makes llm.chat reject a non-local LLM_BASE_URL with a readable message;
  - sets HF_HUB_OFFLINE / TRANSFORMERS_OFFLINE so Hugging Face libraries load cached models only (download them first).

It is a guard inside the Python process, not a firewall: for a real air gap also cut the network at the OS level.
"""
import ipaddress
import os
import socket
from contextlib import contextmanager
from urllib.parse import urlparse


class OfflineError(ConnectionRefusedError):
    pass


def enabled() -> bool:
    return os.environ.get("OFFLINE", "0").lower() in ("1", "true", "yes")


def is_local(host: str) -> bool:
    """Loopback, private-range or link-local IP literal, or `localhost`."""
    if host in ("localhost", "localhost.localdomain"):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


def check_url(url: str | None) -> None:
    """Raise OfflineError if OFFLINE=1 and the URL points off this machine / LAN."""
    if not enabled() or not url:
        return
    host = urlparse(url).hostname or ""
    if not is_local(host):
        raise OfflineError(f"OFFLINE=1: {url!r} is not on this machine or your LAN. Point LLM_BASE_URL at a local server.")


@contextmanager
def guard():
    """Install the socket guard for the duration of the block (tests). `enforce()` installs it for good."""
    connect, getaddrinfo = socket.socket.connect, socket.getaddrinfo

    def guarded_connect(self, address):
        if self.family in (socket.AF_INET, socket.AF_INET6) and not is_local(str(address[0])):
            raise OfflineError(f"OFFLINE=1: refusing to connect to {address[0]}")
        return connect(self, address)

    def guarded_getaddrinfo(host, *args, **kwargs):
        if host is not None and not is_local(str(host)):
            try:
                ipaddress.ip_address(str(host).strip("[]"))  # a public IP literal is refused at connect()
            except ValueError:
                raise OfflineError(f"OFFLINE=1: refusing DNS lookup of {host!r}") from None
        return getaddrinfo(host, *args, **kwargs)

    socket.socket.connect, socket.getaddrinfo = guarded_connect, guarded_getaddrinfo
    try:
        yield
    finally:
        socket.socket.connect, socket.getaddrinfo = connect, getaddrinfo


_installed = False


def enforce() -> bool:
    """Call once at start-up of every entry point. Returns True if the guard is now active."""
    global _installed
    if not enabled():
        return False
    os.environ["HF_HUB_OFFLINE"] = os.environ["TRANSFORMERS_OFFLINE"] = "1"  # overrides: offline means offline
    if not _installed:
        guard().__enter__()  # never exited: the guard stays for the life of the process
        _installed = True
    return True
