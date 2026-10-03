"""rednix command-line interface."""

from __future__ import annotations

import argparse
import sys
import time

from . import __version__, config as config_mod, doctor as doctor_mod, nix as nix_mod
from . import ssh as ssh_mod
from . import vm as vm_mod
from .config import ConfigError, Config, load_config
from .state import StateError, all_events, default_event


def _fail(message: str) -> "NoReturn":
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def cmd_init(args, config: Config) -> int:
    config.state_root.mkdir(parents=True, exist_ok=True)
    config.events_dir.mkdir(parents=True, exist_ok=True)
    config.gcroots_dir.mkdir(parents=True, exist_ok=True)
    config.ssh_sockets_dir.mkdir(parents=True, exist_ok=True)
    if not config.config_path.exists():
        config.config_path.write_text(
            f"# RedNix configuration\n"
            f"# state_root = {config.state_root}  (set to relocate, e.g. onto an external SSD)\n"
            f'share_root = "{config.share_root}"\n'
            f'default_network = "{config.default_network}"\n'
            f"guest_mem_mib = {config.guest_mem_mib}\n"
            f"guest_vcpu = {config.guest_vcpu}\n"
            f"ssh_port_base = {config.ssh_port_base}\n"
            f"host_uid = {config.host_uid}\n"
            f"host_gid = {config.host_gid}\n",
            encoding="utf-8",
        )
    if args.pubkey:
        ssh_mod.import_public_key(config, args.pubkey)
    else:
        ssh_mod.ensure_keypair(config)
    ssh_mod.write_ssh_config(config)
    print(f"state root ready: {config.state_root}")
    return 0


def cmd_doctor(args, config: Config) -> int:
    checks = doctor_mod.run_checks(config, offline=args.offline)
    ok = doctor_mod.report(checks)
    return 0 if ok else 1


def cmd_build(args, config: Config) -> int:
    nix_mod.build(config, event=args.event, pin=args.pin)
    return 0


def cmd_start(args, config: Config) -> int:
    instance = vm_mod.start(
        config,
        args.event,
        network=args.network,
        mem=args.mem,
        cpus=args.cpus,
        share=args.share,
        fresh=args.fresh,
    )
    print(f"event {args.event} is up (pid {instance['pid']})")
    print(f"  ssh:  rednix shell {args.event}")
    print(f"  gui:  rednix gui --event {args.event} (app menu)")
    print(f"  web:  rednix services --event {args.event}")
    print(f"  port: {instance['ssh_port']} (127.0.0.1 -> guest :22)")
    return 0


def cmd_stop(args, config: Config) -> int:
    event = default_event(config, args.event)
    vm_mod.stop(config, event)
    print(f"event {event} stopped (state preserved)")
    return 0


def cmd_destroy(args, config: Config) -> int:
    vm_mod.destroy(config, args.event, purge_share=args.purge_share, assume_yes=args.yes)
    print(f"event {args.event} destroyed")
    return 0


def cmd_list(args, config: Config) -> int:
    rows = vm_mod.status(config)
    if not rows:
        print("no events; create one with: rednix start <event>")
        return 0
    for row in rows:
        state_str = "running" if row["running"] else "stopped"
        port = row["ssh_port"] or "-"
        print(f"{row['event']:<24} {state_str:<8} {row['network'] or '-':<6} ssh:{port:<5} {row['size_mib']} MiB")
    return 0


def cmd_status(args, config: Config) -> int:
    event = default_event(config, args.event)
    rows = vm_mod.status(config, event=event)
    for row in rows:
        for key, value in row.items():
            print(f"{key:>12}: {value}")
    return 0


def cmd_shell(args, config: Config) -> int:
    event = default_event(config, args.event)
    ssh_mod.write_ssh_config(config)
    sys.exit(ssh_mod.run(config, event, []))


def cmd_exec(args, config: Config) -> int:
    if not args.command:
        _fail("exec requires a command after --")
    event = default_event(config, args.event)
    ssh_mod.write_ssh_config(config)
    return ssh_mod.run(config, event, args.command)


def cmd_fhs(args, config: Config) -> int:
    event = default_event(config, args.event)
    ssh_mod.write_ssh_config(config)
    sys.exit(ssh_mod.run(config, event, ["fhs"], interactive_tty=True))


def cmd_gui(args, config: Config) -> int:
    from . import gui as gui_mod

    if args.list and args.program:
        _fail("gui --list does not take a program")
    event = default_event(config, args.event)
    ssh_mod.write_ssh_config(config)
    if not args.program:
        from . import apps

        return apps.launch(config, event, list_only=args.list, xwls=args.xwls)
    return gui_mod.gui(config, event, args.program, args.args, xwls=args.xwls)


