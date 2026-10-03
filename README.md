# RedNix

> [!NOTE]
> THIS IS AI CODE BTW, I DONT HAVE TIME TO WRITE A GOOD README
> vibed this up for an upcoming ctf & AD event!

A per-CTF disposable NixOS MicroVM pentesting workbench. RedNix replaces "run Metasploit on my host" with a
disposable, per-competition NixOS MicroVM that:

- keeps the red-team toolset out of the host system closure entirely,
- shares exactly **one** host folder with the guest,
- forwards individual GUI windows into the existing Hyprland session,
- keeps a lightweight desktop fallback for apps that refuse to work under Waypipe,
- survives an entire competition **offline**, with no first-run downloads and no infrastructure debugging.

The security story is **cheap to discard, not hard to compromise**: any sensitive information lives on the
hypervisor, a compromised event VM is simply deleted, and `rednix destroy <event>` is a first-class command.
Adding a competition never triggers a host rebuild — RedNix drives the generated MicroVM runner package
directly from a per-event state directory. Rationale and rejected alternatives live in [`PLAN.md`](PLAN.md).

## One VM per event

There is exactly **one** guest profile. `rednix destroy <event>` deletes VM state and never touches the shared
folder (unless `--purge-share` is given). Per-event state (disk image, SSH port, sockets, logs) lives under a
configurable state root, so events are independent and the whole root can sit on an external SSD.

## Architecture (30-second overview)

```
                    HOST (NixOS + Hyprland)                      GUEST (NixOS MicroVM)
 ┌──────────────────────────────────────────────────────┐   ┌────────────────────────────┐
 │  rednix (Python)                                     │   │  sshd  (127.0.0.1 fwd)     │
 │   ├─ $STATE_ROOT/events/<event>/                     │   │  waypipe server            │
 │   │    current -> /nix/store/…-microvm-qemu-rednix   │   │  xwayland-satellite        │
 │   │    state.img        (persistent volume)          │   │  labwc + wayvnc  (:1)      │
 │   │    rednix-virtiofs-work.sock                     │   │  docker (preloaded images) │
 │   │    rednix.sock      (QMP)                        │   │  buildFHSEnv ("fhs")       │
 │   │    work -> ~/CTF/<event>                         │   │  tool groups               │
 │   ├─ execs:                                          │   │                            │
 │   │    current/bin/virtiofsd-run   (bg, cwd=event)   │   │                            │
 │   │    current/bin/microvm-run     (fg, cwd=event)   │   │                            │
 │   └─ waypipe ssh / ssh -L                            │   │                            │
 └──────────────────────────────────────────────────────┘   └────────────────────────────┘
        ▲                                                        ▲
        │ virtiofs: "work" -> /work                              │ virtio-blk: state.img
        │ (the ONLY shared path)                                 │  → /var/lib/rednix + binds
        └────────────────────────────────────────────────────────┘
```

Why this works without host integration: the generated runner package contains all the pieces the host systemd
module would otherwise orchestrate — `bin/microvm-run`, `bin/microvm-shutdown`, `bin/virtiofsd-run` — and it
resolves every relative path (share sockets, volume images, QMP socket) against its **current working directory**.
So "one runner package, N independent event state directories" is a supported shape, not a hack.

## Quickstart

```sh
rednix init            # create state root, config, keypair, ssh_config (idempotent)
rednix doctor          # preflight: /dev/kvm, userns, UID match, free space, ZFS, pinned runner
rednix build --pin     # nix build .#guestRunner; --pin writes a GC root
rednix warm            # boot once, launch the toolset, msfdb init, exit
rednix start <event>   # boot the per-event VM; allocates a free SSH port; symlinks work
rednix default <event> # remember this event for subsequent commands
rednix shell           # ssh into the guest (master connection)
rednix gui             # searchable menu of installed GUI apps
rednix gui --list      # show app names and guest launch commands
rednix services        # start a web service and tunnel it to your host browser
rednix desktop         # floating labwc + wayvnc fallback for apps that refuse Waypipe
rednix stop            # microvm-shutdown (QMP ACPI) + terminate virtiofsd; preserves the volume
rednix destroy <event> # delete VM state; never touches share_root/<event>
```

