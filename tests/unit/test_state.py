import json
import socket
import subprocess
import time

import pytest

from rednix.state import (
    StateError,
    allocate_free_port,
    all_events,
    cleanup_stale_sockets,
    default_event,
    event_lock,
    pid_alive,
    read_instance,
    require_routable_name,
    share_dir_for,
    socket_has_listener,
    validate_event_name,
    write_instance,
)


@pytest.mark.parametrize("name", ["ctf", "raymond-james", "ev1", "a-b-c"])
def test_valid_event_names(name):
    assert validate_event_name(name) == name


@pytest.mark.parametrize("name", ["CTF", "a/b", "-lead", "has space", "x" * 32, ""])
def test_invalid_event_names(name):
    with pytest.raises(StateError):
        validate_event_name(name)


def test_routable_name_limit():
    require_routable_name("short")  # rednix-short = 11 chars
    with pytest.raises(StateError, match="TAP"):
        require_routable_name("way-too-long-event-name")


def test_allocate_free_port_skips_occupied():
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blocker.bind(("127.0.0.1", 0))
    port = blocker.getsockname()[1]
    try:
        blocker.listen(1)
        free = allocate_free_port(port)
        assert free != port
    finally:
        blocker.close()


def test_pid_alive():
    assert pid_alive(0) is False
    assert pid_alive(None) is False
    assert pid_alive(-5) is False
    assert pid_alive(__import__("os").getpid()) is True
    proc = subprocess.Popen(["true"])
    proc.wait()
    deadline = time.time() + 5
    while pid_alive(proc.pid) and time.time() < deadline:
        time.sleep(0.05)
    assert pid_alive(proc.pid) is False


def test_socket_listener_and_stale_cleanup(tmp_path):
    live = tmp_path / "rednix.sock"
    dead = tmp_path / "rednix-virtiofs-work.sock"
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(live))
    server.listen(1)
    import socket as _s

    stale = _s.socket(_s.AF_UNIX, _s.SOCK_STREAM)
    stale.bind(str(dead))
    stale.close()

    assert socket_has_listener(live) is True
    assert socket_has_listener(dead) is False
    # cleanup unlinks unconditionally: callers must verify no VM runs first,
    # because connecting to a live vhost-user socket would kill its daemon
    removed = cleanup_stale_sockets(tmp_path)
    assert removed == ["rednix.sock", "rednix-virtiofs-work.sock"]
    assert not live.exists()
    assert not dead.exists()
    server.close()


def test_instance_round_trip(tmp_path):
    assert read_instance(tmp_path) is None
    write_instance(tmp_path, {"event": "ev", "pid": 42})
    assert read_instance(tmp_path) == {"event": "ev", "pid": 42}
    assert not list(tmp_path.glob("*.tmp"))


def test_event_lock_creates_file(tmp_path):
    with event_lock(tmp_path):
        assert (tmp_path / ".lock").exists()


def test_all_events_and_default(tmp_path):
    (tmp_path / "events" / "b-event").mkdir(parents=True)
    (tmp_path / "events" / "a-event").mkdir()
    (tmp_path / "events" / "notes.txt").write_text("x")

    class Cfg:
        pass

    cfg = Cfg()
    cfg.events_dir = tmp_path / "events"
    cfg.event_dir = lambda name: cfg.events_dir / name
    assert all_events(cfg) == ["a-event", "b-event"]
    assert default_event(cfg) == "a-event"


def test_share_dir_override(config):
    assert share_dir_for(config, "ev") == config.share_root / "ev"
    assert share_dir_for(config, "ev", "/tmp/alt") == __import__("pathlib").Path("/tmp/alt/ev")
