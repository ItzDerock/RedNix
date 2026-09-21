"""VM lifecycle: start, stop, destroy, snapshots, status, logs, warm-up.

The launcher never evaluates the flake here; it only execs runner binaries
from store paths that were pinned by `rednix build`. Per-event QEMU
arguments (SSH hostfwd port, NIC profile) are written to ./qemu-extra-args
in the event directory and picked up by the runner's extraArgsScript.
"""

from __future__ import annotations

import datetime as _dt
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import state
from .config import NETWORK_PROFILES, Config
from .ssh import ensure_keypair, ssh_args, write_ssh_config
from .state import (
    StateError,
    cleanup_stale_sockets,
    event_lock,
    instance_path,
    pid_alive,
    read_instance,
    require_routable_name,
    share_dir_for,
    socket_has_listener,
    validate_event_name,
    write_instance,
    allocate_free_port,
)

NAT_MAC = "02:00:00:00:00:01"
ROUTED_MAC = "02:00:00:00:00:02"
VIRTIOFS_SOCKET = "rednix-virtiofs-work.sock"
QMP_SOCKET = "rednix.sock"
SHUTDOWN_TIMEOUT = 90
KILL_GRACE = 15
READINESS_POLL_INTERVAL = 0.5


class Runner:
    def __init__(self, path: Path):
        self.path = path
        self.microvm_run = path / "bin" / "microvm-run"
        self.microvm_shutdown = path / "bin" / "microvm-shutdown"
        # Direct virtiofsd invocation (no supervisord) — the upstream
        # virtiofsd-run cannot start as an unprivileged user.
        self.virtiofsd_run = path / "bin" / "rednix-virtiofsd-work"

    def validate(self) -> None:
        for binary in (self.microvm_run, self.virtiofsd_run):
            if not binary.exists():
                raise StateError(
                    f"runner {self.path} is missing {binary.name}; re-run: rednix build --pin"
                )


def resolve_runner(config: Config, event: str) -> Runner:
    edir = config.event_dir(event)
    candidates = [
        edir / "current",
        config.gcroots_dir / event,
        config.gcroots_dir / "guestRunner",
    ]
    for candidate in candidates:
        if candidate.is_symlink() or candidate.is_dir():
            target = candidate.resolve()
            if target.is_dir():
                runner = Runner(target)
                runner.validate()
                return runner
    raise StateError(
        "no runner pinned for this event; run: rednix build --pin "
        "(offline starts never evaluate the flake)"
    )


def qemu_extra_args(network: str, ssh_port: int, event: str,
                    mem: int | None = None, cpus: int | None = None) -> str:
    if network == "nat":
        nic = (
            f"-netdev user,id=rednix0,hostfwd=tcp:127.0.0.1:{ssh_port}-:22 "
            f"-device virtio-net-pci,netdev=rednix0,mac={NAT_MAC}"
        )
    elif network == "routed":
        tap = f"rednix-{event}"
        require_routable_name(event)
        nic = (
            f"-netdev tap,id=rednix0,ifname={tap},script=no,downscript=no "
            f"-device virtio-net-pci,netdev=rednix0,mac={ROUTED_MAC}"
        )
    else:
        raise StateError(f"unknown network profile {network!r}; expected one of {NETWORK_PROFILES}")

    overrides = ""
    if mem is not None:
        overrides += f"-m {mem} "
    if cpus is not None:
        overrides += f"-smp {cpus} "
    return (overrides + nic).strip()


def _open_log(event_dir: Path, name: str) -> int:
    path = event_dir / name
    if path.exists():
        return os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, f"# {_dt.datetime.now().isoformat()} {name}\n".encode())
    return fd


def _wait_for_socket(path: Path, timeout: float) -> bool:
    # Existence only: connecting to a vhost-user socket would be treated as
    # the master connection, and its disconnect shuts virtiofsd down.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_socket():
            return True
        time.sleep(0.2)
    return False


