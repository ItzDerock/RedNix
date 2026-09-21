#!/usr/bin/env bash
# A11 — GUI smoke: waypipe window, --xwls X11 window, desktop reconnect. [manual]
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}"
echo "run and confirm visually in Hyprland:"
echo "  rednix gui $REDNIX_TEST_EVENT xterm          # window title starts with [RedNix]"
echo "  rednix gui --xwls $REDNIX_TEST_EVENT xeyes   # X11 client under xwayland-satellite"
echo "  rednix desktop $REDNIX_TEST_EVENT            # opens; close viewer; rerun reconnects"
[ "${REDNIX_TEST_GUI:-}" = "1" ] || { echo "SKIP A11 (REDNIX_TEST_GUI=1 to enable)"; exit 0; }
echo "FAIL A11: manual verification required"; exit 1
