# RedNix threat model

Guest root is **untrusted**. The security story is "cheap to discard", not "hard to compromise": RedNix has exactly
one guest profile, `rednix destroy <event>` is a first-class command, and the design invests in making destruction
and recreation fast and boring rather than in per-session hardening.

This document states plainly what is defended, what is not, and the exact limits of the partial mitigations.

## Defended

- Guest root is untrusted.
- Guest root cannot read host files outside the single `/work` share.
- Host services are unreachable from the guest.
- In the `routed` profile the scope rules live in host nftables, so guest root cannot disable them.
- `rednix destroy` reliably returns to a clean slate, and `--fresh` provides an in-event reset.

## Not defended, stated plainly

- **A VM escape or a QEMU/virtiofsd vulnerability defeats everything.**
- **Waypipe gives guest clients a path to the host compositor.** The man page is explicit that it does not filter
  compositor protocols and that proxied clients inherit whatever the compositor grants — screenshots, lock screen,
  DoS. A compromised forwarded application is not contained by Waypipe.
- **The host user runs QEMU directly**, so a hypervisor escape yields that user's privileges.
- **The shared folder is a two-way interface:** the guest can modify and replace files in `/work`.

There is no attempt at a "sealed room" threat model. Guest root is untrusted; the host kernel and compositor are
not defended against a VM escape here.

## Partial mitigations, and their exact limits

### Hyprland's permission system

Hyprland's permission system (`screencopy`, `input-capture`, `cursorpos`, `plugin`, `keyboard`) is a genuine
additional layer — but note its limits:

- **It is disabled by default.** `ecosystem.enforce_permissions = true` must be set.
- **The config syntax differs by version.** It has been Lua-configured since Hyprland 0.55
  (`hl.permission({ binary, type, mode })`) versus the older hyprlang syntax in 0.54. Write the rules against the
  version actually installed, and re-check after any Hyprland upgrade.
- **Rules match on binary path.** Under Waypipe the local client is the single `waypipe` binary, so a rule can deny
  `screencopy`/`input-capture`/`cursorpos` for
  `/nix/store/[a-z0-9]{32}-waypipe-[0-9.]*/bin/waypipe` — but it then applies to **every** forwarded app, because
  they share one Waypipe client process. There is no per-app granularity. That is the honest limit of this
  mitigation, and it is why the clipboard and screen-capture behaviour of `rednix gui` should be tested rather than
  assumed.
- **On NixOS the regex spans a store hash**, so the rule must be written as a regex (or interpolated with
  `lib.escapeRegex`), not as a literal path.

See [`hyprland-integration.md`](hyprland-integration.md) for the concrete rule and the test guidance.

### The shared folder and forwarded desktop remain interfaces to the host

> The one qualification is that **the shared folder and forwarded desktop connection remain interfaces to the
> host**. […] Waypipe means we cannot promise that guest compromise has zero host impact.

Waypipe's own manual is blunter:

> Waypipe does not provide any strong security guarantees […] It does not filter which Wayland protocols the
> compositor makes available to the client […] proxied clients run under Waypipe can also make screenshots or
> lock the screen.

This is documented, not fixed.

## Runs as the invoking user

The launcher runs as the **invoking user**, who must be in the `kvm` group. The `microvm.nix` host module runs
guests as `User=microvm Group=kvm`; RedNix accepts the weaker equivalent and documents it here as a deliberate,
revisitable simplification. A `--system` mode that re-execs under a dedicated `microvm` user is a documented future
option, not v1 work.