Run inside `nix develop` (or install the launcher) so every host-side dependency (`ssh`, `waypipe`,
`vncviewer`, `nix`, `nft`, `ip`) is on PATH. `rednix build` runs `nix build .#guestRunner`; `--pin` additionally
writes a GC root under `$STATE_ROOT/gcroots`. Run `rednix warm` once before the event so the first boot is not
also the first download.

Choose an event once to avoid repeating `--event` or positional event names:

```sh
rednix default my-ctf
rednix gui
rednix services exploitfarm
rednix shell
rednix exec -- id
rednix default         # print the event commands will use
rednix default --clear # return to automatic event selection
```

The selection persists across terminals and is scoped to the state root. An
explicit event always overrides it for that command. You can select a new name
before creating the event, then run `rednix build` and `rednix start` without an
event argument. Commands with optional events use the saved choice; `build` and
`warm` retain their original defaults when no choice is saved. Commands requiring
an explicit event, such as `destroy`, `snapshot`, and `restore`, still require it.

### Apps and web services

With a VM running, `rednix gui` opens a terminal picker: type to search by app
name or command, use the arrow keys, and press Enter to launch. Escape cancels.
The menu discovers apps in the guest and selects X11 forwarding for tools such
as Ghidra and Burp. `rednix gui --list` prints the available apps and commands;
explicit commands such as `rednix gui --xwls ghidra` still work.

`rednix services` opens a service picker. You can also connect directly:

```sh
rednix services --list                         # supported services and guest ports
rednix services --event EVENT exploitfarm      # start ExploitFarm and forward its UI
rednix services --event EVENT tulip            # start Tulip and forward its UI
rednix services --event EVENT all              # both UIs in one tunnel
rednix services --event EVENT --port 8050 exploitfarm
```

Open the printed URLs in your host browser. Keep the command running; Ctrl+C
closes its tunnels and leaves the guest services running. Default host ports
are 5050 for ExploitFarm and 3000 for Tulip; a free nearby port is chosen if
occupied. `--port` requests an exact host port for one service, and `--no-start`
connects without starting services. All forwards bind to host localhost. Both
commands honor `--state-root` and `REDNIX_STATE_ROOT`; `--event` selects a VM,
otherwise the saved default (or the most recently started event) is used. The GUI menu works
with an existing guest build. Rebuild the guest once for passwordless service
startup; with an older guest, start the services in `rednix shell` and connect
using `rednix services --no-start`.

## SSH keys

The guest authorizes exactly one public key, and **nothing personal is committed to this repo**:

- `rednix init` generates an Ed25519 keypair under `$STATE_ROOT/keys/` and `rednix build` injects the public
  half into the guest via a flake input override (`--override-input guestKey`), so the committed `flake.lock`
  never changes.
- To reuse an existing keypair: `rednix init --pubkey ~/.ssh/id_ed25519` (a path to the private key imports
  both halves; a `.pub` path records only the public half).
- `rednix doctor` verifies the private key matches the public half that gets baked in, and tells you to
  `rednix build --pin` after any key change. `keys/rednix.pub` in the repo is a comment-only placeholder that
  only exists so `nix build .#guestRunner` evaluates standalone.

## Commands

`rednix default [<event>]` shows or saves the default event. Use
`rednix default --clear` to remove it. `rednix start` also accepts an omitted event.

