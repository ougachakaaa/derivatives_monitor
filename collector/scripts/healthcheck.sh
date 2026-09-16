#!/bin/sh
# Main-loop liveness only. Market inactivity is not a failure.
set -eu
status=${1:-/app/data/collector-runtime.sqlite}
test -f "$status" && test ! -L "$status"
for suffix in -journal -wal -shm; do
    test ! -L "$status$suffix"
done
# Hashing the schema rows after whitespace removal identifies the complete current protocol.
snapshot=$(sqlite3 -readonly -cmd '.timeout 100' "$status" "
BEGIN;
SELECT type||name||sql FROM sqlite_master
 WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name;
SELECT heartbeat_us FROM current_status WHERE singleton=1
 AND (SELECT journal_mode FROM pragma_journal_mode)='delete'
 AND process_state IN ('starting','running')
 AND typeof(heartbeat_us)='integer' AND heartbeat_us > 0;
ROLLBACK;")
heartbeat=$(printf '%s\n' "$snapshot" | tail -n 1)
schema=$(printf '%s\n' "$snapshot" | sed '$d' | tr -d '[:space:]')
schema_hash=$(printf '%s' "$schema" | sha256sum)
test "${schema_hash%% *}" = '8fb54c462453fc5b4319604b289472fa6e6265fcadc94778cb9d69292e1d53e5'
case "$heartbeat" in ''|*[!0-9]*) exit 1;; esac
# Evaluate time after reading the snapshot, so a concurrent publication cannot look future-dated.
now_us=$(date +%s%6N)
age_us=$((now_us - heartbeat))
test "$age_us" -ge 0 && test "$age_us" -le 10000000
