#!/usr/bin/env bash
# Isolated real three-container acceptance. Never touches production data/config.
set -euo pipefail
case "${KEEP_RUNNING:-0}" in 0|1) ;; *) echo 'KEEP_RUNNING must be 0 or 1' >&2; exit 2 ;; esac
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if ! docker version >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo 'Docker Engine + Compose v2 required; three-container test NOT RUN.' >&2; exit 1
fi
work=$(mktemp -d /tmp/dm-read-docker.XXXXXX)
project="dm-read-$(basename "$work" | tr '[:upper:].' '[:lower:]-')"
export COLLECTOR_DIR="$work/collector" QUERY_PORT=0 DASHBOARD_PORT=0
COLLECTOR_UID=$(id -u); COLLECTOR_GID=$(id -g)
export COLLECTOR_UID COLLECTOR_GID
mkdir -p "$COLLECTOR_DIR/data" "$COLLECTOR_DIR/flow"
compose() { docker compose -p "$project" -f "$repo_dir/collector/compose.yaml" -f "$work/override.yaml" "$@"; }
cleanup() {
    local result=$?
    trap - EXIT
    compose logs --no-color > "$work/services.log" 2>&1 || true
    if [[ $result -eq 0 && ${KEEP_RUNNING:-0} == 1 ]]; then
        printf 'Synthetic demo retained (TEST DOUBLE, no real CTP).\nProject: %s\nData: %s/data\n' "$project" "$COLLECTOR_DIR"
        printf 'Dashboard: http://%s\nAPI: http://%s/docs\n' "$(compose port dashboard 8080)" "$(compose port query 8000)"
        printf 'Stop and remove demo containers (data retained): bash %q\n' "$work/stop.sh"
        exit 0
    fi
    compose down --timeout 60 >/dev/null 2>&1 || true
    docker rm -f "$project-extract" >/dev/null 2>&1 || true
    docker image rm "$project:collector" "$project:query" "$project:dashboard" "$project:build" >/dev/null 2>&1 || true
    if [[ $result -eq 0 ]]; then rm -rf -- "$work"; else echo "Synthetic evidence retained at $work" >&2; fi
    exit "$result"
}
trap cleanup EXIT
# A standalone cleanup command remains usable from any working directory.
{
    printf '#!/usr/bin/env bash\nset -euo pipefail\n'
    printf 'export COLLECTOR_DIR=%q COLLECTOR_UID=%q COLLECTOR_GID=%q QUERY_PORT=0 DASHBOARD_PORT=0\n' "$COLLECTOR_DIR" "$COLLECTOR_UID" "$COLLECTOR_GID"
    printf 'docker compose -p %q -f %q -f %q down --timeout 60\n' "$project" "$repo_dir/collector/compose.yaml" "$work/override.yaml"
    printf 'docker image rm %q %q %q %q\n' "$project:collector" "$project:query" "$project:dashboard" "$project:build"
} > "$work/stop.sh"
cat > "$COLLECTOR_DIR/config.ini" <<'INI'
[config]
FrontMdAddr=tcp://127.0.0.1:1
Instruments=IF2609
DataDirectory=data
FlowPath=flow
SnapshotIntervalMs=100
StatusIntervalSeconds=1
ConnectTimeoutSeconds=20
RunSeconds=0
INI
chmod 600 "$COLLECTOR_DIR/config.ini"
cat > "$work/override.yaml" <<YAML
services:
  collector:
    image: $project:collector
    environment:
      LD_PRELOAD: /opt/test/libfake_md.so
    volumes:
      - type: bind
        source: $work/libfake_md.so
        target: /opt/test/libfake_md.so
        read_only: true
  query:
    image: $project:query
  dashboard:
    image: $project:dashboard
YAML
compose build collector query dashboard
docker build -f "$repo_dir/collector/Dockerfile" --target build -t "$project:build" "$repo_dir"
docker create --name "$project-extract" "$project:build" /bin/true >/dev/null
docker cp "$project-extract:/build/libfake_md.so" "$work/libfake_md.so"
docker rm "$project-extract" >/dev/null
chmod 644 "$work/libfake_md.so"
compose up -d --no-build --pull never collector query dashboard

# Query through Nginx using a disposable HTTP client from the backend image.
http() {
    docker run --rm --network "${project}_default" --entrypoint python "$project:query" -c '
import json, sys, urllib.request
with urllib.request.urlopen("http://dashboard:8080" + sys.argv[1], timeout=6) as response:
    value = json.load(response)
for key in sys.argv[2:]: value = value[key]
print(value if isinstance(value, (str, int)) else json.dumps(value))
' "$@"
}
wait_rows() {
    local attempt value
    for ((attempt=0; attempt<45; attempt++)); do
        value=$(http '/api/summary?day=20260907' rows 2>/dev/null) || value=0
        if [[ "$value" =~ ^[0-9]+$ ]] && ((value >= $1)); then return 0; fi
        sleep 1
    done
    echo 'No increasing HTTP snapshot count' >&2; return 1
}
wait_rows 3
http /api/health | tee "$work/health.json"
http '/api/summary?day=20260907' | tee "$work/summary.json"
grep -q 'TEST DOUBLE' "$work/summary.json"
before=$(http '/api/summary?day=20260907' rows)
wait_rows "$((before + 2))"
for service in collector query dashboard; do
    cid=$(compose ps -q "$service")
    healthy=false
    for ((attempt=0; attempt<30; attempt++)); do
        if [[ $(docker inspect -f '{{.State.Health.Status}}' "$cid") == healthy ]]; then healthy=true; break; fi
        sleep 1
    done
    [[ "$healthy" == true ]]
done
compose exec -T dashboard wget -q -O - http://127.0.0.1:8080/ | tee "$work/index.html"
grep -q '/assets/' "$work/index.html"
compose exec -T query python -c '
from pathlib import Path
from storage import Store
assert not Path("/app/config.ini").exists()
try: Path("/data/SHOULD_NOT_EXIST").write_text("bad")
except OSError: pass
else: raise AssertionError("data mount accepted a write")
with Store("/data").connect("20260907") as db:
    import sqlite3
    try: db.execute("DELETE FROM snapshots")
    except sqlite3.OperationalError: pass
    else: raise AssertionError("SQLite accepted a write")
'
collector_id=$(compose ps -q collector)
query_id=$(compose ps -q query)
compose up -d --no-build --pull never collector query dashboard
[[ $(compose ps -q collector) == "$collector_id" && $(compose ps -q query) == "$query_id" ]]
before=$(http '/api/summary?day=20260907' rows)
compose stop query dashboard
sleep 3
[[ $(docker inspect -f '{{.State.Running}}' "$collector_id") == true ]]
compose up -d --no-build --pull never query dashboard
wait_rows "$((before + 2))"
compose stop --timeout 60 collector
[[ $(docker inspect -f '{{.State.ExitCode}}' "$collector_id") == 0 ]]
[[ $(http /api/health collector status) == stopped ]]
[[ $(http '/api/summary?day=20260904' rows) -gt 0 ]]
before=$(http '/api/summary?day=20260907' rows)
[[ $(stat -c '%u:%g' "$COLLECTOR_DIR/data/20260907.sqlite") == "$COLLECTOR_UID:$COLLECTOR_GID" ]]
compose up -d --no-build --pull never --force-recreate collector query
wait_rows "$((before + 2))"
echo 'PASS: three images, app healthchecks, Nginx API proxy, shared readonly WAL, independent stops, persistence and recreation.'
echo 'Synthetic TEST DOUBLE input only; real CTP acceptance remains separate.'
