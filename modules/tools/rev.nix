# RedNix tool group: rev — debugging, disassembly, and reverse engineering
{ pkgs, lib, ... }:
let
  # nixpkgs' `ghidra` wrapper launches via `launch.sh bg`, which detaches the
  # JVM and redirects all of its output to /dev/null. Under waypipe the whole
  # session is torn down as soon as launch.sh exits (~1s), killing Ghidra with
  # only the misleading "Exited with error.  Run in foreground (fg) mode for
  # more details." left behind. Launch in fg mode instead: it behaves like any
  # other GUI app and keeps error output visible.
  #
  # `_JAVA_AWT_WM_NONREPARENTING=1` is required on every GUI path this stack
  # has: xwayland-satellite (`rednix gui --xwls`) and labwc's Xwayland both
  # manage X11 windows without X11-frame reparenting (labwc draws server-side
  # decorations around the raw window), so AWT's reparenting assumption breaks
  # and windows draw blank/white without the flag (same workaround as for
  # sway/i3). Verified empirically under both.
  ghidraFg = pkgs.writeShellScriptBin "ghidra" ''
    export _JAVA_AWT_WM_NONREPARENTING=1
    GHIDRA_MAXMEM="''${GHIDRA_MAXMEM:-}"
    GHIDRA_GUI_MAXMEM="''${GHIDRA_GUI_MAXMEM:-$GHIDRA_MAXMEM}"
    exec "${pkgs.ghidra}/lib/ghidra/support/launch.sh" fg jdk Ghidra \
      "$GHIDRA_GUI_MAXMEM" \
      "''${GHIDRA_JAVA_OPTIONS:-} ''${GHIDRA_GUI_JAVA_OPTIONS:-}" \
      ghidra.GhidraRun "$@"
  '';
in
{
  environment.systemPackages = [ ghidraFg ] ++ (with pkgs; [
    gdb
    gef
    binutils
    radare2
    rizin
    ghidra
    cutter
    ltrace
    strace
    patchelf
    pwninit
    python3Packages.ropper
    # TODO(unverified): pwndbg
    # TODO(unverified): gef
  ]);
}