def cmd_services(args, config: Config) -> int:
    from . import services

    if args.list:
        for service in services.SERVICES:
            print(f"{service.name:<14} guest :{service.port:<5}  {service.title}")
        return 0
    event = default_event(config, args.event)
    ssh_mod.write_ssh_config(config)
    return services.run(config, event, args.services, local_port=args.port,
                        start=not args.no_start)


def cmd_desktop(args, config: Config) -> int:
    from . import gui as gui_mod

    event = default_event(config, args.event)
    ssh_mod.write_ssh_config(config)
    if args.stop:
        return gui_mod.desktop_stop(config, event)
    return gui_mod.desktop(config, event, local_port=args.port)


def cmd_logs(args, config: Config) -> int:
    event = default_event(config, args.event)
    vm_mod.logs(config, event, follow=args.follow)
    return 0


def cmd_snapshot(args, config: Config) -> int:
    path = vm_mod.snapshot(config, args.event, args.name)
    print(f"snapshot saved: {path}")
    return 0


def cmd_restore(args, config: Config) -> int:
    vm_mod.restore(config, args.event, args.name)
    print(f"snapshot {args.name} restored for {args.event}")
    return 0


def cmd_gc(args, config: Config) -> int:
    cutoff = time.time() - args.older_than * 86400
    events = all_events(config)
    stale = []
    for event in events:
        instance = config.event_dir(event) / "instance.json"
        mtime = instance.stat().st_mtime if instance.exists() else config.event_dir(event).stat().st_mtime
        if mtime < cutoff:
            stale.append(event)
    gcroots = sorted(config.gcroots_dir.glob("*"))
    referenced = {
        (config.event_dir(e) / "current").resolve()
        for e in events
        if (config.event_dir(e) / "current").is_symlink()
    }
    unpinned = [root for root in gcroots if root.is_symlink() and root.resolve() not in referenced]

    if not stale and not unpinned:
        print("nothing to collect")
        return 0
    for root in unpinned:
        print(f"unpinned GC root: {root}")
    for event in stale:
        print(f"stale event (older than {args.older_than} days): {event}")
    if not args.yes:
        answer = input("Delete these? [y/N] ").strip().lower()
        if answer not in ("y", "yes"):
            print("aborted")
            return 0
    for root in unpinned:
        root.unlink()
    for event in stale:
        vm_mod.destroy(config, event, purge_share=False, assume_yes=True)
    return 0


def cmd_warm(args, config: Config) -> int:
    vm_mod.warm(config, args.event)
    return 0


