#!/usr/bin/env bash
# A6 — fresh reset: --fresh discards the A5 data.
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}"

rednix stop "$REDNIX_TEST_EVENT" 2>/dev/null || true
rednix start "$REDNIX_TEST_EVENT" --fresh

if rednix exec "$REDNIX_TEST_EVENT" -- test ! -e ~/proof; then
  echo "PASS A6"
else
  echo "FAIL A6: --fresh did not discard guest state"; exit 1
fi
