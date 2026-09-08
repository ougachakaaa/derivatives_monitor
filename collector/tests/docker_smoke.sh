#!/usr/bin/env bash
# Real Docker integration test. Uses only uniquely named test images/containers
# and temporary synthetic datasets, never collector/config.ini or collector/data.
set -euo pipefail
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
repo_dir="$(cd -- "$script_dir/../.." && pwd -P)"
if ! docker version >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    echo 'Docker Engine + Compose v2 required; container smoke test NOT RUN.' >&2
    exit 1
fi
server=$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}')
[[ "$server" == linux/amd64 || "$server" == linux/x86_64 ]] || { echo 'Linux x86-64 required' >&2; exit 1; }

work=$(mktemp -d /tmp/dm-docker-smoke.XXXXXX)
test_name="dm-smoke-$(basename "$work" | tr '[:upper:].' '[:lower:]-')"
runtime_image="$test_name:runtime"
build_image="$test_name:build"
extractor="$test_name-extract"
timeout_name="$test_name-timeout"
export COLLECTOR_DIR="$work/collector"
COLLECTOR_UID=$(id -u); COLLECTOR_GID=$(id -g)
export COLLECTOR_UID COLLECTOR_GID
mkdir -p "$COLLECTOR_DIR/data" "$COLLECTOR_DIR/flow" "$work/timeout-data" "$work/timeout-flow"

compose() { docker compose --project-name "$test_name" --file "$repo_dir/compose.yaml" --file "$work/override.yaml" "$@"; }
cleanup() {
    local result=$?
    trap - EXIT
    if [[ -f "$work/override.yaml" ]]; then
        compose logs --no-color > "$work/collector.log" 2>&1 || true
        compose down --timeout 60 >/dev/null 2>&1 || true
    fi
    docker logs "$timeout_name" > "$work/timeout.log" 2>&1 || true
    docker rm --force "$extractor" "$timeout_name" >/dev/null 2>&1 || true
    docker image rm "$runtime_image" "$build_image" >/dev/null 2>&1 || true
    if [[ $result -eq 0 ]]; then rm -rf -- "$work";
    else printf 'Docker smoke failed. Synthetic evidence retained in %s\n' "$work" >&2; fi
    exit "$result"
}
trap cleanup EXIT

echo 'Building production image; its build stage runs all seven CTests.'
docker build --file "$repo_dir/collector/Dockerfile" --target runtime --tag "$runtime_image" "$repo_dir"
docker build --file "$repo_dir/collector/Dockerfile" --target build --tag "$build_image" "$repo_dir"
docker run --rm --network none --entrypoint /bin/sh "$runtime_image" -ec '
    /opt/collector/data_collector --help
    test ! -e /app/config.ini
    test ! -e /src
    test -z "$(find /opt -iname "*fake*" -print)"
    if command -v g++ || command -v python3; then exit 1; fi
    ldd /opt/collector/data_collector > /tmp/ldd
    ! grep -q "not found" /tmp/ldd
'

# Extract only the test shared library into a temporary readonly mount.
docker create --name "$extractor" "$build_image" /bin/true >/dev/null
docker cp "$extractor:/build/libfake_md.so" "$work/libfake_md.so"
docker rm "$extractor" >/dev/null
chmod 644 "$work/libfake_md.so"
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
    image: $runtime_image
    environment:
      LD_PRELOAD: /opt/test/libfake_md.so
    volumes:
      - type: bind
        source: $work/libfake_md.so
        target: /opt/test/libfake_md.so
        read_only: true
YAML

readonly_run() {
    docker run --rm --network none --read-only --user "$COLLECTOR_UID:$COLLECTOR_GID" \
        --mount "type=bind,src=$COLLECTOR_DIR/data,dst=/app/data,readonly" \
        --entrypoint /bin/sh "$runtime_image" "$@"
}
query() {
    # Parameters are expanded by the container shell.
    # shellcheck disable=SC2016
    readonly_run -ec '
        database=/app/data/$1.sqlite
        test -f "$database"
        exec 9</app/data/.collector.lock
        if flock -s -n 9 && [ ! -s "$database-wal" ]; then database="file:$database?mode=ro&immutable=1"; fi
        exec sqlite3 -readonly -batch -bail "$database" "$2"
    ' sh "$1" "$2"
}
wait_for_rows() {
    local attempts count
    for ((attempts=0; attempts<45; attempts++)); do
        count=$(query "$1" "$2" 2>/dev/null) || count=0
        if [[ "$count" =~ ^[0-9]+$ ]] && (( count >= $3 )); then return 0; fi
        sleep 1
    done
    echo 'Timed out waiting for committed synthetic data.' >&2; return 1
}

