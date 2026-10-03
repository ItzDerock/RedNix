import json
from pathlib import Path
import subprocess

import pytest

from rednix import apps, guest_apps, menu
from rednix.state import StateError


def test_desktop_exec_fields_keep_argument_boundaries(monkeypatch):
    monkeypatch.setattr(guest_apps.shutil, "which", lambda name: name)
    entry = {"Name": "Demo App", "Icon": "demo", "Exec":
             'demo "two words" %U %i %c %k %%'}
    assert guest_apps.desktop_command(entry, Path("/tmp/demo.desktop")) == [
        "demo", "two words", "--icon", "demo", "Demo App", "/tmp/demo.desktop", "%",
    ]
    with pytest.raises(ValueError):
        guest_apps.desktop_command({"Name": "Bad", "Exec": "demo %z"}, Path("bad"))


def test_discovery_filters_entries_and_preserves_ghidra_wrapper(tmp_path, monkeypatch):
    monkeypatch.setattr(guest_apps.shutil, "which",
                        lambda name: name if Path(name).name in ("demo", "ghidra") else None)
    user = tmp_path / "user" / "applications"
    system = tmp_path / "system" / "applications"
    user.mkdir(parents=True)
    system.mkdir(parents=True)
    entries = {
        "demo.desktop": "Name=Demo\nExec=demo %F\n",
        "hidden.desktop": "Name=Hidden\nExec=demo\nHidden=true\n",
        "nodisplay.desktop": "Name=No display\nExec=demo\nNoDisplay=true\n",
        "terminal.desktop": "Name=CLI\nExec=demo\nTerminal=true\n",
        "missing.desktop": "Name=Missing\nExec=missing\n",
        "tryexec.desktop": "Name=Missing TryExec\nExec=demo\nTryExec=missing\n",
        "ghidra.desktop": "Name=Package Ghidra\nExec=/nix/store/fake/bin/ghidra\n",
        "masked.desktop": "Name=Masked\nExec=demo\n",
        "cwd.desktop": "Name=Working directory\nExec=demo\nPath=/tmp/two words\n",
    }
    for name, entry in entries.items():
        (system / name).write_text("[Desktop Entry]\nType=Application\n" + entry)
    (user / "masked.desktop").write_text("[Desktop Entry]\nHidden=true\n")
    result = guest_apps.discover([user.parent, system.parent])
    assert [app["name"] for app in result] == ["Demo", "Ghidra", "Working directory"]
    assert result[1]["command"] == ["ghidra"]
    assert result[1]["xwls"] is True
    assert result[2]["command"][-2:] == ["/tmp/two words", "demo"]


def test_guest_discovery_failure_is_actionable(config, monkeypatch):
    monkeypatch.setattr(apps, "require_running", lambda *args: None)
    monkeypatch.setattr(apps.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 255, "", "connection refused"))
    with pytest.raises(StateError, match="connection refused"):
        apps.installed(config, "test")


@pytest.mark.parametrize("payload", ["oops", {}, [{"name": "Bad", "command": "demo"}]])
def test_invalid_guest_app_list(config, monkeypatch, payload):
    monkeypatch.setattr(apps, "require_running", lambda *args: None)
    monkeypatch.setattr(apps.subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 0, json.dumps(payload), ""))
    with pytest.raises(StateError, match="invalid app list"):
        apps.installed(config, "test")


def test_picker_search_uses_names_and_commands():
    labels = ["Ghidra — ghidra [X11]", "Firefox — firefox", "Thunar — thunar"]
    assert menu.matching(labels, "GHID x11") == [0]
    assert menu.matching(labels, "") == [0, 1, 2]
    assert menu.matching(labels, "missing") == []


def test_picker_launch_uses_guest_command_and_x11(config, monkeypatch):
    monkeypatch.setattr(apps, "installed", lambda *args: [
        {"name": "Demo", "command": ["demo", "two words"], "xwls": True},
    ])
    monkeypatch.setattr(apps.menu, "choose", lambda *args: 0)
    calls = []
    monkeypatch.setattr(apps.gui, "gui", lambda *args, **kwargs: calls.append((args, kwargs)) or 0)
    assert apps.launch(config, "test") == 0
    assert calls[0][0][2:] == ("demo", ["two words"])
    assert calls[0][1] == {"xwls": True}
