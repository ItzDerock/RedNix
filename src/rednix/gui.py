"""GUI access to the guest: per-window Waypipe forwarding and the VNC desktop fallback.

``rednix gui`` runs entirely on the host as the client side of the forwarding:

    waypipe --no-gpu --title-prefix "[RedNix] " ssh -F <ssh_config> rednix-<event> -- <program> [args...]

- ``--no-gpu`` blocks the ``wayland-drm`` and ``linux-dmabuf`` Wayland
  protocols, so guest clients are offered no direct GPU or DMA-BUF path.
  Start here; enable acceleration only if a specific tool demands it.
- The ``[RedNix] `` title prefix is applied client-side as a visual cue for
  Hyprland window rules and workspaces. It is not a security boundary.
- ``--xwls`` runs X11 clients (Burp, Ghidra) under Wayland via
  xwayland-satellite and therefore requires ``xwayland-satellite`` in the
  guest ``PATH``.

``rednix desktop`` is the fallback for tools that refuse to run under Waypipe:
an SSH tunnel to the guest's VNC server (guest-side 127.0.0.1:5901, wayvnc
serving a headless labwc session), the on-demand guest session
(``rednix-desktop.service``, started through scoped NOPASSWD sudo), and a
local viewer. Closing the viewer leaves the guest
session running, so the next ``rednix desktop`` reconnects.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time

from . import state
from .config import Config
from .ssh import start_service, stop_service
from .state import StateError

DESKTOP_UNIT = "rednix-desktop.service"
GUEST_VNC_PORT = 5901
TUNNEL_SETTLE_SECONDS = 2.0
VNC_READY_TIMEOUT_SECONDS = 30.0
VNC_POLL_INTERVAL_SECONDS = 0.5


def gui(config: Config, event: str, program: str, args: list[str], xwls: bool = False) -> int:
    if shutil.which("waypipe") is None:
        raise StateError(
            "waypipe not found on the host PATH; it is the client side of window "
            "forwarding and must be installed on the host (nixpkgs package: waypipe)"
        )
    argv = [
        "waypipe",
        "--no-gpu",
        "--title-prefix",
        "[RedNix] ",
        *(["--xwls"] if xwls else []),
        "ssh",
        "-F",
        str(config.ssh_config),
        f"rednix-{event}",
        "--",
        program,
        *args,
    ]
    try:
        os.execvp("waypipe", argv)
    except OSError as exc:
        raise StateError(f"failed to exec waypipe: {exc}") from exc


def desktop(config: Config, event: str, local_port: int = 5901) -> int:
    instance = state.read_instance(config.event_dir(event))
    if instance is None or not state.pid_alive(instance.get("pid")):
        raise StateError(f"event '{event}' is not running; start it with: rednix start {event}")
    config.ssh_sockets_dir.mkdir(parents=True, exist_ok=True)
    # This tunnel must outlive the viewer so the guest session can be reconnected.
    tunnel = subprocess.Popen(
        [
            "ssh",
            "-F",
            str(config.ssh_config),
            "-N",
            "-o",
            "ExitOnForwardFailure=yes",
            "-L",
            f"{local_port}:127.0.0.1:{GUEST_VNC_PORT}",
            f"rednix-{event}",
        ],
        start_new_session=True,
    )

    settle_deadline = time.monotonic() + TUNNEL_SETTLE_SECONDS
    while time.monotonic() < settle_deadline:
        if tunnel.poll() is not None:
            raise StateError(
                f"SSH tunnel to the guest exited immediately (exit code {tunnel.returncode}); "
                f"check 'rednix logs {event}' and that local port {local_port} is free"
            )
        time.sleep(0.1)

    code = start_service(config, event, DESKTOP_UNIT)
    if code != 0:
        _stop_tunnel(tunnel)
        raise StateError(
            f"failed to start {DESKTOP_UNIT} in the guest (ssh exit code {code}); "
            f"check it with 'rednix shell {event}' and 'systemctl status {DESKTOP_UNIT}'"
        )

    deadline = time.monotonic() + VNC_READY_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if tunnel.poll() is not None:
            raise StateError(
                "SSH tunnel to the guest exited while waiting for the desktop "
                f"(exit code {tunnel.returncode}); check 'rednix logs {event}'"
            )
        if _port_open(local_port):
            break
        time.sleep(VNC_POLL_INTERVAL_SECONDS)
    else:
        _stop_tunnel(tunnel)
        raise StateError(
            f"the guest desktop did not accept connections on 127.0.0.1:{local_port} within "
            f"{int(VNC_READY_TIMEOUT_SECONDS)} s; check it with 'rednix shell {event}' and "
            f"'systemctl status {DESKTOP_UNIT}'"
        )

    if shutil.which("vncviewer") is None:
        print("no local VNC viewer found (looked for 'vncviewer' on PATH)")
        print("the SSH tunnel to the guest desktop is up in the background:")
        print(
            f"  ssh -F {config.ssh_config} -N "
            f"-L {local_port}:127.0.0.1:{GUEST_VNC_PORT} rednix-{event}"
        )
        print(f"connect a VNC client to 127.0.0.1:{local_port}")
        return 0

    result = subprocess.run(["vncviewer", f"127.0.0.1:{local_port}"])
    _stop_tunnel(tunnel)
    print("desktop session still running in the guest; reconnect any time with: rednix desktop")
    return result.returncode


def desktop_stop(config: Config, event: str) -> int:
    code = stop_service(config, event, DESKTOP_UNIT)
    print(f"desktop session stopped for event '{event}'")
    return code


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(1.0)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _stop_tunnel(tunnel: subprocess.Popen) -> None:
    tunnel.terminate()
    try:
        tunnel.wait(timeout=5)
    except subprocess.TimeoutExpired:
        tunnel.kill()
        tunnel.wait(timeout=5)
