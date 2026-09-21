#!/usr/bin/env bash
# A10 — static vs dynamic binaries: static runs directly, dynamic via fhs,
# Ubuntu-linked via the preloaded container.
set -euo pipefail
: "${REDNIX_TEST_EVENT:?}"

rednix exec "$REDNIX_TEST_EVENT" -- bash -c 'printf "int main(){return 0;}" > t.c && gcc -static -o static-bin t.c && gcc -o dynamic-bin t.c'
rednix exec "$REDNIX_TEST_EVENT" -- ./static-bin                      # must succeed
rednix exec "$REDNIX_TEST_EVENT" -- fhs ./dynamic-bin                 # must succeed
rednix exec "$REDNIX_TEST_EVENT" -- docker run --rm -v /work:/work ubuntu:24.04 /bin/true
echo "PASS A10"