def cmd_images(args, config: Config) -> int:
    event = default_event(config, args.event)
    ssh_mod.write_ssh_config(config)
    return ssh_mod.run(config, event, ["docker", "images", "--format",
                                      "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"])


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rednix",
        description="Disposable per-CTF NixOS MicroVM pentesting workbench",
    )
    parser.add_argument("--version", action="version", version=f"rednix {__version__}")
    parser.add_argument("--state-root", help="override the state root directory")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the state root, config, and keypair")
    p.add_argument(
        "--pubkey",
        help="import an existing keypair (private key path, or .pub for the public half only) "
        "instead of generating one",
    )
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("doctor", help="preflight checks with exact fixes")
    p.add_argument("--offline", action="store_true", help="assert no network expectations")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("build", help="build the guest runner (nix build .#guestRunner)")
    p.add_argument("event", nargs="?", help="build into this event's state directory")
    p.add_argument("--pin", action="store_true", help="pin the runner under $STATE_ROOT/gcroots")
    p.set_defaults(func=cmd_build)

    p = sub.add_parser("warm", help="boot once and run first-boot initialization")
    p.add_argument("event", nargs="?", default="warmup")
    p.set_defaults(func=cmd_warm)

    p = sub.add_parser("images", help="list preloaded docker images in the guest")
    p.add_argument("event", nargs="?")
    p.set_defaults(func=cmd_images)

    p = sub.add_parser("start", help="create/resume an event VM")
    p.add_argument("event")
    p.add_argument("--network", choices=config_mod.NETWORK_PROFILES)
    p.add_argument("--mem", type=int, help="override guest RAM in MiB")
    p.add_argument("--cpus", type=int, help="override guest vCPUs")
    p.add_argument("--share", help="override the host share root for this event")
    p.add_argument("--fresh", action="store_true", help="discard the persistent volume first")
    p.set_defaults(func=cmd_start)

    p = sub.add_parser("stop", help="shut down the VM, preserving state")
    p.add_argument("event", nargs="?")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("destroy", help="delete VM state; shared files stay unless --purge-share")
    p.add_argument("event")
    p.add_argument("--purge-share", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_destroy)

    p = sub.add_parser("list", help="list events")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("status", help="show one event's status")
    p.add_argument("event", nargs="?")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("shell", help="interactive SSH into the guest")
    p.add_argument("event", nargs="?")
    p.set_defaults(func=cmd_shell)

    p = sub.add_parser("exec", help="run a command in the guest")
    p.add_argument("event", nargs="?")
    p.add_argument("command", nargs=argparse.REMAINDER)
    p.set_defaults(func=cmd_exec)

    p = sub.add_parser("fhs", help="guest shell with conventional Linux paths")
    p.add_argument("event", nargs="?")
    p.set_defaults(func=cmd_fhs)

    p = sub.add_parser("gui", help="pick a GUI app or forward a program's window via Waypipe")
    p.add_argument("--event")
    p.add_argument("--list", action="store_true", help="list GUI apps installed in the running guest")
    p.add_argument("--xwls", action="store_true", help="use xwayland-satellite for X11 clients")
    p.add_argument("program", nargs="?", help="guest program; omit to open the app menu")
    p.add_argument("args", nargs=argparse.REMAINDER,
                   help="arguments passed verbatim to the guest program")
    p.set_defaults(func=cmd_gui)

    p = sub.add_parser("services", help="pick web services and tunnel them to your host browser")
    p.add_argument("--event")
    p.add_argument("--list", action="store_true", help="list supported services (no VM required)")
    p.add_argument("--port", type=int, help="host port override for a single service")
    p.add_argument("--no-start", action="store_true", help="tunnel services without starting them")
    p.add_argument("services", nargs="*", metavar="SERVICE", help="exploitfarm, tulip, or all; omit for menu")
    p.set_defaults(func=cmd_services)

    p = sub.add_parser("desktop", help="open the fallback VNC desktop")
    p.add_argument("event", nargs="?")
    p.add_argument("--port", type=int, default=5901, help="local VNC tunnel port")
    p.add_argument("--stop", action="store_true", help="stop the desktop session")
    p.set_defaults(func=cmd_desktop)

    p = sub.add_parser("logs", help="show or follow the VM log")
    p.add_argument("event", nargs="?")
    p.add_argument("-f", "--follow", action="store_true")
    p.set_defaults(func=cmd_logs)

    p = sub.add_parser("snapshot", help="snapshot the persistent volume")
    p.add_argument("event")
    p.add_argument("name")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("restore", help="restore a snapshot")
    p.add_argument("event")
    p.add_argument("name")
    p.set_defaults(func=cmd_restore)

    p = sub.add_parser("gc", help="prune unpinned runners and stale events")
    p.add_argument("--older-than", type=int, default=30, metavar="DAYS")
    p.add_argument("--yes", action="store_true")
    p.set_defaults(func=cmd_gc)

    def _net():
        from . import net
        return net

    p = sub.add_parser("net", help="routed-profile networking (requires root)")
    net_parser = p.add_subparsers(dest="net_command", required=True)

    p2 = net_parser.add_parser("up", help="create TAP + nftables scope table")
    p2.add_argument("event")
    p2.add_argument("--iface", help="designated Ethernet interface for the CTF network")
    p2.set_defaults(func=lambda a, c: _net().net_up(c, a.event, iface=a.iface))

    p2 = net_parser.add_parser("down", help="remove TAP + nftables table")
    p2.add_argument("event", nargs="?")
    p2.set_defaults(func=lambda a, c: _net().net_down(c, default_event(c, a.event)))

    p2 = net_parser.add_parser("show", help="print the effective ruleset")
    p2.add_argument("event", nargs="?")
    p2.set_defaults(func=lambda a, c: _net().net_show(c, default_event(c, a.event)))

    p2 = net_parser.add_parser("allow", help="allow a destination CIDR and port")
    p2.add_argument("event")
    p2.add_argument("entry", help="CIDR:PORT, e.g. 10.20.0.5/32:443")
    p2.set_defaults(func=lambda a, c: _net().net_allow(c, a.event, a.entry))

    p2 = net_parser.add_parser("callback", help="DNAT a callback port to the guest")
    p2.add_argument("event")
    p2.add_argument("port", type=int)
    p2.set_defaults(func=lambda a, c: _net().net_callback(c, a.event, a.port))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args.state_root)
    except ConfigError as exc:
        _fail(str(exc))
    try:
        return args.func(args, config)
    except (StateError, ConfigError) as exc:
        _fail(str(exc))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