compose config --quiet
compose up --detach --no-build --pull never collector
cid=$(compose ps --all --quiet collector)
wait_for_rows 20260907 'SELECT COUNT(*) FROM snapshots' 3
before=$(query 20260907 'SELECT COUNT(*) FROM snapshots')
wait_for_rows 20260907 'SELECT COUNT(*) FROM snapshots' "$((before + 2))"
readonly_run /opt/collector/verify.sh 20260907
[[ $(query 20260907 "SELECT COUNT(*) FROM runs WHERE source LIKE '%TEST DOUBLE%'") -ge 1 ]]
compose logs --no-color > "$work/live.log"
grep -q 'event=front_disconnected' "$work/live.log"
grep -q 'connections=2' "$work/live.log"

# Same configuration must retain one service instance.
compose up --detach --no-build --pull never collector
[[ "$cid" == "$(compose ps --all --quiet collector)" ]]

# Ensure the first process has run >10s before testing the restart policy.
sleep 11
restarts=$(docker inspect --format '{{.RestartCount}}' "$cid")
docker exec "$cid" /bin/sh -c 'kill -TERM 1' || true
restarted=false
for ((attempt=0; attempt<45; attempt++)); do
    current=$(docker inspect --format '{{.RestartCount}}' "$cid")
    if (( current > restarts )); then restarted=true; break; fi
    sleep 1
done
[[ "$restarted" == true ]]
wait_for_rows 20260907 'SELECT COUNT(*) FROM runs' 2
compose stop --timeout 60 collector
[[ $(docker inspect --format '{{.State.ExitCode}}' "$cid") == 0 ]]
sleep 2
[[ $(docker inspect --format '{{.State.Status}}' "$cid") == exited ]]
readonly_run /opt/collector/verify.sh 20260904
readonly_run /opt/collector/verify.sh 20260907
[[ $(query 20260907 'SELECT COUNT(*) FROM runs WHERE stopped_us IS NULL') == 0 ]]
before=$(query 20260907 'SELECT COUNT(*) FROM snapshots')

compose up --detach --no-build --pull never --force-recreate collector
wait_for_rows 20260907 'SELECT COUNT(*) FROM snapshots' "$((before + 2))"
wait_for_rows 20260907 'SELECT COUNT(*) FROM runs' 3
compose stop --timeout 60 collector
[[ $(stat -c '%u:%g' "$COLLECTOR_DIR/data/20260907.sqlite") == "$COLLECTOR_UID:$COLLECTOR_GID" ]]
if readonly_run -ec 'sqlite3 -readonly "file:/app/data/20260907.sqlite?immutable=1" "DELETE FROM snapshots"'; then
    echo 'Readonly SQLite unexpectedly accepted a write' >&2; exit 1
fi

# Use the official SDK with no network to test pre-open login timeout/restart.
# Separate data and flow prevent synthetic rows from being mistaken for live data.
docker run --detach --name "$timeout_name" --network none --restart unless-stopped \
    --user "$COLLECTOR_UID:$COLLECTOR_GID" \
    --mount "type=bind,src=$COLLECTOR_DIR/config.ini,dst=/app/config.ini,readonly" \
    --mount "type=bind,src=$work/timeout-data,dst=/app/data" \
    --mount "type=bind,src=$work/timeout-flow,dst=/app/flow" "$runtime_image" >/dev/null
restarted=false
for ((attempt=0; attempt<75; attempt++)); do
    if [[ $(docker inspect --format '{{.RestartCount}}' "$timeout_name") -gt 0 ]]; then restarted=true; break; fi
    sleep 1
done
[[ "$restarted" == true ]]
docker logs "$timeout_name" > "$work/timeout.log" 2>&1
grep -q 'startup connection/login timeout' "$work/timeout.log"
if grep -q 'TEST DOUBLE' "$work/timeout.log"; then echo 'Official SDK test loaded synthetic input' >&2; exit 1; fi
docker stop --time 60 "$timeout_name" >/dev/null
sleep 2
[[ $(docker inspect --format '{{.State.Status}}' "$timeout_name") == exited ]]
if compgen -G "$work/timeout-data/*.sqlite" >/dev/null; then
    echo 'Offline official SDK unexpectedly produced a daily database' >&2; exit 1
fi
echo 'PASS: Docker build, synthetic ingestion, readonly verification, restart, stop and persistent datasets.'
echo 'Real CTP connectivity and market-data acceptance remain separate.'
