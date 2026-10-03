"""On-demand guest services exposed through managed host-loopback SSH tunnels."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
import time
import urllib.error
import urllib.request

from . import apps, menu, ssh, state
from .config import Config
from .state import StateError


@dataclass(frozen=True)
class Service:
    name: str
    title: str
    port: int
    health_path: str


SERVICES = (
    Service("exploitfarm", "ExploitFarm — exploit coordination", 5050, "/api/status"),
    Service("tulip", "Tulip — traffic analysis", 3000, "/api/tags"),
)


def select(names: list[str]) -> list[Service]:
    if names == ["all"]:
        return list(SERVICES)
    known = {s.name: s for s in SERVICES}
    unknown = [name for name in names if name not in known]
    if unknown:
        raise StateError(f"unknown service: {', '.join(unknown)}; use rednix services --list")
    return [known[name] for name in dict.fromkeys(names)]


def _healthy(opener, url: str) -> bool:
    try:
        with opener.open(url, timeout=1) as response:
            return response.status < 500
    except urllib.error.HTTPError as exc:
        return exc.code < 500
    except (OSError, urllib.error.URLError):
        return False


def forward(config: Config, event: str, selected: list[Service],
            local_port: int | None = None, start: bool = True) -> int:
    if local_port is not None and (len(selected) != 1 or not 1 <= local_port <= 65535):
        raise StateError("--port requires one service and a port from 1 to 65535")
    apps.require_running(config, event)
    ports = []
    for service in selected:
        port = local_port if local_port is not None else state.allocate_free_port(
            service.port, avoid=set(ports))
        ports.append(port)
    if start:
        for service in selected:
            print(f"Starting {service.name} in {event}…", flush=True)
            code = ssh.run(config, event, [service.name, "start"])
            if code:
                raise StateError(
                    f"failed to start {service.name}; inspect: rednix exec {event} -- {service.name} logs"
                )
    # A dedicated SSH connection makes tunnel lifetime match this command.
    # Reusing ControlPersist would leave forwards on the shared master after exit.
    argv = ssh.ssh_args(config, event, [
        "-N", "-o", "ExitOnForwardFailure=yes", "-o", "ControlMaster=no",
        "-o", "ControlPath=none", "-o", "ControlPersist=no",
    ])
    for service, port in zip(selected, ports):
        argv[1:1] = ["-L", f"127.0.0.1:{port}:127.0.0.1:{service.port}"]
    try:
        tunnel = subprocess.Popen(argv)
    except OSError as exc:
        raise StateError(f"could not start SSH tunnel: {exc}") from exc
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        pending = list(zip(selected, ports))
        deadline = time.monotonic() + 30
        while pending:
            if tunnel.poll() is not None:
                raise StateError(
                    f"SSH tunnel exited (code {tunnel.returncode}); check the local port is free "
                    f"and try: rednix shell {event}"
                )
            pending = [(service, port) for service, port in pending if not _healthy(
                opener, f"http://127.0.0.1:{port}{service.health_path}")]
            if not pending:
                break
            if time.monotonic() >= deadline:
                raise StateError(
                    "services did not respond through the tunnel within 30 s; inspect: "
                    + "; ".join(f"rednix exec {event} -- {s.name} logs" for s, _ in pending)
                )
            time.sleep(0.2)
        for service, port in zip(selected, ports):
            print(f"{service.name}: http://127.0.0.1:{port}", flush=True)
        print("Open these URLs in your host browser. Ctrl+C closes the tunnels; "
              "services keep running in the guest.", flush=True)
        return tunnel.wait()
    finally:
        if tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait()


def run(config: Config, event: str, names: list[str], local_port: int | None = None,
        start: bool = True) -> int:
    if not names:
        index = menu.choose(f"Web services — {event}",
                            [s.title for s in SERVICES] + ["All services"])
        if index is None:
            return 0
        names = [SERVICES[index].name] if index < len(SERVICES) else ["all"]
    return forward(config, event, select(names), local_port, start)
