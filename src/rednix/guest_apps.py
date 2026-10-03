"""App discovery helper sent over SSH to the guest's Python (no installation)."""

from __future__ import annotations

import configparser
import json
import os
from pathlib import Path
import re
import shlex
import shutil


# These also cover tools without a desktop entry and preserve RedNix's
# foreground Ghidra wrapper instead of the package's absolute Exec path.
FAVORITES = (
    ("firefox", "Firefox", False),
    ("burpsuite", "Burp Suite", True),
    ("ghidra", "Ghidra", True),
    ("cutter", "Cutter", True),
    ("wireshark", "Wireshark", False),
    ("thunar", "Thunar (files)", False),
    ("foot", "Foot (terminal)", False),
    ("xterm", "XTerm", True),
)


def desktop_command(entry, path: Path) -> list[str]:
    """Expand Exec fields without files/URLs; never interpret a shell command."""
    # Desktop string escaping precedes command line unquoting.
    escapes = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}
    value = re.sub(r"\\([sntr\\])", lambda m: escapes[m[1]], entry["Exec"])
    tokens = shlex.split(value)
    result = []
    for token in tokens:
        if token in ("%f", "%F", "%u", "%U", "%d", "%D", "%n", "%N", "%v", "%m"):
            continue
        if token == "%i":
            if entry.get("Icon"):
                result.extend(["--icon", entry["Icon"]])
            continue

        def field(match):
            code = match[1]
            if code == "%":
                return "%"
            if code == "c":
                return entry["Name"]
            if code == "k":
                return str(path)
            raise ValueError(f"unsupported desktop field %{code}")

        result.append(re.sub(r"%(.)", field, token))
    if not result or not shutil.which(result[0]):
        raise ValueError("executable unavailable")
    return result


def discover(data_dirs: list[Path] | None = None) -> list[dict]:
    apps = []
    favorites = set()
    for binary, name, xwls in FAVORITES:
        if shutil.which(binary):
            favorites.add(binary)
            apps.append(dict(name=name, command=[binary], xwls=xwls))
    if data_dirs is None:
        data_dirs = [Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share")))]
        data_dirs += [Path(p) for p in os.environ.get(
            "XDG_DATA_DIRS", "/usr/local/share:/usr/share").split(":") if p]
        data_dirs.append(Path("/run/current-system/sw/share"))
    seen = set()
    for directory in data_dirs:
        for path in sorted((directory / "applications").rglob("*.desktop")):
            desktop_id = str(path.relative_to(directory / "applications")).replace("/", "-")
            if desktop_id in seen:
                continue
            seen.add(desktop_id)
            parser = configparser.ConfigParser(interpolation=None, strict=False)
            parser.optionxform = str
            try:
                parser.read(path, encoding="utf-8")
                entry = parser["Desktop Entry"]
                if entry.get("Type") != "Application" or any(
                    entry.get(key, "false").lower() == "true"
                    for key in ("Hidden", "NoDisplay", "Terminal")
                ):
                    continue
                if entry.get("TryExec") and not shutil.which(entry["TryExec"]):
                    continue
                command = desktop_command(entry, path)
                if Path(command[0]).name in favorites:
                    continue
                if entry.get("Path"):
                    # Honor a desktop entry's working directory with safely
                    # quoted arguments; the picker never concatenates raw Exec.
                    command = ["sh", "-c", 'cd -- "$1" && shift && exec "$@"',
                               "rednix-app", entry["Path"], *command]
                apps.append(dict(name=entry["Name"], command=command, xwls=True))
            except (OSError, UnicodeError, configparser.Error, KeyError, ValueError):
                continue
    return sorted(apps, key=lambda app: (app["name"].casefold(), app["command"]))


if __name__ == "__main__":
    print(json.dumps(discover()))
