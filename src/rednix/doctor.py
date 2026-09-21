"""Preflight checks. Every failure prints the exact fix."""

from __future__ import annotations

import grp
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .config import Config
from .state import all_events

MIN_STATE_FREE_GIB = 10
WARN_STATE_FREE_GIB = 64

ZFS_DOC_NOTE = (
    "virtiofs on ZFS requires the dataset options xattr=sa and acltype=posixacl "
    "(zfs set xattr=sa acltype=posixacl <dataset>)"
)


@dataclass
class CheckResult:
    name: str
    status: str
    detail: str
    fix: str = ""

    @property
    def failed(self) -> bool:
        return self.status == "fail"

    @property
    def warned(self) -> bool:
        return self.status == "warn"


def _check_kvm() -> CheckResult:
    kvm = Path("/dev/kvm")
    if not kvm.exists():
        return CheckResult(
            "kvm", "fail", "/dev/kvm does not exist",
            "enable virtualisation or load the kvm-intel/kvm-amd module",
        )
    if not (os.access(kvm, os.R_OK) and os.access(kvm, os.W_OK)):
        return CheckResult(
            "kvm", "fail", "/dev/kvm is not readable/writable by your user",
            'add yourself to the kvm group: users.users.<you>.extraGroups = [ "kvm" ]; then re-login',
        )
    return CheckResult("kvm", "ok", "/dev/kvm accessible")


def _check_kvm_group() -> CheckResult:
    kvm = Path("/dev/kvm")
    if kvm.exists() and os.access(kvm, os.R_OK | os.W_OK):
        return CheckResult(
            "kvm-group", "ok", "user can access /dev/kvm (group membership or ACL)"
        )
    try:
        group = grp.getgrnam("kvm")
    except KeyError:
        return CheckResult("kvm-group", "warn", "no kvm group on this system", "")
    if group.gr_gid in os.getgroups():
        return CheckResult("kvm-group", "ok", "user is in the kvm group")
    return CheckResult(
        "kvm-group", "fail", "user is not in the kvm group",
        'users.users.<you>.extraGroups = [ "kvm" ]; then re-login',
    )


def _check_userns() -> CheckResult:
    clone = Path("/proc/sys/kernel/unprivileged_userns_clone")
    if clone.is_file() and clone.read_text().strip() == "0":
        return CheckResult(
            "userns", "fail", "unprivileged user namespaces are disabled",
            "boot.kernel.sysctl.\"kernel.unprivileged_userns_clone\" = 1;",
        )
    maxns = Path("/proc/sys/user/max_user_namespaces")
    if maxns.is_file() and maxns.read_text().strip() == "0":
        return CheckResult(
            "userns", "fail", "user.max_user_namespaces is 0",
            'boot.kernel.sysctl."user.max_user_namespaces" = 28633;',
        )
    if shutil.which("unshare"):
        probe = subprocess.run(["unshare", "-Ur", "true"], capture_output=True)
        if probe.returncode != 0:
            return CheckResult(
                "userns", "fail", f"unshare -Ur failed: {probe.stderr.decode().strip()}",
                "required by virtiofsd; check kernel namespace limits",
            )
    return CheckResult("userns", "ok", "unprivileged user namespaces available (virtiofsd)")


def _check_uid_gid(config: Config) -> CheckResult:
    uid, gid = os.getuid(), os.getgid()
    if uid != config.host_uid or gid != config.host_gid:
        return CheckResult(
            "uid-gid", "fail",
            f"host ids are {uid}:{gid} but the share translation is built for "
            f"{config.host_uid}:{config.host_gid}",
            f"set host_uid = {uid} and host_gid = {gid} in {config.config_path}, "
            f"or build with matching hostUid/hostGid flake args, then rednix build --pin",
        )
    return CheckResult("uid-gid", "ok", f"host ids {uid}:{gid} match the share translation")


def _check_space(config: Config) -> CheckResult:
    results = []
    for label, path in (("state root", config.state_root), ("share root", config.share_root)):
        try:
            usage = shutil.disk_usage(path if path.exists() else path.parent)
        except OSError as exc:
            results.append(CheckResult("space", "warn", f"{label}: {exc}"))
            continue
        free_gib = usage.free / (1024 ** 3)
        if free_gib < MIN_STATE_FREE_GIB:
            results.append(CheckResult(
                "space", "fail", f"{label}: {free_gib:.1f} GiB free",
                f"free space; the guest closure needs tens of GiB",
            ))
        elif free_gib < WARN_STATE_FREE_GIB:
            results.append(CheckResult(
                "space", "warn", f"{label}: {free_gib:.1f} GiB free",
                "the full pentest store image plus state.img can exceed this",
            ))
        else:
            results.append(CheckResult("space", "ok", f"{label}: {free_gib:.1f} GiB free"))
    return max(results, key=lambda r: {"ok": 0, "warn": 1, "fail": 2}[r.status])


