#!/usr/bin/env bash
# A2 — blocked host service: a host localhost listener is unreachable from the guest.
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}"
PORT="${REDNIX_TEST_LISTEN_PORT:-4567}"

python3 -c "import socket,time; s=socket.socket(); s.bind(('127.0.0.1',$PORT)); s.listen(1); time.sleep(120)" &
listener=$!
trap 'kill $listener 2>/dev/null || true' EXIT
sleep 0.5

if rednix exec "$REDNIX_TEST_EVENT" -- timeout 5 bash -c "</dev/tcp/10.0.2.2/$PORT" 2>/dev/null; then
  echo "FAIL A2: guest reached a host service"; exit 1
fi
echo "PASS A2"
