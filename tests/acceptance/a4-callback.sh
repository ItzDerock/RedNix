#!/usr/bin/env bash
# A4 — callback forwarding (routed): rednix net callback <port> lets the guest
# reach a host listener (reverse shells work).
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}"
PORT="${REDNIX_TEST_CALLBACK_PORT:-4444}"
[ "${REDNIX_TEST_ROUTED:-}" = "1" ] || { echo "SKIP A4 (REDNIX_TEST_ROUTED=1 to enable)"; exit 0; }

sudo rednix net callback "$REDNIX_TEST_EVENT" "$PORT"
python3 -c "import socket,time; s=socket.socket(); s.bind(('0.0.0.0',$PORT)); s.listen(1); print(s.accept()[1]); time.sleep(5)" &
listener=$!
trap 'kill $listener 2>/dev/null || true' EXIT
sleep 0.5

if rednix exec "$REDNIX_TEST_EVENT" -- timeout 5 bash -c "echo hello >/dev/tcp/10.7.0.1/$PORT"; then
  echo "PASS A4"
else
  echo "FAIL A4: callback connection failed"; exit 1
fi
