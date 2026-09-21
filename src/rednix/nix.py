"""Nix build plumbing. Only `rednix build` evaluates the flake; starts never do."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .config import Config
from .state import StateError, validate_event_name


def find_flake_dir(start: Path | None = None) -> Path:
    current = (start or Path.cwd()).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "flake.nix").is_file():
            return candidate
    raise StateError(
        "no flake.nix found from the working directory upward; "
        "run from the RedNix checkout or set REDNIX_FLAKE"
    )


def build(config: Config, event: str | None = None, pin: bool = False) -> Path:
    flake = Path(os.environ.get("REDNIX_FLAKE", "")) or find_flake_dir()
    if not (flake / "flake.nix").is_file():
        raise StateError(f"REDNIX_FLAKE points at {flake}, which has no flake.nix")

    if event is not None:
        event = validate_event_name(event)
        edir = config.event_dir(event)
        edir.mkdir(parents=True, exist_ok=True)

    if pin:
        out_link = config.gcroots_dir / (event or "guestRunner")
        out_link.parent.mkdir(parents=True, exist_ok=True)
    elif event:
        out_link = edir / "current"
    else:
        out_link = config.gcroots_dir / "guestRunner"
        out_link.parent.mkdir(parents=True, exist_ok=True)

    if not config.public_key.is_file():
        raise StateError(
            f"no guest public key at {config.public_key}; run rednix init first"
        )

    print(f"nix build {flake}#guestRunner -> {out_link}")
    result = subprocess.run(
        [
            "nix",
            "build",
            f"{flake}#guestRunner",
            # Inject the state-root public key. --override-input implies
            # --no-write-lock-file, so the committed flake.lock never changes.
            "--override-input",
            "guestKey",
            f"file+file://{config.public_key}",
            "--out-link",
            str(out_link),
            "--print-out-paths",
        ],
    )
    if result.returncode != 0:
        raise StateError("nix build failed")

    target = out_link.resolve()
    if pin and event:
        current = config.event_dir(event) / "current"
        if current.is_symlink() or current.exists():
            current.unlink()
        current.symlink_to(target)
    print(f"runner: {target}")
    return target
