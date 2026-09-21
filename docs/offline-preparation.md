# Offline preparation

The offline story is the highest-value part of the design and is explicit, checkable work: by the time you are on
the game floor, there must be **no first-run downloads and no infrastructure debugging**. The plan's whole reason
for existing is the constraint the user stated:

> I don't want to be the one debugging their setup during a competition!

This document covers the four preparation commands, the four rules that make offline start actually work, the
manual on-hardware rehearsal checklist, and the automated acceptance test that encodes it.

## The four commands

```sh
rednix build --pin          # nix build .#guestRunner; --out-link $STATE_ROOT/gcroots/<event>
rednix warm                 # boot once, launch every important app, init msfdb, exercise Ghidra/Burp plugins
rednix snapshots-images     # ensure preloaded OCI images are present and loadable
rednix doctor --offline     # re-run all checks with no network expectations
```

- **`rednix build --pin`** — `nix build .#guestRunner`; with `--pin`, write a GC root under `$STATE_ROOT/gcroots/`.
- **`rednix warm`** — boot once, launch the toolset, run `msfdb init`, exit. Run it once before the event.
- **`rednix snapshots-images`** — ensure the preloaded OCI images are present and loadable.
- **`rednix doctor --offline`** — re-run all checks with no network expectations.

## The four rules

1. **Pin everything with GC roots.** A `nix build` `result` symlink is a GC root; `rednix build --pin` writes them
   under `$STATE_ROOT/gcroots/` so the runner survives `nix-collect-garbage`.
2. **The launcher must not need the network.** `nix run .#rednix` re-evaluates the flake and may want to fetch
   inputs. Therefore the launcher is **installed** ahead of time (`nix profile install`, or a pinned store path
   referenced from the user's PATH) and `rednix start` only ever execs store paths that are already pinned. Offline
   start must not evaluate the flake at all.
3. **First-run downloads are the trap.** Launch every significant tool once while preparing — Metasploit's DB,
   Ghidra's first-run project setup, browser profile creation, MITM proxy CA generation, wordlist extraction.
4. Then rehearse with the network **physically unavailable**: reboot host, `rednix start`, both GUI paths, a sample
   challenge, file transfer, `rednix stop`, `rednix start` again, `rednix destroy`.

## Manual, on-hardware rehearsal checklist (§10.3)

Pre-competition, in order:

1. `rednix doctor`
2. `rednix build --pin`
3. `rednix warm`
4. `rednix snapshot`
5. network physically down
6. `rednix start`
7. `rednix shell`
8. `rednix gui` (Burp/Ghidra/xterm)
9. `rednix desktop`
10. static binary
11. `rednix fhs <dynamic binary>`
12. `docker load` a sample image
13. transfer files both ways
14. `rednix stop`
15. `rednix start`
16. `rednix destroy`
17. confirm the shared folder survived

## The automated form (A8)

The manual checklist has an automated counterpart in the acceptance suite (A8):

| # | Test | Assertion |
|---|---|---|
| A8 | Offline boot | With networking physically down, `rednix start` succeeds with no `nix` evaluation and no fetch; both GUI paths and a sample challenge work. |

A8 and the §10.3 checklist together are the exit criteria for M5 — *"A8 and the §10.3 checklist pass with
networking physically unavailable."*