| Command                                                                                      | Behaviour                                                                                                                                                                                                                                                    |
| -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `rednix init [--pubkey PATH]`                                                                | Create state root, config, keypair (or import the given one), ssh_config. Idempotent.                                                                                                                                                                        |
| `rednix doctor [--offline]`                                                                  | Preflight: `/dev/kvm`, userns, UID match, free space on state/share roots, ZFS xattr check, pinned runner, keypair, host tools. Prints the exact fix for each failure.                                                                                       |
| `rednix build [<event>] [--pin]`                                                             | `nix build .#guestRunner`, injecting the state-root public key; with `--pin`, write a GC root; with `<event>`, link the runner into that event's directory.                                                                                                  |
| `rednix warm [<event>]`                                                                      | Boot, launch the toolset, `msfdb init`, exit. Run once before the event.                                                                                                                                                                                     |
| `rednix images [<event>]`                                                                    | List the preloaded docker images in the guest.                                                                                                                                                                                                               |
| `rednix start [<event>] [--network nat\|routed] [--mem N] [--cpus N] [--share PATH] [--fresh]` | Create state root for the event if absent; allocate a free SSH port; symlink `work`; start `virtiofsd-run` in the background with `cwd` = event dir; exec `microvm-run` detached; wait for sshd; write `instance.json`. `--fresh` discards the volume first. |
| `rednix stop [<event>]`                                                                      | `current/bin/microvm-shutdown` (QMP ACPI powerdown), then terminate `virtiofsd-run`. Preserves the volume.                                                                                                                                                   |
| `rednix destroy <event> [--purge-share] [--yes]`                                             | Stop, then `rm -rf $STATE_ROOT/events/<event>` and its GC root. **Never touches `share_root/<event>` unless `--purge-share`.**                                                                                                                               |
| `rednix list` / `status [<event>]`                                                           | Enumerate events, bound ports, running state, disk usage.                                                                                                                                                                                                    |
| `rednix shell [<event>]`                                                                     | `ssh` (master connection).                                                                                                                                                                                                                                   |
| `rednix exec [<event>] -- <cmd…>`                                                            | Non-interactive `ssh`.                                                                                                                                                                                                                                       |
| `rednix fhs [<event>]`                                                                       | `ssh -t` running `fhs`.                                                                                                                                                                                                                                      |
| `rednix gui [--event <event>] [--list] [--xwls] [<program> [args…]]`                         | Searchable installed-app menu when no program is supplied; `--list` prints apps. Explicit programs use Waypipe; `--xwls` routes X11 clients through xwayland-satellite. |
| `rednix services [--event <event>] [--list] [--port N] [--no-start] [SERVICE…]`               | Pick or name `exploitfarm`, `tulip`, or `all`; start services and forward their UIs to host localhost until Ctrl+C. |
| `rednix desktop [<event>] [--port N] [--stop]`                                               | SSH tunnel + start/reconnect the floating labwc session (wayvnc on 127.0.0.1:5901) + local viewer.                                                                                                                                                           |
| `rednix logs [<event>] [-f]`                                                                 | Tail `vm.log`.                                                                                                                                                                                                                                               |
| `rednix snapshot <event> <name>` / `rednix restore <event> <name>`                           | Copy/restore `state.img` as a restore point.                                                                                                                                                                                                                 |
| `rednix net up\|down\|show\|allow\|callback`                                                 | Routed-profile TAP + nftables scope management. Requires root; prints the exact command if not.                                                                                                                                                              |
| `rednix gc [--older-than DAYS] [--yes]`                                                      | Prune unpinned runner generations and events older than N days, after confirmation.                                                                                                                                                                          |

## Configuration

Precedence:

```
--state-root flag → REDNIX_STATE_ROOT env → $STATE_ROOT/config.toml → compiled default (~/.local/state/rednix)
```

Point `state_root` at an external SSD and every event lives there.

```toml
# $STATE_ROOT/config.toml
state_root = "/mnt/ssd/rednix"
share_root = "~/CTF"
default_network = "nat"
guest_mem_mib = 16384
guest_vcpu = 8
ssh_port_base = 2222
host_uid = 1000
host_gid = 100
guest_uid = 1000
guest_gid = 1000
ssh_connect_timeout = 120
# ctf_iface = "eth0"        # required for `rednix net up` (routed profile)
```

## Host prerequisites

One-time, not per-event. `rednix doctor` verifies each and prints the exact fix:

- `/dev/kvm` readable/writable by the invoking user (usually `users.users.<you>.extraGroups = [ "kvm" ]`).
- Unprivileged user namespaces available (needed by `virtiofsd`).
- Host UID/GID match the guest user's UID/GID (set `host_uid`/`host_gid` in `config.toml`), or the share is
  configured with UID translation.

Host assumptions: NixOS host, Hyprland compositor, 32 GB RAM. Guest allocation is **16 GiB / 8 vCPU**
(`microvm.mem = 16384`, `microvm.vcpu = 8`), halved so the host keeps room for the compositor, browser, and editor.
Note `microvm.mem` is in **MiB, not GiB** — `16384` is correct. The guest root filesystem is `tmpfs` sized `50%`
of guest RAM by default, so at 16 GiB that is ~8 GiB of RAM-resident `/tmp`.

## Repository layout

