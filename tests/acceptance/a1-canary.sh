#!/usr/bin/env bash
# A1 — host-only canary: from the guest, /work is the ONLY reachable host path.
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}" "${REDNIX_TEST_CANARY:?}"
echo "host secret" > "$REDNIX_TEST_CANARY"

if rednix exec "$REDNIX_TEST_EVENT" -- cat "$REDNIX_TEST_CANARY" 2>/dev/null; then
  echo "FAIL A1: guest read a host-only canary"; exit 1
fi
if rednix exec "$REDNIX_TEST_EVENT" -- find / -xdev -name "$(basename "$REDNIX_TEST_CANARY")" 2>/dev/null | grep -q .; then
  echo "FAIL A1: guest found the host-only canary"; exit 1
fi
echo "PASS A1"
