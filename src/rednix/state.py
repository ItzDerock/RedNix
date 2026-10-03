"""Event state: layout, locking, free ports, instance records, stale recovery."""

from __future__ import annotations

import errno
import fcntl
import json
import os
import re
import socket
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import Config

EVENT_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")

# Linux caps interface names at 15 bytes; the routed profile names the TAP
# "rednix-<event>", so event names beyond this length cannot use it.
MAX_ROUTED_EVENT_NAME = 15 - len("rednix-")

SOCKET_NAMES = ("rednix.sock", "rednix-virtiofs-work.sock")

DEFAULT_NETWORK = "nat"


class StateError(RuntimeError):
    pass


def validate_event_name(event: str) -> str:
    if not EVENT_NAME_RE.fullmatch(event):
        raise StateError(
            f"invalid event name {event!r}: use lowercase letters, digits and dashes "
            f"(max 31 chars); max {MAX_ROUTED_EVENT_NAME} for the routed network profile"
        )
    return event


def require_routable_name(event: str) -> str:
    if len(event) > MAX_ROUTED_EVENT_NAME:
        raise StateError(
            f"event name {event!r} is too long for a TAP interface "
            f"(rednix-{event} exceeds 15 characters); use the nat profile"
        )
    return event


@contextmanager
def event_lock(event_dir: Path) -> Iterator[None]:
    event_dir.mkdir(parents=True, exist_ok=True)
    lock_path = event_dir / ".lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def allocate_free_port(base: int, avoid: set[int] | None = None) -> int:
    avoid = avoid or set()
    for port in range(base, base + 1000):
        if port in avoid:
            continue
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
        return port
    raise StateError(f"no free port found in range {base}-{base + 999}")


def instance_path(event_dir: Path) -> Path:
    return event_dir / "instance.json"


def read_instance(event_dir: Path) -> dict | None:
    path = instance_path(event_dir)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise StateError(f"{path}: unreadable instance record: {exc}") from exc


def write_instance(event_dir: Path, data: dict) -> None:
    path = instance_path(event_dir)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        return True
    return True


def socket_has_listener(path: Path) -> bool:
    if not path.is_socket():
        return False
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(str(path))
    except (ConnectionRefusedError, OSError):
        return False
    finally:
        client.close()
    return True


def cleanup_stale_sockets(event_dir: Path) -> list[str]:
    # Callers must have verified no VM is running for this event first (pid
    # check), because unlinking a live vhost-user socket is destructive.
    removed = []
    for name in SOCKET_NAMES:
        path = event_dir / name
        if path.is_socket():
            path.unlink()
            removed.append(name)
    return removed


def all_events(config: Config) -> list[str]:
    events_dir = config.events_dir
    if not events_dir.is_dir():
        return []
    return sorted(p.name for p in events_dir.iterdir() if p.is_dir())


def read_default_event(config: Config) -> str | None:
    try:
        event = config.default_event_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeError) as exc:
        raise StateError(f"cannot read {config.default_event_path}: {exc}") from exc
    try:
        return validate_event_name(event)
    except StateError as exc:
        raise StateError(
            f"{config.default_event_path}: {exc}; reset with: rednix default --clear"
        ) from exc


def set_default_event(config: Config, event: str | None) -> None:
    if event is not None:
        validate_event_name(event)
    try:
        if event is None:
            config.default_event_path.unlink(missing_ok=True)
            return
        config.state_root.mkdir(parents=True, exist_ok=True)
        # Each writer gets its own temporary file; readers see a complete name.
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=config.state_root,
            prefix=".default-event-", delete=False,
        ) as fp:
            tmp = Path(fp.name)
            try:
                fp.write(event + "\n")
                fp.close()
                tmp.replace(config.default_event_path)
            finally:
                tmp.unlink(missing_ok=True)
    except OSError as exc:
        raise StateError(f"cannot update {config.default_event_path}: {exc}") from exc


def default_event(config: Config, explicit: str | None = None) -> str:
    if explicit is not None:
        return validate_event_name(explicit)
    selected = read_default_event(config)
    if selected is not None:
        return selected
    events = all_events(config)
    if not events:
        raise StateError(
            "no events found; create one with: rednix start <event>"
        )
    if len(events) == 1:
        return events[0]
    latest = max(
        events,
        key=lambda name: (
            instance_path(config.event_dir(name)).stat().st_mtime
            if instance_path(config.event_dir(name)).is_file()
            else 0
        ),
    )
    return latest


def share_dir_for(config: Config, event: str, override: str | None = None) -> Path:
    root = Path(override).expanduser() if override else config.share_root
    return root / event
