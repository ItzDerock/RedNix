#!/usr/bin/env bash
# A7 — destroy preserves the share: VM state goes, shared files stay.
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}"

rednix start "$REDNIX_TEST_EVENT"
share=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['share'])" \
  "$([ -n "${REDNIX_STATE_ROOT:-}" ] && echo "$REDNIX_STATE_ROOT" || echo "$HOME/.local/state/rednix")/events/$REDNIX_TEST_EVENT/instance.json")
echo "keepme" > "$share/a7-proof.txt"

rednix destroy "$REDNIX_TEST_EVENT" --yes

[ ! -e "$HOME/.local/state/rednix/events/$REDNIX_TEST_EVENT" ] || { echo "FAIL A7: event dir remains"; exit 1; }
[ -f "$share/a7-proof.txt" ] || { echo "FAIL A7: shared file was deleted"; exit 1; }
echo "PASS A7"
