#!/usr/bin/env bash
# A9 — stale-state recovery: kill -9 the VM, then start must succeed untouched.
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}"

rednix start "$REDNIX_TEST_EVENT"
state_root="${REDNIX_STATE_ROOT:-$HOME/.local/state/rednix}"
pid=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['pid'])" \
  "$state_root/events/$REDNIX_TEST_EVENT/instance.json")
kill -9 "$pid"
sleep 1

rednix start "$REDNIX_TEST_EVENT" && echo "PASS A9"