def _wait_for_port(port: int, timeout: float) -> bool:
    # The QEMU hostfwd listener accepts TCP immediately, before the guest's
    # sshd exists, so readiness means receiving an SSH banner, not a
    # successful connect.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(2.0)
            try:
                sock.connect(("127.0.0.1", port))
                banner = sock.recv(64)
                if banner.startswith(b"SSH-"):
                    return True
            except (OSError, socket.timeout):
                pass
        time.sleep(READINESS_POLL_INTERVAL)
    return False


def _terminate_process_group(pid: int, grace: float = KILL_GRACE) -> None:
    try:
        group = os.getpgid(pid)
    except ProcessLookupError:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(group, sig)
        except ProcessLookupError:
            return
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            try:
                os.killpg(group, 0)
            except ProcessLookupError:
                return
            time.sleep(0.2)
        grace = 2


def _teardown(config: Config, event: str, qemu_pid: int | None,
              virtiofsd_pid: int | None) -> None:
    edir = config.event_dir(event)
    if qemu_pid and pid_alive(qemu_pid):
        shutdown = resolve_runner(config, event).microvm_shutdown
        if shutdown.exists():
            subprocess.run([str(shutdown)], cwd=edir, timeout=SHUTDOWN_TIMEOUT,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if qemu_pid and pid_alive(qemu_pid):
        _terminate_process_group(qemu_pid, grace=KILL_GRACE)
    if virtiofsd_pid and pid_alive(virtiofsd_pid):
        _terminate_process_group(virtiofsd_pid, grace=5)
    cleanup_stale_sockets(edir)


def _tail(path: Path, lines: int = 40) -> str:
    if not path.is_file():
        return ""
    data = path.read_bytes().splitlines()
    return "\n".join(line.decode(errors="replace") for line in data[-lines:])


def start(config: Config, event: str, network: str | None = None, mem: int | None = None,
          cpus: int | None = None, share: str | None = None, fresh: bool = False) -> dict:
    event = validate_event_name(event)
    network = network or config.default_network
    if network not in NETWORK_PROFILES:
        raise StateError(f"unknown network profile {network!r}; expected one of {NETWORK_PROFILES}")
    if network == "routed":
        require_routable_name(event)
        tap = f"rednix-{event}"
        if not (Path("/sys/class/net") / tap).exists():
            raise StateError(
                f"TAP device {tap} does not exist on the host; run: sudo rednix net up {event}"
            )

    edir = config.event_dir(event)
    with event_lock(edir):
        existing = read_instance(edir) or {}
        if pid_alive(existing.get("pid")):
            raise StateError(
                f"event {event!r} is already running (pid {existing['pid']}); use rednix stop first"
            )
        cleanup_stale_sockets(edir)
        ssh_port = allocate_free_port(config.ssh_port_base)

        if fresh and (edir / "state.img").exists():
            (edir / "state.img").unlink()

        runner = resolve_runner(config, event)

        target = share_dir_for(config, event, share)
        target.mkdir(parents=True, exist_ok=True)
        link = edir / "work"
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target)

        (edir / "qemu-extra-args").write_text(
            qemu_extra_args(network, ssh_port, event, mem=mem, cpus=cpus) + "\n",
            encoding="utf-8",
        )

        instance = {
            "event": event,
            "created_at": existing.get("created_at")
            or _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "runner": str(runner.path),
            "network": network,
            "ssh_port": ssh_port,
            "share": str(target),
            "mem_mib": mem or config.guest_mem_mib,
            "cpus": cpus or config.guest_vcpu,
            "pid": None,
            "virtiofsd_pid": None,
        }

        virtiofsd_log = _open_log(edir, "virtiofsd.log")
        virtiofsd = subprocess.Popen(
            [str(runner.virtiofsd_run)],
            cwd=edir,
            stdout=virtiofsd_log,
            stderr=virtiofsd_log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        os.close(virtiofsd_log)
        if not _wait_for_socket(edir / VIRTIOFS_SOCKET, timeout=15):
            _terminate_process_group(virtiofsd.pid, grace=5)
            raise StateError(
                "virtiofsd did not come up; tail of virtiofsd.log:\n"
                + _tail(edir / "virtiofsd.log")
            )

        vm_log = _open_log(edir, "vm.log")
        qemu = subprocess.Popen(
            [str(runner.microvm_run)],
            cwd=edir,
            stdout=vm_log,
            stderr=vm_log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
        os.close(vm_log)

        # Record the instance and regenerate ssh_config BEFORE readiness: the
        # per-event Host block carries the ssh port the readiness probes need.
        instance["virtiofsd_pid"] = virtiofsd.pid
        write_instance(edir, instance)
        write_ssh_config(config)

        def handle_signal(signum, _frame):
            _teardown(config, event, qemu.pid, virtiofsd.pid)
            sys.exit(128 + signum)

        previous_int = signal.signal(signal.SIGINT, handle_signal)
        previous_term = signal.signal(signal.SIGTERM, handle_signal)
        try:
            ready = _wait_for_port(ssh_port, timeout=config.ssh_connect_timeout)
            if ready:
                # sshd is socket-activated and answers before the guest's bind
                # mounts settle, and some units (sshd.service, nscd) crash-loop
                # without blocking sessions; readiness is therefore checked
                # concretely: a working exec, then the state bind mounts up.
                deadline = time.monotonic() + config.ssh_connect_timeout
                while time.monotonic() < deadline:
                    probe = subprocess.run(
                        ssh_args(config, event) + ["--", "true"],
                        capture_output=True, text=True, timeout=15,
                    )
                    if probe.returncode == 0:
                        break
                    time.sleep(2.0)
                else:
                    ready = False
            if ready:
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    probe = subprocess.run(
                        ssh_args(config, event)
                        + ["--", "findmnt -n /home/rednix"],
                        capture_output=True, text=True, timeout=15,
                    )
                    if probe.returncode == 0 and "/dev/vdb" in probe.stdout:
                        break
                    time.sleep(2.0)
                else:
                    ready = False
        finally:
            signal.signal(signal.SIGINT, previous_int)
            signal.signal(signal.SIGTERM, previous_term)

        if not ready:
            _teardown(config, event, qemu.pid, virtiofsd.pid)
            raise StateError(
                f"guest did not open SSH port {ssh_port} within "
                f"{config.ssh_connect_timeout}s; tail of vm.log:\n" + _tail(edir / "vm.log")
            )

        instance["pid"] = qemu.pid
        instance["virtiofsd_pid"] = virtiofsd.pid
        write_instance(edir, instance)
        write_ssh_config(config)
        return instance


def stop(config: Config, event: str) -> dict | None:
    event = validate_event_name(event)
    edir = config.event_dir(event)
    with event_lock(edir):
        instance = read_instance(edir)
        if instance is None:
            print(f"event {event!r} has no state to stop")
            return None
        qemu_pid = instance.get("pid")
        vfd_pid = instance.get("virtiofsd_pid")

        if pid_alive(qemu_pid):
            shutdown = resolve_runner(config, event).microvm_shutdown
            try:
                subprocess.run([str(shutdown)], cwd=edir, timeout=SHUTDOWN_TIMEOUT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                pass
            deadline = time.monotonic() + SHUTDOWN_TIMEOUT
            while time.monotonic() < deadline and pid_alive(qemu_pid):
                time.sleep(0.5)
            if pid_alive(qemu_pid):
                _terminate_process_group(qemu_pid)
        if pid_alive(vfd_pid):
            _terminate_process_group(vfd_pid, grace=5)

        cleanup_stale_sockets(edir)
        # Master connections to the same port must not survive a restart;
        # they would multiplex onto the dead previous VM.
        if config.ssh_sockets_dir.is_dir():
            for control in config.ssh_sockets_dir.glob(f"ssh-*:{instance.get('ssh_port', 0)}"):
                control.unlink(missing_ok=True)
        instance["pid"] = None
        instance["virtiofsd_pid"] = None
        write_instance(edir, instance)
        return instance


def destroy(config: Config, event: str, purge_share: bool = False,
            assume_yes: bool = False) -> None:
    event = validate_event_name(event)
    edir = config.event_dir(event)
    if not edir.is_dir():
        raise StateError(f"event {event!r} does not exist")

    instance = read_instance(edir) or {}
    share = instance.get("share") or str(share_dir_for(config, event))

    if pid_alive(instance.get("pid")):
        stop(config, event)

    print(f"This removes VM state for {event!r}: {edir}")
    print(f"Shared files stay on the host: {share}"
          + (" (--purge-share will delete them)" if purge_share else ""))
    if not assume_yes:
        answer = input("Proceed? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("aborted")
            return

    with event_lock(edir):
        shutil.rmtree(edir)
    gcroot = config.gcroots_dir / event
    if gcroot.is_symlink() or gcroot.exists():
        gcroot.unlink()
    if purge_share:
        share_path = Path(share)
        if share_path.resolve().parent == Path(config.share_root).resolve() and share_path.name == event:
            shutil.rmtree(share_path)
        else:
            print(f"refusing to purge unexpected share path {share}", file=sys.stderr)
    write_ssh_config(config)


def _disk_usage_bytes(path: Path) -> int:
    total = 0
    for dirpath, _dirnames, filenames in os.walk(path):
        for filename in filenames:
            file_path = Path(dirpath) / filename
            try:
                if not file_path.is_symlink():
                    total += file_path.stat().st_size
            except OSError:
                pass
    return total


def status(config: Config, event: str | None = None) -> list[dict]:
    events = [validate_event_name(event)] if event else state.all_events(config)
    rows = []
    for name in events:
        edir = config.event_dir(name)
        instance = read_instance(edir) or {}
        rows.append({
            "event": name,
            "running": pid_alive(instance.get("pid")),
            "network": instance.get("network"),
            "ssh_port": instance.get("ssh_port"),
            "pid": instance.get("pid"),
            "share": instance.get("share"),
            "created_at": instance.get("created_at"),
            "size_mib": round(_disk_usage_bytes(edir) / (1024 * 1024)) if edir.is_dir() else 0,
        })
    return rows


def snapshot(config: Config, event: str, name: str) -> Path:
    event = validate_event_name(event)
    edir = config.event_dir(event)
    instance = read_instance(edir) or {}
    if pid_alive(instance.get("pid")):
        raise StateError("stop the VM before snapshotting")
    source = edir / "state.img"
    if not source.is_file():
        raise StateError(f"{source} does not exist")
    snapshots = edir / "snapshots"
    snapshots.mkdir(exist_ok=True)
    target = snapshots / f"{name}.img"
    shutil.copy2(source, target)
    return target


def restore(config: Config, event: str, name: str) -> None:
    event = validate_event_name(event)
    edir = config.event_dir(event)
    instance = read_instance(edir) or {}
    if pid_alive(instance.get("pid")):
        raise StateError("stop the VM before restoring a snapshot")
    source = edir / "snapshots" / f"{name}.img"
    if not source.is_file():
        raise StateError(f"snapshot {name!r} does not exist for event {event!r}")
    shutil.copy2(source, edir / "state.img")


def logs(config: Config, event: str, follow: bool = False) -> None:
    event = validate_event_name(event)
    path = config.event_dir(event) / "vm.log"
    if not path.is_file():
        raise StateError(f"no vm.log for event {event!r}")
    with open(path, "r", errors="replace") as fp:
        if not follow:
            sys.stdout.write(fp.read())
            return
        fp.seek(0, os.SEEK_END)
        try:
            while True:
                line = fp.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    time.sleep(0.5)
        except KeyboardInterrupt:
            pass


def warm(config: Config, event: str) -> None:
    from .ssh import run as ssh_run

    event = validate_event_name(event)
    instance = start(config, event, network="nat")
    try:
        print("running first-boot warm-up (msfdb init, docker check)...")
        ssh_run(config, event, ["bash", "-lc", "msfdb init || msfdb status; docker images || true"])
        warm_script = config.state_root / "warm.sh"
        if warm_script.is_file():
            print(f"running warm script: {warm_script}")
            subprocess.run(
                ["scp", "-F", str(config.ssh_config), str(warm_script), f"rednix-{event}:warm.sh"],
                check=False,
            )
            ssh_run(config, event, ["bash", "-lc", "bash ~/warm.sh"])
    finally:
        stop(config, event)
        print(f"warm-up complete; instance {event!r} stopped (state preserved)")
