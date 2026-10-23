import socket
import threading

import pytest

from backend import llm, offline


@pytest.mark.parametrize("host,local", [("127.0.0.1", True), ("localhost", True), ("192.168.1.20", True), ("10.0.0.5", True),
                                        ("::1", True), ("8.8.8.8", False), ("example.com", False), ("172.32.0.1", False)])
def test_is_local(host, local):
    assert offline.is_local(host) is local


def test_enabled_reads_the_env(monkeypatch):
    monkeypatch.delenv("OFFLINE", raising=False)
    assert not offline.enabled()
    monkeypatch.setenv("OFFLINE", "1")
    assert offline.enabled()


def test_guard_blocks_the_internet_but_not_loopback():
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    threading.Thread(target=lambda: server.accept(), daemon=True).start()
    with offline.guard():
        socket.create_connection(("127.0.0.1", port), timeout=2).close()  # this machine: fine
        with pytest.raises(offline.OfflineError, match="refusing to connect to 93.184.216.34"):
            socket.create_connection(("93.184.216.34", 80), timeout=2)
        with pytest.raises(offline.OfflineError, match="DNS lookup of 'example.com'"):
            socket.getaddrinfo("example.com", 80)
    server.close()


def test_guard_is_removed_afterwards():
    before = socket.socket.connect
    with offline.guard():
        assert socket.socket.connect is not before
    assert socket.socket.connect is before


def test_llm_refuses_a_remote_server_when_offline(monkeypatch):
    monkeypatch.setenv("OFFLINE", "1")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    with pytest.raises(llm.LLMUnavailable, match="OFFLINE=1"):
        llm.chat([{"role": "user", "content": "hi"}])


def test_enforce_sets_the_hugging_face_offline_flags(monkeypatch):
    import os
    monkeypatch.setenv("OFFLINE", "1")
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")  # monkeypatch restores both variables afterwards
    monkeypatch.setenv("TRANSFORMERS_OFFLINE", "0")
    monkeypatch.setattr(offline, "_installed", True)  # don't leave a guard installed in the test process
    assert offline.enforce() is True
    assert os.environ["HF_HUB_OFFLINE"] == "1" and os.environ["TRANSFORMERS_OFFLINE"] == "1"