```
flake.nix
flake.lock
AGENTS.md                     # instructions for coding agents and contributors
PLAN.md                       # design & implementation plan: rationale, milestones
README.md
modules/
  guest/
    default.nix               # imports everything below
    base.nix                  # locale, hostname, user, sudo policy, tmpfiles
    ssh.nix                   # sshd + authorized key (injected at build time)
    state.nix                 # persistent volume + bind mounts
    networking.nix            # systemd.network for nat + routed profiles
    wayland.nix               # waypipe, xwayland-satellite
    desktop.nix               # floating labwc + wayvnc + root menu + waybar
    fhs.nix                   # buildFHSEnv
    containers.nix            # docker + preloaded/baked images
  tools/
    core.nix  net.nix  exploit.nix  rev.nix  forensics.nix  crypto.nix
keys/
  rednix.pub                  # placeholder; rednix build injects your key from the state root
src/rednix/
  __init__.py  cli.py  config.py  state.py  vm.py  net.py  ssh.py  gui.py  doctor.py  nix.py
tests/
  unit/                       # pytest: config parsing, path resolution, arg validation
  acceptance/                 # bash: lifecycle, isolation, offline, network scope
docs/
  threat-model.md
  offline-preparation.md
  networking.md
  hyprland-integration.md
  state-design.md
```

## Documentation

- [`docs/threat-model.md`](docs/threat-model.md) — what is defended, what is not, and the exact limits of the
  partial mitigations (Waypipe, Hyprland permissions, running as the invoking user).
- [`docs/offline-preparation.md`](docs/offline-preparation.md) — the four commands, the four rules, the manual
  rehearsal checklist, and the automated offline acceptance test (A8).
- [`docs/networking.md`](docs/networking.md) — the `nat` and `routed` profiles, the host nftables rules, the
  `rednix net` subcommands, and the CTF rules compliance caveat.
- [`docs/field-guide/`](docs/field-guide/) — offline CTF playbooks, quick search UI, and a read-only file triage helper.
- [`docs/tulip.md`](docs/tulip.md) — Tulip setup, remote PCAP capture and attack/defense traffic analysis.
- [`docs/exploitfarm.md`](docs/exploitfarm.md) — host port forwarding, ExploitFarm event setup, `xfarm` workers, flag submission, and troubleshooting.
- [`examples/exploitfarm/`](examples/exploitfarm/README.md) — standalone exploit starters for HTTP vulnerabilities, TCP protocols, and ret2win.
- [`docs/hyprland-integration.md`](docs/hyprland-integration.md) — the Waypipe invocation, the `[RedNix]` window
  rule, `--xwls`, and the Hyprland permission system and its limits.
- [`docs/state-design.md`](docs/state-design.md) — how the persistent volume and bind mounts work, and the
  mount-ordering problem they solve.
- [`PLAN.md`](PLAN.md) — the design and implementation plan: requirements, rejected alternatives, milestones.
- [`AGENTS.md`](AGENTS.md) — build/test commands and conventions for coding agents and contributors.

## Security

RedNix isolates the red-team toolset from the host system closure, but it is **not** a "sealed room" threat model.
Read this before trusting it with anything.

**Waypipe is not a security boundary.** The shared folder and forwarded desktop connection remain interfaces to
the host: guest compromise cannot be promised zero host impact. Waypipe's own manual is blunter:

> Waypipe does not provide any strong security guarantees […] It does not filter which Wayland protocols the
> compositor makes available to the client […] proxied clients run under Waypipe can also make screenshots or
> lock the screen.

A compromised forwarded application is not contained by Waypipe.

**A VM escape defeats everything.** A VM escape or a QEMU/virtiofsd vulnerability defeats the whole model. The host
user runs QEMU directly, so a hypervisor escape yields that user's privileges. The host kernel and compositor are
not defended against a VM escape.

**The shared folder is two-way.** The guest can modify and replace files in `/work`. `rednix destroy` deletes VM
state but never touches the share root unless `--purge-share` is given.

Mitigations that help, and their limits (see [`docs/threat-model.md`](docs/threat-model.md) for the full list):
Hyprland's permission system is a genuine additional layer but is **disabled by default**, matches on binary path
(so under Waypipe it applies to _every_ forwarded app, with no per-app granularity), and its config syntax differs
between Hyprland 0.54 (hyprlang) and 0.55+ (lua). In the `routed` networking profile the scope rules live in host
nftables, so guest root cannot disable them.
