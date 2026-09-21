#!/usr/bin/env bash
# A3 — scope enforcement (routed): non-allow-listed destinations are dropped and
# guest root cannot flush the rednix nftables table back into a working state.
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}"
echo "REQUIRE: sudo rednix net up $REDNIX_TEST_EVENT --iface <ctf-iface>"
echo "REQUIRE: sudo rednix start $REDNIX_TEST_EVENT --network routed"
echo "then run inside the guest as root:"
echo "  rednix exec $REDNIX_TEST_EVENT -- sudo nft flush table inet rednix-$REDNIX_TEST_EVENT"
echo "  rednix exec $REDNIX_TEST_EVENT -- bash -c '</dev/tcp/10.9.9.9/80'   # must still fail"
echo "and verify: sudo nft list table inet rednix-$REDNIX_TEST_EVENT (policy drop intact)"
[ "${REDNIX_TEST_ROUTED:-}" = "1" ] || { echo "SKIP A3 (REDNIX_TEST_ROUTED=1 to enable)"; exit 0; }
echo "FAIL A3: manual verification required"; exit 1
