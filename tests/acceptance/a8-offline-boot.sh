#!/usr/bin/env bash
# A8 — offline boot: with networking physically down, start + both GUI paths +
# a sample challenge work with zero nix evaluation. [manual]
set -euo pipefail
echo "REQUIRE: unplug ethernet / disable wifi, then reboot the host."
echo "then, in order:"
echo "  rednix start $REDNIX_TEST_EVENT"
echo "  rednix gui $REDNIX_TEST_EVENT xterm"
echo "  rednix desktop $REDNIX_TEST_EVENT"
echo "  rednix exec $REDNIX_TEST_EVENT -- ls /work"
echo "Verify no process invoked `nix` during start: journalctl or a shell wrapper."
[ "${REDNIX_TEST_OFFLINE:-}" = "1" ] || { echo "SKIP A8 (REDNIX_TEST_OFFLINE=1 to enable)"; exit 0; }
echo "FAIL A8: manual verification required"; exit 1
