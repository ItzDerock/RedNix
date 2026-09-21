#!/usr/bin/env bash
# Run all acceptance tests in order; prints PASS/FAIL/SKIP per test.
set -uo pipefail
cd "$(dirname "$0")"

total=0; passed=0; failed=0; skipped=0
for test_script in a*.sh; do
  total=$((total + 1))
  if out=$("$test_script" 2>&1); then
    if grep -q "SKIP" <<<"$out"; then
      skipped=$((skipped + 1)); printf '%-38s SKIP\n' "$test_script"
    else
      passed=$((passed + 1)); printf '%-38s PASS\n' "$test_script"
    fi
  else
    failed=$((failed + 1)); printf '%-38s FAIL\n%s\n' "$test_script" "$out"
  fi
done
echo "----------------------------------------"
echo "total=$total passed=$passed skipped=$skipped failed=$failed"
[ "$failed" -eq 0 ]
