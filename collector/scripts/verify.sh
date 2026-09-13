#!/bin/sh
# Runs inside the image. Both the mount and the SQLite connection are read-only.
set -eu
if [ "$#" -ne 1 ]; then echo 'Usage: verify.sh YYYYMMDD' >&2; exit 2; fi
day=$1
case "$day" in ''|*[!0-9]*) echo 'Invalid trading day' >&2; exit 2 ;; esac
if [ "${#day}" -ne 8 ]; then echo 'Invalid trading day' >&2; exit 2; fi
database="/app/data/$day.sqlite"
if [ ! -f "$database" ]; then echo "Missing daily database: $day" >&2; exit 1; fi

# A cleanly closed WAL database has no sidecars. SQLite otherwise tries to create
# them even for mode=ro. Immutable is safe ONLY while we hold the Collector's lock
# and there is no nonempty WAL to recover. Never use it against an active writer.
if [ -f /app/data/.collector.lock ]; then
    exec 9</app/data/.collector.lock
    if flock -s -n 9 && [ ! -s "$database-wal" ]; then
        database="file:$database?mode=ro&immutable=1"
    fi
fi

result=$(sqlite3 -readonly -batch -bail "$database" <<SQL
.timeout 1000
PRAGMA query_only=ON;
BEGIN;
SELECT CASE WHEN (SELECT user_version FROM pragma_user_version)=2
 AND (SELECT application_id FROM pragma_application_id)=1145914161
 THEN 'schema_ok' ELSE 'schema_invalid' END;
SELECT CASE WHEN COUNT(*)=1 AND MIN(trading_day)='$day' AND MIN(schema_version)=2
 AND MIN(bar_interval_us)=15000000 AND MIN(close_grace_us)=1000000
 THEN 'dataset_ok' ELSE 'dataset_invalid' END FROM dataset;
SELECT CASE WHEN COUNT(*)>0 AND COUNT(TradingDay)=COUNT(*)
 AND MIN(TradingDay)='$day' AND MAX(TradingDay)='$day'
 AND COUNT(DISTINCT TradingDay||':'||InstrumentID||':'||bucket_start_us)=COUNT(*)
 AND COUNT(*)=SUM(bucket_end_us=bucket_start_us+15000000)
 AND COUNT(*)=SUM(bucket_start_us%15000000=0)
 AND COUNT(*)=SUM(callback_count>0 AND valid_last_price_count BETWEEN 0 AND callback_count)
 AND COUNT(*)=SUM(first_event_us>=bucket_start_us AND first_event_us<=last_event_us AND last_event_us<bucket_end_us)
 AND COUNT(*)=SUM((is_partial=0 AND partial_reasons='[]') OR (is_partial=1 AND partial_reasons!='[]'))
 AND NOT EXISTS(SELECT 1 FROM pragma_foreign_key_check)
 THEN 'market_bars_ok' ELSE 'market_bars_invalid_or_empty' END FROM market_bars;
PRAGMA integrity_check;
.headers on
.mode column
SELECT trading_day, schema_version FROM dataset;
SELECT InstrumentID, COUNT(*) AS bars, SUM(is_partial) AS partial_bars,
 datetime(MAX(last_event_us)/1000000.0,'unixepoch','+8 hours') AS last_event_beijing,
 datetime(MAX(committed_us)/1000000.0,'unixepoch','+8 hours') AS last_commit_beijing
 FROM market_bars GROUP BY InstrumentID;
SELECT run_id, source, started_us, stopped_us FROM runs ORDER BY started_us;
COMMIT;
SQL
) || {
    echo 'Daily SQLite query failed; verification did not pass.' >&2
    echo 'If this is a closed historical WAL file without sidecars while another day is being collected, stop the Collector normally and retry. Do not delete WAL files.' >&2
    exit 1
}

checks=$(printf '%s\n' "$result" | head -n 4)
expected=$(printf 'schema_ok\ndataset_ok\nmarket_bars_ok\nok')
if [ "$checks" != "$expected" ]; then
    printf 'Daily SQLite verification failed:\n%s\n' "$checks" >&2
    exit 1
fi
printf '%s\n' "$result"
printf 'Daily SQLite checks passed. This does not establish live feed freshness; compare repeated observations.\n'
