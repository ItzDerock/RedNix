"""SSH plumbing: host keypair, generated ssh_config, command construction."""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from .config import Config
from .state import StateError, all_events, instance_path

SSH_COMMON = """\
Host rednix-*
  User rednix
  IdentityFile {identity_file}
  IdentitiesOnly yes
  # The guest is reachable only via loopback hostfwd to our own VM, and its
  # host keys regenerate on tmpfs-root reboots; pinning them buys nothing
  # here and breaks after every stop/start cycle.
  StrictHostKeyChecking no
  UserKnownHostsFile /dev/null
  LogLevel ERROR
  ControlMaster auto
  ControlPath {control_path}
  ControlPersist 600
  ConnectTimeout 10
  ServerAliveInterval 15
  ServerAliveCountMax 4
"""


def ensure_keypair(config: Config) -> Path:
    config.keys_dir.mkdir(parents=True, exist_ok=True)
    key = config.private_key
    if not key.exists():
        subprocess.run(
            [
                "ssh-keygen",
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-C",
                "rednix",
                "-f",
                str(key),
            ],
            check=True,
        )
        print(f"generated guest SSH key: {key}")
    elif not config.public_key.exists():
        derived = _derive_public(key)
        config.public_key.write_text(derived + "\n", encoding="utf-8")
    os.chmod(key, 0o600)
    return key


def _derive_public(private: Path) -> str:
    result = subprocess.run(
        ["ssh-keygen", "-y", "-f", str(private)], capture_output=True, text=True
    )
    if result.returncode != 0:
        raise StateError(
            f"{private}: ssh-keygen could not read the private key: "
            f"{result.stderr.strip()}"
        )
    return result.stdout.strip()


def import_public_key(config: Config, src: str) -> None:
    """Seed the state-root keys from a user-provided keypair.

    A path to a private key imports both halves (the public half is derived).
    A path ending in .pub records only the public half; the matching private
    key must then be placed at the state-root private path for ssh to work.
    """
    path = Path(src).expanduser()
    if not path.is_file():
        raise StateError(f"{path}: no such file")
    config.keys_dir.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".pub":
        pub = path.read_text(encoding="utf-8").strip()
        if not pub or pub.startswith("#"):
            raise StateError(f"{path}: not a usable public key")
        config.public_key.write_text(pub + "\n", encoding="utf-8")
        if not config.private_key.exists():
            print(
                f"copied public key to {config.public_key}; the matching private key "
                f"must be placed at {config.private_key} for ssh to authenticate"
            )
    else:
        derived = _derive_public(path)
        shutil.copy2(path, config.private_key)
        os.chmod(config.private_key, 0o600)
        config.public_key.write_text(derived + "\n", encoding="utf-8")
        print(f"imported keypair: {config.private_key} + {config.public_key}")


def write_ssh_config(config: Config) -> Path:
    events = all_events(config)
    blocks = [SSH_COMMON.format(
        identity_file=config.private_key,
        control_path=config.ssh_sockets_dir / "ssh-%r@%h:%p",
    )]
    for event in events:
        instance = {}
        if instance_path(config.event_dir(event)).is_file():
            try:
                instance = json.loads(
                    instance_path(config.event_dir(event)).read_text(encoding="utf-8")
                )
            except Exception:
                instance = {}
        port = instance.get("ssh_port")
        if port:
            blocks.append(
                f"Host rednix-{event}\n"
                f"  HostName 127.0.0.1\n"
                f"  Port {port}\n"
            )
    config.ssh_config.write_text("".join(blocks), encoding="utf-8")
    return config.ssh_config


def ssh_args(config: Config, event: str, extra: list[str] | None = None) -> list[str]:
    args = ["ssh", "-F", str(config.ssh_config), f"rednix-{event}"]
    if extra:
        args = args[:1] + extra + args[1:]
    return args


def run(config: Config, event: str, command: list[str], interactive_tty: bool = False,
        capture: bool = False) -> int:
    # ssh concatenates remote arguments with spaces, so the command must be
    # pre-joined into one correctly quoted string for the remote shell.
    extra = []
    if interactive_tty:
        extra.append("-t")
    args = ssh_args(config, event, extra) + ["--", shlex.join(list(command))]
    result = subprocess.run(args, capture_output=capture, text=capture)
    if capture:
        sys.stdout.write(result.stdout or "")
        sys.stderr.write(result.stderr or "")
    return result.returncode


def start_service(config: Config, event: str, unit: str) -> int:
    return run(config, event, ["sudo", "-n", "systemctl", "start", unit])


def stop_service(config: Config, event: str, unit: str) -> int:
    return run(config, event, ["sudo", "-n", "systemctl", "stop", unit])
