"""Host-side routed-profile networking: persistent TAP device plus nftables scope enforcement."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .config import Config
from .state import StateError, require_routable_name, validate_event_name

GUEST_CIDR = "10.7.0.0/24"
HOST_TAP_ADDR = "10.7.0.1/24"
GUEST_IP = "10.7.0.2"
TAP_PREFIX = "rednix-"

NET_STATE = "net.json"
RUN_DIR = Path("/run/rednix")
IP_FORWARD_PROC = Path("/proc/sys/net/ipv4/ip_forward")
NET_CLASS_DIR = Path("/sys/class/net")

PRIVATE_RANGES = (
    "127.0.0.0/8",
    "10.0.0.0/8",
    "172.16.0.0/12",
    "192.168.0.0/16",
    "169.254.0.0/16",
    "100.64.0.0/10",
)

ALLOW_ENTRY_RE = re.compile(r"^[0-9./]+:[0-9]+$")

NIXOS_PACKAGES = {"nft": "nftables", "ip": "iproute2"}

ROOT_HINT = "error: this command must run as root; use: sudo rednix net ..."


def _run(
    cmd: list[str],
    input_text: str | None = None,
    check: bool = True,
    ignore_stderr: str | None = None,
) -> subprocess.CompletedProcess:
    if input_text is not None:
        proc = subprocess.run(cmd, input=input_text, capture_output=True, text=True)
    else:
        proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    if check and proc.returncode != 0 and (ignore_stderr is None or ignore_stderr.lower() not in proc.stderr.lower()):
        detail = proc.stderr.strip() or proc.stdout.strip() or "no error output"
        raise StateError(f"{' '.join(cmd)}: {detail}")
    return proc


def _require_bin(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        package = NIXOS_PACKAGES[name]
        raise StateError(f"required binary {name!r} not found in PATH; install the nixos package {package!r}")
    return path


def _read_ip_forward() -> str:
    return IP_FORWARD_PROC.read_text(encoding="utf-8").strip()


def _write_ip_forward(value: str) -> None:
    IP_FORWARD_PROC.write_text(f"{value}\n", encoding="utf-8")


def _read_net_state(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise StateError(f"{path}: unreadable net record: {exc}") from exc


def _write_net_state(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _load_profile(config: Config, event: str) -> dict:
    path = config.event_dir(event) / NET_STATE
    data = _read_net_state(path)
    if data is None:
        raise StateError(f"the routed profile is not set up for event {event!r}; run: sudo rednix net up {event}")
    if not data.get("iface") or not data.get("tap"):
        raise StateError(f"{path}: missing 'iface' or 'tap'; re-run: sudo rednix net up {event}")
    data.setdefault("allows", [])
    data.setdefault("callbacks", [])
    return data


def _reapply(config: Config, event: str, data: dict) -> None:
    nft = _require_bin("nft")
    ruleset = build_ruleset(
        table=str(data["tap"]),
        tap=str(data["tap"]),
        iface=str(data["iface"]),
        allows=[str(entry) for entry in data["allows"]],
        callbacks=[int(port) for port in data["callbacks"]],
    )
    _run([nft, "-f", "-"], input_text=ruleset)


# Pure and unit-tested: returns the complete nftables script text without touching the system.
def build_ruleset(table: str, tap: str, iface: str, allows: list[str], callbacks: list[int]) -> str:
    lines = [
        "#!/usr/sbin/nft -f",
        f"# RedNix routed profile — table inet {table}",
        "# create-then-delete makes re-running `sudo rednix net up` idempotent",
        "",
        f"add table inet {table}",
        f"delete table inet {table}",
        f"add table inet {table} {{",
        "",
        "    chain forward {",
        "        type filter hook forward priority 0; policy drop;",
        "",
        "        ct state established,related accept",
        "",
        "        # scope enforcement: guest IPv6 is dropped entirely",
        f'        meta nfproto ipv6 iifname "{tap}" drop',
        "",
        "        # callbacks: host ports DNAT'd to the guest",
    ]
    for port in callbacks:
        lines.append(f'        oifname "{tap}" ip daddr {GUEST_IP} tcp dport {port} accept')
    lines += [
        "",
        "        # allow-list: event destinations punched through the scope drop below",
    ]
    for entry in allows:
        cidr, _, port = entry.partition(":")
        lines.append(f'        iifname "{tap}" ip daddr {cidr} tcp dport {port} accept')
        lines.append(f'        iifname "{tap}" ip daddr {cidr} udp dport {port} accept')
    ranges = ", ".join(PRIVATE_RANGES)
    lines += [
        "",
        "        # scope enforcement: private and link-local ranges are unreachable from the guest",
        f'        iifname "{tap}" ip daddr {{ {ranges} }} drop',
        "",
        "        # egress: guest traffic toward the CTF interface",
        f'        iifname "{tap}" oifname "{iface}" accept',
        "    }",
        "",
        "    chain input {",
        "        type filter hook input priority 0; policy accept;",
        "",
        "        # host services are unreachable from the guest",
        f'        iifname "{tap}" ip saddr {GUEST_CIDR} ct state established,related accept',
        f'        iifname "{tap}" ip saddr {GUEST_CIDR} drop',
        "    }",
        "",
        "    chain prerouting {",
        "        type nat hook prerouting priority -100;",
        "",
        "        # callbacks: DNAT host ports to the guest",
    ]
    for port in callbacks:
        lines.append(f'        iifname "{iface}" tcp dport {port} dnat ip to {GUEST_IP}:{port}')
    lines += [
        "    }",
        "",
        "    chain postrouting {",
        "        type nat hook postrouting priority 100;",
        "",
        "        # egress: masquerade guest traffic leaving via the CTF interface",
        f'        oifname "{iface}" ip saddr {GUEST_CIDR} masquerade',
        "    }",
        "}",
        "",
    ]
    return "\n".join(lines)


def net_up(config: Config, event: str, iface: str | None = None) -> int:
    event = validate_event_name(event)
    require_routable_name(event)
    tap = TAP_PREFIX + event

    if os.geteuid() != 0:
        print(ROOT_HINT, file=sys.stderr)
        return 1

    iface = iface or config.ctf_iface
    if not iface:
        print(
            f"error: no CTF interface given; use: rednix net up {event} --iface <if>, "
            "or set 'ctf_iface' in config.toml",
            file=sys.stderr,
        )
        return 1
    if not (NET_CLASS_DIR / iface).exists():
        print(f"error: interface {iface!r} not found in /sys/class/net", file=sys.stderr)
        return 1

    ip = _require_bin("ip")
    nft = _require_bin("nft")

    _run(
        [ip, "tuntap", "add", "dev", tap, "mode", "tap", "owner", str(config.host_uid), "group", str(config.host_gid)],
        ignore_stderr="exists",
    )
    _run([ip, "addr", "replace", HOST_TAP_ADDR, "dev", tap])
    _run([ip, "link", "set", tap, "up"])

    RUN_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    prev_path = RUN_DIR / f"{tap}.ip_forward.prev"
    was = _read_ip_forward()
    if not prev_path.exists():
        prev_path.write_text(was + "\n", encoding="utf-8")
    _write_ip_forward("1")

    edir = config.event_dir(event)
    existing = _read_net_state(edir / NET_STATE) or {}
    allows = [str(entry) for entry in existing.get("allows", [])]
    callbacks = [int(port) for port in existing.get("callbacks", [])]
    ruleset = build_ruleset(table=tap, tap=tap, iface=iface, allows=allows, callbacks=callbacks)
    _run([nft, "-f", "-"], input_text=ruleset)

    _write_net_state(
        edir / NET_STATE,
        {"iface": iface, "tap": tap, "allows": allows, "callbacks": callbacks},
    )

    print(f"routed profile is up for event {event!r}")
    print(f"  tap:       {tap} ({HOST_TAP_ADDR}), guest {GUEST_IP} inside {GUEST_CIDR}")
    print(f"  egress:    {GUEST_CIDR} masquerades via {iface}")
    print(f"  nftables:  table inet {tap} (scope-enforced)")
    if was != "1":
        print(f"  note:      net.ipv4.ip_forward was {was}, now host-wide 1; 'rednix net down' restores it")
    if allows:
        print(f"  allows:    {', '.join(allows)}")
    if callbacks:
        print(f"  callbacks: {', '.join(str(port) for port in callbacks)}")
    return 0


def net_down(config: Config, event: str) -> int:
    event = validate_event_name(event)
    require_routable_name(event)
    tap = TAP_PREFIX + event

    if os.geteuid() != 0:
        print(ROOT_HINT, file=sys.stderr)
        return 1

    nft = _require_bin("nft")
    ip = _require_bin("ip")

    removed = []
    if _run([nft, "delete", "table", "inet", tap], check=False).returncode == 0:
        removed.append(f"table inet {tap}")
    if _run([ip, "link", "delete", "dev", tap], check=False).returncode == 0:
        removed.append(f"tap device {tap}")

    restored = ""
    prev_path = RUN_DIR / f"{tap}.ip_forward.prev"
    if prev_path.is_file():
        value = prev_path.read_text(encoding="utf-8").strip()
        if value:
            _write_ip_forward(value)
            restored = "net.ipv4.ip_forward restored to its previous value"
        prev_path.unlink()

    print(f"routed profile is down for event {event!r}: removed {', '.join(removed) if removed else 'nothing (already down)'}")
    if restored:
        print(restored)
    return 0


def net_show(config: Config, event: str) -> int:
    event = validate_event_name(event)
    require_routable_name(event)
    tap = TAP_PREFIX + event

    if os.geteuid() != 0:
        print(ROOT_HINT, file=sys.stderr)
        return 1

    nft = _require_bin("nft")
    proc = _run([nft, "list", "table", "inet", tap], check=False)
    if proc.returncode == 0:
        print(proc.stdout.rstrip())
        print()
    else:
        print(f"nftables: table inet {tap} is not present (run: sudo rednix net up {event})")

    data = _read_net_state(config.event_dir(event) / NET_STATE)
    if data is None:
        print(f"the routed profile is not set up for event {event!r}")
        return 0

    iface = str(data.get("iface", "?"))
    allows = [str(entry) for entry in data.get("allows", [])]
    callbacks = [int(port) for port in data.get("callbacks", [])]
    forward = _read_ip_forward()

    print(f"routed profile for event {event!r}:")
    print(f"  interface:  {iface} (CTF uplink)")
    print(f"  tap:        {data.get('tap', tap)} ({HOST_TAP_ADDR})")
    print(f"  guest:      {GUEST_IP} inside {GUEST_CIDR}")
    print(f"  masquerade: {GUEST_CIDR} leaving via {iface}")
    print(f"  ip_forward: {forward}")
    if allows:
        print(f"  allow-list: {len(allows)} destination(s), tcp+udp, punched through the private-range drop:")
        for entry in allows:
            print(f"    {entry}")
    else:
        print("  allow-list: none (guest reaches the CTF network only; private ranges stay dropped)")
    if callbacks:
        print(f"  callbacks:  {len(callbacks)} port(s) DNAT'd from {iface} to the guest:")
        for port in callbacks:
            print(f"    {iface}:{port} -> {GUEST_IP}:{port}")
    else:
        print("  callbacks:  none (reverse shells have no inbound path)")
    return 0


def net_allow(config: Config, event: str, entry: str) -> int:
    event = validate_event_name(event)
    require_routable_name(event)

    if os.geteuid() != 0:
        print(ROOT_HINT, file=sys.stderr)
        return 1

    if not ALLOW_ENTRY_RE.fullmatch(entry):
        raise StateError(f"invalid allow entry {entry!r}: expected CIDR:PORT, e.g. 10.20.0.5/32:443")

    _require_bin("nft")
    data = _load_profile(config, event)
    allows = [str(existing) for existing in data["allows"]]
    if entry in allows:
        print(f"{entry} is already allowed for event {event!r}")
        return 0
    allows.append(entry)
    data["allows"] = allows
    _write_net_state(config.event_dir(event) / NET_STATE, data)
    _reapply(config, event, data)
    print(f"allowed {entry} (tcp+udp) for event {event!r}; ruleset re-applied")
    return 0


def net_callback(config: Config, event: str, port: int) -> int:
    event = validate_event_name(event)
    require_routable_name(event)

    if os.geteuid() != 0:
        print(ROOT_HINT, file=sys.stderr)
        return 1

    if not 1 <= port <= 65535:
        raise StateError(f"invalid callback port {port}: must be between 1 and 65535")

    _require_bin("nft")
    data = _load_profile(config, event)
    callbacks = [int(existing) for existing in data["callbacks"]]
    if port in callbacks:
        print(f"callback port {port} is already DNAT'd for event {event!r}")
        return 0
    callbacks.append(port)
    data["callbacks"] = callbacks
    _write_net_state(config.event_dir(event) / NET_STATE, data)
    _reapply(config, event, data)
    print(f"callback port {port} DNAT'd to {GUEST_IP}:{port} for event {event!r}; ruleset re-applied")
    return 0
