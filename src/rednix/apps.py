"""Host-side discovery and launch of installed guest GUI applications."""

from __future__ import annotations

import json
from pathlib import Path
import shlex
import subprocess

from . import guest_apps, gui, menu, ssh, state
from .config import Config
from .state import StateError


def require_running(config: Config, event: str) -> None:
    instance = state.read_instance(config.event_dir(event))
    if instance is None or not state.pid_alive(instance.get("pid")):
        raise StateError(f"event '{event}' is not running; start it with: rednix start {event}")


def installed(config: Config, event: str) -> list[dict]:
    require_running(config, event)
    source = Path(guest_apps.__file__).read_text(encoding="utf-8")
    try:
        result = subprocess.run(
            ssh.ssh_args(config, event) + ["--", "python3 -"],
            input=source, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise StateError(f"could not list guest apps: {exc}") from exc
    if result.returncode:
        raise StateError(f"could not list guest apps: {result.stderr.strip()}")
    try:
        apps = json.loads(result.stdout)
        if not isinstance(apps, list) or any(
            not isinstance(app, dict) or not isinstance(app.get("name"), str)
            or not isinstance(app.get("xwls"), bool)
            or not isinstance(app.get("command"), list) or not app["command"]
            or not all(isinstance(arg, str) for arg in app["command"])
            for app in apps
        ):
            raise ValueError("invalid app list")
        return apps
    except (ValueError, TypeError) as exc:
        raise StateError("guest returned an invalid app list") from exc


def launch(config: Config, event: str, list_only: bool = False, xwls: bool = False) -> int:
    apps = installed(config, event)
    labels = [f"{app['name']}  —  {shlex.join(app['command'])}"
              + ("  [X11]" if app["xwls"] else "") for app in apps]
    if list_only:
        print("\n".join(labels) if labels else "No GUI applications found in the guest.")
        return 0
    index = menu.choose(f"GUI applications — {event}", labels)
    if index is None:
        return 0
    app = apps[index]
    return gui.gui(config, event, app["command"][0], app["command"][1:],
                   xwls=xwls or app["xwls"])
