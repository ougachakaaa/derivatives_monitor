#!/bin/sh
# Main-loop liveness only. Market inactivity is not a failure.
set -eu
status=${1:-/app/data/collector-runtime.sqlite}
test -f "$status" && test ! -L "$status"
for suffix in -journal -wal -shm; do
    test ! -L "$status$suffix"
done
heartbeat=$(sqlite3 -readonly -cmd '.timeout 100' "$status" "
BEGIN;
SELECT heartbeat_us FROM current_status WHERE singleton=1
 AND (SELECT journal_mode FROM pragma_journal_mode)='delete'
 AND (SELECT group_concat(name, ',') FROM
      (SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name))
     ='current_status,instrument_status,runs,runtime_snapshots'
 AND EXISTS(SELECT 1 FROM runs WHERE runs.run_id=current_status.run_id)
 AND process_state IN ('starting','running')
 AND typeof(heartbeat_us)='integer' AND heartbeat_us > 0;
ROLLBACK;")
case "$heartbeat" in ''|*[!0-9]*) exit 1;; esac
# Evaluate time after reading the snapshot, so a concurrent publication cannot look future-dated.
now_us=$(date +%s%6N)
age_us=$((now_us - heartbeat))
test "$age_us" -ge 0 && test "$age_us" -le 10000000
