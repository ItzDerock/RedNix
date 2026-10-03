"""Configuration resolution: --state-root flag > REDNIX_STATE_ROOT > config.toml > default."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

DEFAULT_STATE_ROOT = Path.home() / ".local" / "state" / "rednix"
DEFAULT_SHARE_ROOT = Path.home() / "CTF"

NETWORK_PROFILES = ("nat", "routed")


class ConfigError(RuntimeError):
    pass


@dataclass
class Config:
    state_root: Path
    share_root: Path
    default_network: str
    guest_mem_mib: int
    guest_vcpu: int
    ssh_port_base: int
    host_uid: int
    host_gid: int
    guest_uid: int
    guest_gid: int
    ssh_connect_timeout: int
    ctf_iface: str | None

    @property
    def events_dir(self) -> Path:
        return self.state_root / "events"

    @property
    def gcroots_dir(self) -> Path:
        return self.state_root / "gcroots"

    @property
    def keys_dir(self) -> Path:
        return self.state_root / "keys"

    @property
    def private_key(self) -> Path:
        return self.keys_dir / "id_ed25519"

    @property
    def public_key(self) -> Path:
        return self.keys_dir / "id_ed25519.pub"

    @property
    def ssh_config(self) -> Path:
        return self.state_root / "ssh_config"

    @property
    def known_hosts(self) -> Path:
        return self.state_root / "known_hosts"

    @property
    def ssh_sockets_dir(self) -> Path:
        return self.state_root / "sockets"

    @property
    def config_path(self) -> Path:
        return self.state_root / "config.toml"

    @property
    def default_event_path(self) -> Path:
        return self.state_root / "default-event"

    def event_dir(self, event: str) -> Path:
        return self.events_dir / event


def _read_toml(path: Path) -> dict:
    try:
        with open(path, "rb") as fp:
            return tomllib.load(fp)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: invalid TOML: {exc}") from exc


def _as_int(table: dict, key: str, path: Path, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"{path}: '{key}' must be an integer, got {value!r}")
    return value


def _as_path(table: dict, key: str, default: Path) -> Path:
    value = table.get(key)
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{key}' must be a non-empty string")
    return Path(value).expanduser()


def load_config(state_root_arg: str | None = None) -> Config:
    explicit = state_root_arg or os.environ.get("REDNIX_STATE_ROOT")
    root = Path(explicit).expanduser() if explicit else DEFAULT_STATE_ROOT

    cfg: dict = {}
    path = root / "config.toml"
    if path.is_file():
        cfg = _read_toml(path)

    # A config.toml may relocate the state root (e.g. onto an external SSD),
    # but only when the root was not given explicitly via flag or environment.
    if not explicit and isinstance(cfg.get("state_root"), str) and cfg["state_root"].strip():
        relocated = Path(cfg["state_root"]).expanduser()
        relocated_cfg_path = relocated / "config.toml"
        if relocated_cfg_path.is_file():
            cfg = _read_toml(relocated_cfg_path)
            cfg.pop("state_root", None)
        root = relocated

    network = cfg.get("default_network", "nat")
    if network not in NETWORK_PROFILES:
        raise ConfigError(
            f"{root / 'config.toml'}: 'default_network' must be one of {NETWORK_PROFILES}, got {network!r}"
        )

    ctf_iface = cfg.get("ctf_iface")
    if ctf_iface is not None and (not isinstance(ctf_iface, str) or not ctf_iface.strip()):
        raise ConfigError(f"{root / 'config.toml'}: 'ctf_iface' must be a non-empty string")

    return Config(
        state_root=root,
        share_root=_as_path(cfg, "share_root", DEFAULT_SHARE_ROOT),
        default_network=network,
        guest_mem_mib=_as_int(cfg, "guest_mem_mib", path, 16384),
        guest_vcpu=_as_int(cfg, "guest_vcpu", path, 8),
        ssh_port_base=_as_int(cfg, "ssh_port_base", path, 2222),
        host_uid=_as_int(cfg, "host_uid", path, os.getuid()),
        host_gid=_as_int(cfg, "host_gid", path, os.getgid()),
        guest_uid=_as_int(cfg, "guest_uid", path, 1000),
        guest_gid=_as_int(cfg, "guest_gid", path, 1000),
        ssh_connect_timeout=_as_int(cfg, "ssh_connect_timeout", path, 120),
        ctf_iface=ctf_iface,
    )
