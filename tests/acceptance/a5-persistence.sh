#!/usr/bin/env bash
# A5 — state persistence: data written to $HOME and /var/lib/postgresql
# survives stop → start.
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}"

rednix exec "$REDNIX_TEST_EVENT" -- bash -c 'echo persisted > ~/proof && sudo systemctl start postgresql && sudo -u postgres psql -c "select 1" >/dev/null'
rednix stop "$REDNIX_TEST_EVENT"
rednix start "$REDNIX_TEST_EVENT"

if rednix exec "$REDNIX_TEST_EVENT" -- grep -q persisted ~/proof; then
  echo "PASS A5 (home persisted)"
else
  echo "FAIL A5: home did not persist"; exit 1
fi
