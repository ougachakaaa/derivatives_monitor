#!/bin/sh
# Container process/main-loop liveness. Market inactivity is not a failure.
set -eu
status=/app/data/.collector-status.json
test -f "$status"
now=$(date +%s)
modified=$(stat -c %Y "$status")
age=$((now - modified))
test "$age" -ge 0 && test "$age" -le 10
grep -Eq '"process_state": "(starting|running)"' "$status"
