# Launcher app and service menus

`rednix gui` without a program queries the running guest over the existing SSH
connection and opens a searchable terminal picker. `--list` offers discovery in
scripts and terminals without an interactive screen. The picker uses Python's
standard-library curses with a numbered fallback when curses is unavailable.

Discovery sends a standalone standard-library Python helper on SSH stdin, so
existing guests need no rebuild. It reads the guest's desktop entries, including
the NixOS system profile, and includes installed common tools without entries.
Hidden, non-display, terminal-only, and unavailable desktop entries are omitted.
Desktop commands expand fields without file/URL arguments, following the
[desktop entry Exec specification](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html).
Known tools use bare program names so Ghidra resolves to RedNix's foreground
wrapper. Known Wayland apps use normal Waypipe; other menu entries default to
`--xwls`. Explicit `rednix gui PROGRAM ARGS` retains its existing behavior.

`rednix services` offers a picker for the supported web service wrappers,
ExploitFarm and Tulip. Names or `all` allow direct access. Services start through
their existing readiness-aware guest wrappers. Each service module grants the
guest user passwordless sudo for its own start, stop, and log commands; wrappers
use absolute system-profile paths and `sudo -n` so SSH never waits for a password.
Existing guests need a rebuild for those permissions. `--no-start` still tunnels
services started manually in older guests. Host ports default to the guest
ports, move to a free nearby port if occupied, and can be overridden for one
service with `--port`. Tunnels bind to `127.0.0.1` and use the configured SSH
identity and event endpoint. A dedicated SSH connection disables control socket
reuse so terminating the command also removes its forwarding listeners.

The launcher polls each service's HTTP endpoint through the tunnel before
printing ready URLs. It bypasses host proxy environment settings for these local
checks. A failed SSH process or readiness deadline reports a fix; every exit
path closes the SSH child. Guest services stay running after the tunnel closes.
There is no new VM channel, host share, flake evaluation, or runtime dependency.