def _check_share_root(config: Config) -> CheckResult:
    share = config.share_root
    if not share.exists():
        return CheckResult(
            "share-root", "fail", f"{share} does not exist",
            f"mkdir -p {share} or set share_root in {config.config_path}",
        )
    if share.is_symlink():
        return CheckResult(
            "share-root", "fail", f"{share} is a symlink",
            "the share root must be a real directory so it cannot smuggle "
            "host paths into the guest",
        )
    fs_type = ""
    try:
        with open("/proc/mounts", encoding="utf-8") as mounts:
            for line in mounts:
                fields = line.split()
                if len(fields) >= 3 and Path(fields[1]) == share:
                    fs_type = fields[2]
                    break
    except OSError:
        pass
    if fs_type == "zfs":
        zfs = shutil.which("zfs")
        dataset = subprocess.run(
            ["zfs", "get", "-H", "-o", "value", "xattr", str(share)], capture_output=True, text=True
        )
        acl = subprocess.run(
            ["zfs", "get", "-H", "-o", "value", "acltype", str(share)], capture_output=True, text=True
        )
        if zfs and (dataset.stdout.strip() != "sa" or acl.stdout.strip() != "posixacl"):
            return CheckResult("share-root", "fail", "ZFS dataset lacks xattr=sa/acltype=posixacl", ZFS_DOC_NOTE)
        if not zfs:
            return CheckResult("share-root", "warn", f"{share} is on ZFS; could not verify dataset options", ZFS_DOC_NOTE)
    return CheckResult("share-root", "ok", f"{share} is a real directory ({fs_type or 'unknown fs'})")


def _check_pinned_runner(config: Config) -> CheckResult:
    candidates = [config.gcroots_dir / "guestRunner"]
    for event in all_events(config):
        candidates.append(config.event_dir(event) / "current")
        candidates.append(config.gcroots_dir / event)
    for candidate in candidates:
        if candidate.is_symlink() and candidate.resolve().is_dir():
            return CheckResult("runner", "ok", f"pinned runner: {candidate.resolve()}")
    return CheckResult(
        "runner", "fail", "no pinned runner found",
        "rednix build --pin",
    )


def _check_keypair(config: Config) -> CheckResult:
    key = config.private_key
    if not key.is_file():
        return CheckResult(
            "keypair", "warn", f"{key} missing",
            "rednix init generates it; its public half is injected into the guest at build time",
        )
    if not config.public_key.is_file():
        return CheckResult(
            "keypair", "warn", f"{config.public_key} missing",
            "rednix init regenerates it from the private key",
        )
    if not _key_matches_public(config, key):
        return CheckResult(
            "keypair", "fail", "private key does not match the public key baked into the guest",
            "rednix build --pin re-bakes the current key into the runner",
        )
    return CheckResult("keypair", "ok", f"{key} matches {config.public_key}")


def _key_matches_public(config: Config, key: Path) -> bool:
    ssh_keygen = shutil.which("ssh-keygen")
    if not ssh_keygen:
        return True
    derived = subprocess.run([ssh_keygen, "-y", "-f", str(key)], capture_output=True, text=True)
    recorded = config.public_key.read_text(encoding="utf-8").split()
    actual = derived.stdout.split()
    return bool(actual) and [actual[0], actual[1]] == recorded[:2]


def _check_tools() -> CheckResult:
    missing = [tool for tool in ("waypipe", "vncviewer") if not shutil.which(tool)]
    if missing:
        return CheckResult(
            "host-tools", "warn", f"not on PATH: {', '.join(missing)}",
            "rednix gui needs waypipe (client); rednix desktop needs tigervnc's vncviewer",
        )
    return CheckResult("host-tools", "ok", "waypipe and vncviewer available")


def run_checks(config: Config, offline: bool = False) -> list[CheckResult]:
    checks = [
        _check_kvm(),
        _check_kvm_group(),
        _check_userns(),
        _check_uid_gid(config),
        _check_space(config),
        _check_share_root(config),
        _check_pinned_runner(config),
        _check_keypair(config),
        _check_tools(),
    ]
    if offline:
        checks.append(CheckResult("offline", "ok", "doctor performs no network access; all checks are local"))
    return checks


def report(checks: list[CheckResult]) -> bool:
    glyphs = {"ok": "✔", "warn": "⚠", "fail": "✖"}
    for check in checks:
        line = f"{glyphs[check.status]} {check.name}: {check.detail}"
        print(line)
        if check.fix and check.status != "ok":
            print(f"  fix: {check.fix}")
    return not any(check.failed for check in checks)
