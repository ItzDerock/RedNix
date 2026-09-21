#!/usr/bin/env bash
# A12 — share write-back: guest writes appear on the host with translated uid.
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}"

share=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['share'])" \
  "${REDNIX_STATE_ROOT:-$HOME/.local/state/rednix}/events/$REDNIX_TEST_EVENT/instance.json")

rednix exec "$REDNIX_TEST_EVENT" -- bash -c 'echo from-guest > /work/a12.txt && chown 1000:1000 /work/a12.txt'
[ "$(cat "$share/a12.txt")" = "from-guest" ] || { echo "FAIL A12: write-back missing"; exit 1; }
[ "$(stat -c %u "$share/a12.txt")" = "1000" ] || { echo "FAIL A12: unexpected owner uid"; exit 1; }
rednix exec "$REDNIX_TEST_EVENT" -- rm /work/a12.txt
[ ! -e "$share/a12.txt" ] || { echo "FAIL A12: guest delete did not propagate"; exit 1; }
echo "PASS A12"
