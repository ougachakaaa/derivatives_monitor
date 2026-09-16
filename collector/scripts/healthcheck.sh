#!/bin/sh
# Main-loop liveness only. Market inactivity is not a failure.
set -eu
# Optional native arguments: minimum run started_us, then the bound run_id.
# Native mode prints the accepted run_id; the original Docker interface stays silent.
status=${1:-/app/data/collector-runtime.sqlite}
minimum=${2:-0}
expected=${3:-}
fail() { printf '%s\n' "$1" >&2; exit 1; }
case "$minimum" in ''|*[!0-9]*) fail invalid_minimum;; esac
test "${#minimum}" -le 18 || fail invalid_minimum
test -f "$status" && test ! -L "$status" || fail runtime_missing_or_symlink
for suffix in -journal -wal -shm; do
    test ! -L "$status$suffix" || fail runtime_sidecar_symlink
done
# Hashing the schema rows after whitespace removal identifies the complete current protocol.
snapshot=$(sqlite3 -readonly -cmd '.timeout 100' "$status" "
PRAGMA query_only=ON;
BEGIN;
SELECT type||name||sql FROM sqlite_master
 WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' ORDER BY type,name;
SELECT COALESCE((SELECT heartbeat_us||'|'||current_status.run_id||'|'||started_us
 FROM current_status JOIN runs USING(run_id) WHERE singleton=1
 AND (SELECT journal_mode FROM pragma_journal_mode)='delete'
 AND process_state IN ('starting','running')
 AND typeof(heartbeat_us)='integer' AND heartbeat_us > 0
 AND typeof(started_us)='integer' AND started_us > 0
 AND ended_us IS NULL AND terminal_state IS NULL), 'unavailable');
ROLLBACK;") || fail runtime_unreadable
facts=$(printf '%s\n' "$snapshot" | tail -n 1)
schema=$(printf '%s\n' "$snapshot" | sed '$d' | tr -d '[:space:]')
schema_hash=$(printf '%s' "$schema" | sha256sum)
test "${schema_hash%% *}" = '8fb54c462453fc5b4319604b289472fa6e6265fcadc94778cb9d69292e1d53e5' || fail runtime_schema
test "$facts" != unavailable || fail runtime_unavailable
heartbeat=${facts%%|*}
rest=${facts#*|}
run_id=${rest%%|*}
started=${rest#*|}
case "$heartbeat:$started" in *[!0-9:]*) fail runtime_invalid_time;; esac
case "$run_id" in ''|*[!0-9a-f]*) fail runtime_invalid_run;; esac
test "${#run_id}" -eq 32 || fail runtime_invalid_run
test "$started" -ge "$minimum" || fail runtime_previous_process
test -z "$expected" || test "$run_id" = "$expected" || fail runtime_run_changed
# Evaluate time after reading the snapshot, so a concurrent publication cannot look future-dated.
now_us=$(date +%s%6N)
age_us=$((now_us - heartbeat))
test "$age_us" -ge 0 || fail heartbeat_future
test "$age_us" -le 10000000 || fail heartbeat_stale
if test "$#" -ge 2; then printf '%s\n' "$run_id"; fi
