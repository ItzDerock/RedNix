# Hyprland integration

RedNix forwards individual GUI windows into the existing Hyprland session with Waypipe, and keeps a guest-side VNC
desktop as a fallback for apps that refuse to run under it. This document covers the Waypipe invocation, the
`[RedNix]` window rule, the X11 path, the OpenSSH requirement, and the Hyprland permission system and its limits.

## Waypipe invocation

`rednix gui <program> [args…]` runs, from the host:

```sh
waypipe --no-gpu --title-prefix "[RedNix] " ssh -F "$STATE_ROOT/ssh_config" rednix -- <program> [args…]
```

### `--no-gpu`

`--no-gpu` blocks `wayland-drm` and `linux-dmabuf`, i.e. it does not expose graphics libraries. Start here; enable
acceleration only if a specific tool demands it.

### `--title-prefix "[RedNix] "`

`--title-prefix "[RedNix] "` is applied client-side in ssh mode, giving a `[RedNix]`-prefixed title for Hyprland
window rules and a dedicated workspace. It is purely a visual cue, **not** a boundary.

> **Note.** `PLAN.md` does not include a literal Hyprland config snippet; it specifies only that the
> `[RedNix]`-prefixed title is what Hyprland window rules match on. Any concrete rule is written against that
> title prefix and (on the guest-window side) the Waypipe window's class/title as Hyprland reports it.

## X11 apps (`--xwls`)

`--xwls` uses **xwayland-satellite** to run X11 clients (Burp, Ghidra) under Wayland. It requires
`xwayland-satellite` in the guest `PATH`. Both Waypipe and xwayland-satellite are nixpkgs packages; pin and test
early — this is the single most likely "GUI tool does not start" failure.

If `--xwls` fails for Burp or Ghidra, the fallback is `rednix desktop` (guest-side floating labwc + wayvnc), which is
exactly why it exists. Test in M4, not on competition day.

Known Ghidra specifics on this path:

- nixpkgs' `ghidra` wrapper is overridden in `modules/tools/rev.nix` to launch in `fg` mode: upstream's background
  mode detaches the JVM and discards its output, which kills Ghidra under waypipe (the waypipe session ends with
  `launch.sh`) and surfaces only as `Exited with error.  Run in foreground (fg) mode for more details.`
- xwayland-satellite is a non-reparenting WM, and labwc's Xwayland integration
  does not reparent X11 windows either, so the wrapper always sets
  `_JAVA_AWT_WM_NONREPARENTING=1`; without it AWT windows draw blank/white on
  both paths.

If clicks in the `rednix desktop` VNC do nothing, restart the session (the desktop is a plain long-lived labwc +
wayvnc; a fresh session always recovers):

```sh
rednix desktop --stop && rednix desktop
```

## Requirements and flags

- **OpenSSH ≥ 6.7.** Waypipe in ssh mode requires OpenSSH ≥ 6.7 for Unix socket forwarding. Fine here, but it is why
  `--ssh-bin` must point at the real OpenSSH client, not a wrapper that breaks `-R`.
- **`--secctx <id>`.** Optionally attaches a Wayland security-context app ID. Not required for v1; noted because it
  is the one hook the compositor could key richer rules on later.

## The Hyprland permission system — and its exact limits

Hyprland's permission system is a genuine additional layer for the Waypipe exposure, but read its limits carefully
before trusting it.

- **Disabled by default.** `ecosystem.enforce_permissions = true` must be set.
- **The config syntax differs by version.** Since Hyprland 0.55 it is Lua-configured:
  `hl.permission({ binary, type, mode })`. The older 0.54 uses hyprlang syntax. Write the rules against the version
  actually installed, and re-check after any Hyprland upgrade — a rule written against the wrong syntax silently
  does nothing.
- **The relevant permission types** are `screencopy`, `input-capture`, `cursorpos`, `plugin`, `keyboard`.
- **Rules match on binary path.** Under Waypipe the local client is the single `waypipe` binary, so a rule can deny
  `screencopy`/`input-capture`/`cursorpos` for the Waypipe store path. On NixOS the path spans a store hash, so the
  rule must be written as a regex (or interpolated with `lib.escapeRegex`), not as a literal path, e.g.:

  ```
  /nix/store/[a-z0-9]{32}-waypipe-[0-9.]*/bin/waypipe
  ```

- **No per-app granularity.** Because every forwarded app shares one Waypipe client process, a rule keyed on the
  `waypipe` binary applies to **every** forwarded app. That is the honest limit of this mitigation.

**Test rather than assume.** Do not assume the clipboard and screen-capture behaviour of `rednix gui`; the point of
the permission rules is to enable checking, not to promise isolation. This is documented, not fixed — see
[`threat-model.md`](threat-model.md).
