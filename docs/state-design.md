# Persistent state design

How the guest's persistent volume and bind mounts work, and why.

## Launcher default event

`rednix default <event>` saves the selected name in `$STATE_ROOT/default-event`.
The path is derived through `Config.default_event_path`. This is launcher state,
kept separate from `config.toml` so setting it preserves configuration comments
and settings without requiring a TOML writer. Writes use a unique temporary file
and atomic replacement so concurrent readers never see a partial name.

Event selection is an explicit argument first, then the saved choice, then the
existing automatic selection of the most recently started event. `rednix default`
prints that effective selection; `rednix default --clear` removes the saved choice.
The selection follows the resolved state root, including configuration relocation.
Only validated event names can be saved, and names may be selected before the
event exists. Deleting an event does not silently select another event; choose a
different default or clear the selection afterward.

Commands that accept omitted events honor this choice. `build` still builds a
global runner and `warm` still uses `warmup` when no choice is saved. `start` now
accepts an omitted event. Commands requiring explicit events keep that interface.
For `exec`, arguments after `--` are parsed separately so `rednix exec -- id`
runs `id` in the selected event instead of interpreting it as an event name.

## Layout

The guest root filesystem is tmpfs. Everything that must survive a reboot
lives on one `microvm.volumes` entry (`state.img`, ext4, 64 GiB sparse,
auto-created and formatted by the runner on first start) mounted at
`/var/lib/rednix`. Bind mounts pull the stateful paths out of it:

| Volume path              | Bind mount           | Used by                    |
|--------------------------|----------------------|----------------------------|
| `/var/lib/rednix/home`   | `/home/rednix`       | guest user home, msfdb     |
| `/var/lib/rednix/postgres` | `/var/lib/postgresql` | PostgreSQL (`msfdb init`) |
| `/var/lib/rednix/root`   | `/root`              | root's files               |

Docker's data root is relocated directly (`virtualisation.docker.daemon.settings.data-root =
/var/lib/rednix/docker`), so it needs no bind mount.

## The ordering problem, and the choice made

`systemd-tmpfiles-setup.service` has no ordering relationship with mount
units: tmpfiles rules creating `/var/lib/rednix/home` can run *before* the
volume mounts (dir created on tmpfs, then hidden by the mount) or *after*
(but still before the bind mounts need it). PLAN.md §6.2 flagged this as an
M1 verification item with a known-good fallback.

**Choice implemented (modules/guest/state.nix):** neither tmpfiles nor a
volume-at-/home fallback. A `rednix-state-prep.service` oneshot creates and
chowns the directories, with explicit ordering:

- `After=var-lib-rednix.mount` (volume first),
- `Before=<every bind mount>.mount` (prep before binds),
- activated in every boot transaction via `wantedBy = multi-user.target`.
- Additionally each bind mount declares `depends = [ "/var/lib/rednix" ]`,
  which NixOS turns into `x-systemd.requires-mounts-for=`, enforcing
  volume-before-bind at the mount level as well.

`neededForBoot` is set **only** on the volume: stage 1 mounts it, stage 2
runs the prep service, then the bind mounts go up. Bind mounts deliberately
do *not* set `neededForBoot` — they would otherwise be mounted from the
initrd before any stage-2 service could create their sources.

If a future NixOS/microvm.nix upgrade fights this ordering, the documented
fallback is PLAN.md's: mount the volume directly at `/home/rednix` and
relocate service data with `services.postgresql.dataDir` and the Docker
`data-root` under it.
