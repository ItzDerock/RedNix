# AGENTS.md

Instructions for coding agents (and human contributors) working in this repository.

## What this is

RedNix is a disposable per-CTF NixOS MicroVM pentesting workbench: a Nix flake that builds the guest
(`modules/`, evaluation entry `.#guestRunner`) and a Python launcher (`src/rednix/`) that drives the generated
runner package from per-event state directories. `PLAN.md` is the authoritative design document; `README.md` is
the user guide.

## Hard constraints

- **The launcher is Python standard-library only.** No third-party dependencies, ever — the offline requirement
  means the flake output must need nothing beyond `python3` (no pip, no vendored wheels).
- **Only `rednix build` evaluates the flake.** `rednix start` and everything after it must exec already-built
  store paths without network access or flake evaluation.
- Exactly **one** shared folder (`/work`, virtiofs). Do not add host/guest channels that weaken this.
- Do not bake user-specific values into the repo (SSH keys, UIDs that differ from the documented defaults).
  The guest SSH key is injected at build time via the `guestKey` flake input override — see
  `modules/guest/ssh.nix` and `src/rednix/nix.py`.

## Environment

`nix develop` is fully self-contained: it puts the launcher and every host-side dependency it shells out to
(`ssh`/`scp`/`ssh-keygen`, `waypipe`, `vncviewer`, `nix`, `nft`, `ip`, `python3` + `pytest`) on PATH, so single
commands work without manual setup:

```sh
nix develop -c <cmd>
```

## Build and test

```sh
nix build .#guestRunner          # guest VM runner (evaluates modules/)
nix build .#rednix               # the launcher
nix develop -c pytest tests/unit # launcher unit tests (pure logic, fast)
```

Acceptance tests (`tests/acceptance/`) run against a real host and real VMs; `tests/acceptance/README.md`
explains the environment variables and the `[manual]` tests that are checklists rather than fake passes.

## Guest-VM ops loop (for testing guest changes)

```sh
nix develop -c rednix build test   # build into the scratch event's state dir
rednix stop test                   # if it was running
rednix start test
ssh -F ~/.local/state/rednix/ssh_config rednix-test   # direct access, bypassing the launcher
```

- The scratch/test event is conventionally named `test`.
- GUI apps run through `rednix gui --xwls` (waypipe + xwayland-satellite); the fallback desktop is the
  systemd `rednix-desktop.service` (headless labwc + waybar + wayvnc + fuzzel/Thunar on 127.0.0.1:5901).
- Debug GUI/VM problems empirically: reproduce through the real pipeline, bypass launch wrappers to capture
  true stderr (e.g. Ghidra's `launch.sh fg`), A/B test suspect env vars, and verify fixes visually
  (`nix shell nixpkgs#grim -c grim -o DP-2 <file>`) plus end-to-end after rebuild before reporting them fixed.

## Conventions

- One NixOS module per area under `modules/guest/` and `modules/tools/`; each does only its own job (mostly
  `environment.systemPackages` or one service). `modules/guest/default.nix` imports all of them; a user can
  comment one out to slim the image.
- Launcher state paths are `Config` properties (`src/rednix/config.py`) — derive new paths there rather than
  constructing them ad hoc. Configuration precedence: `--state-root` flag → `REDNIX_STATE_ROOT` env →
  `$STATE_ROOT/config.toml` → compiled default.
- argparse wiring lives in `build_parser()` in `src/rednix/cli.py`; every subcommand handler takes
  `(args, config)`.
- Every `rednix doctor` check prints the exact fix for its failure, not just the failure.
- Readiness is polled (bounded), never `sleep`-guessed; fail loudly with the tail of `vm.log`.
- Resolved design choices get recorded in `docs/` (see `docs/state-design.md` for the pattern) so a future
  rebuild does not rediscover them.

## Gotchas

- `microvm.mem` is **MiB, not GiB** — `16384` is 16 GiB. Do not tune down to exactly 2048 MiB (QEMU hangs).
- The runner binaries (`microvm-run`, `virtiofsd-run`) resolve every relative path against their **current
  working directory**, which is the event state dir — this is what makes one runner serve N events.
- virtiofs: `posixAcl = true` is mutually exclusive with `--translate-uid`/`--translate-gid`; the share uses
  translation, so keep `posixAcl = false`.
- `--override-input` (used for the guest key) implies `--no-write-lock-file`; the committed `flake.lock` must
  never change as a side effect of a build.
- Waypipe is **not** a security boundary; see `docs/threat-model.md` before "improving" its invocation.
