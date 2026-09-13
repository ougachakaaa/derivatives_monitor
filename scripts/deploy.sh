#!/usr/bin/env bash
# Host entrypoint. INI values are data; never source/eval the configuration.
set +x
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly script_dir
REPO_ROOT="$(cd -- "$script_dir/.." && pwd -P)"
COLLECTOR_DIR="$REPO_ROOT/collector"
COMPOSE_FILE="$REPO_ROOT/compose.yaml"
COLLECTOR_UID="$(id -u)"
COLLECTOR_GID="$(id -g)"
export REPO_ROOT COLLECTOR_DIR COMPOSE_FILE COLLECTOR_UID COLLECTOR_GID
readonly image_name='derivatives-monitor-collector:local'
readonly config_path="$COLLECTOR_DIR/config.ini"
readonly project_name='derivatives-monitor'
temp_config=''
trap 'if [[ -n "$temp_config" ]]; then rm -f -- "$temp_config"; fi' EXIT

die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
usage() { printf 'Usage: %s {up|logs|status|stop|verify YYYYMMDD}\n' "$0"; }
compose() { docker compose --project-name "$project_name" --file "$COMPOSE_FILE" "$@"; }

check_docker() {
    command -v docker >/dev/null 2>&1 || die 'Docker 未安装或不在 PATH 中。'
    local server
    if ! server=$(docker version --format '{{.Server.Os}}/{{.Server.Arch}}' 2>&1); then
        printf '%s\n' "$server" >&2
        die 'Docker 不可用；请启动 Docker，并在 Docker Desktop 中启用此 WSL 的集成。'
    fi
    case "$server" in linux/amd64|linux/x86_64) ;; *) die '需要 Linux x86-64 Docker Engine。' ;; esac
    docker compose version >/dev/null 2>&1 || die '需要 Docker Compose v2（docker compose）。'
    [[ "$COLLECTOR_DIR" != *,* ]] || die '部署目录不能包含逗号（Docker bind mount 限制）。'
}

ini_value() {
    awk -v key="$1" '
        function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
        { line=trim($0) }
        line == "" || line ~ /^[#;]/ { next }
        line ~ /^\[.*\]$/ { section=trim(substr(line,2,length(line)-2)); next }
        section == "config" { p=index(line,"="); if (p && trim(substr(line,1,p-1))==key) value=trim(substr(line,p+1)) }
        END { print value }
    ' "$2"
}

create_config() {
    [[ ! -e "$config_path" && ! -L "$config_path" ]] || return 0
    [[ -t 0 ]] || die '首次部署需要交互终端填写配置；也可预先创建 collector/config.ini。'
    local default_front default_broker front broker user password instruments
    default_front=$(ini_value FrontMdAddr "$COLLECTOR_DIR/config.example.ini")
    default_broker=$(ini_value BrokerID "$COLLECTOR_DIR/config.example.ini")
    printf '首次配置：请填写已确认的行情接入信息，账号可留空。\n' >&2
    read -r -p "FrontMdAddr [$default_front]: " front
    read -r -p "BrokerID [$default_broker]: " broker
    read -r -p 'UserID（可留空）: ' user
    read -r -s -p 'Password（隐藏输入，可留空）: ' password
    printf '\n' >&2
    read -r -p 'Instruments（精确代码，逗号分隔，必填）: ' instruments
    [[ -n "${instruments//[[:space:]]/}" ]] || die '合约列表不能为空。'
    # Publish atomically without replacing a configuration created by another process.
    temp_config=$(mktemp "$COLLECTOR_DIR/.config-XXXXXX")
    chmod 600 "$temp_config"
    {
        printf '[config]\nFrontMdAddr=%s\nBrokerID=%s\nUserID=%s\nPassword=%s\n' "${front:-$default_front}" "${broker:-$default_broker}" "$user" "$password"
        printf 'UserProductInfo=DM-Linux\nInstruments=%s\n' "$instruments"
        printf 'DataDirectory=data\nFlowPath=flow\nSnapshotIntervalMs=15000\nStatusIntervalSeconds=10\nConnectTimeoutSeconds=120\nRetryIntervalSeconds=5\nSubscriptionBatchSize=100\nRunSeconds=0\n'
    } > "$temp_config"
    unset password
    ln -T -- "$temp_config" "$config_path" || die '配置已存在，未覆盖；请检查后重新运行。'
    rm -f -- "$temp_config"; temp_config=''
    printf '已保存本地配置（权限 0600）；后续运行将复用此文件。\n'
}

check_config() {
    [[ -f "$config_path" && -r "$config_path" ]] || die 'collector/config.ini 不存在或不可读。'
    # Match the C++ parser's section/whitespace/last-value rules. Never print raw lines,
    # since a malformed line can contain credentials. Full field checks run in the image.
    awk '
        function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
        function fail(message) { print "Error: " message > "/dev/stderr"; bad=1 }
        { line=trim($0) }
        line == "" || line ~ /^[#;]/ { next }
        line ~ /^\[.*\]$/ { section=trim(substr(line,2,length(line)-2)); next }
        section == "config" {
            p=index(line,"="); if (!p) { fail("INI syntax error at line " NR); next }
            values[trim(substr(line,1,p-1))]=trim(substr(line,p+1))
        }
        END {
            if (values["FrontMdAddr"]=="") fail("FrontMdAddr is required")
            if (values["Instruments"]=="" && values["InstrumentsFile"]=="") fail("Instruments or InstrumentsFile is required")
            if (values["DataDirectory"]!="" && values["DataDirectory"]!="data") fail("Docker requires DataDirectory=data")
            if (values["FlowPath"]!="" && values["FlowPath"]!="flow") fail("Docker requires FlowPath=flow")
            if (values["RunSeconds"]!="" && values["RunSeconds"]!="0") fail("Docker requires RunSeconds=0")
            if (values["CsvOutputPath"]!="") fail("Collector does not accept CsvOutputPath")
            exit bad ? 1 : 0
        }
    ' "$config_path"
}

check_existing_checkout() {
    local cid mounted service project_files
    # Docker Desktop can represent WSL mounts with an internal path. Use the Compose
    # project config label to identify the checkout instead of comparing mount sources.
    for service in collector query dashboard; do
        cid=$(compose ps --all --quiet "$service")
        [[ -n "$cid" ]] || continue
        project_files=$(docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "$cid")
        [[ "$project_files" == "$COMPOSE_FILE" ]] || die '同名部署属于另一 checkout；请从原目录管理，未替换容器。'
        if [[ "$service" == collector ]]; then
            mounted=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/app/config.ini"}}{{.Source}}{{end}}{{end}}' "$cid")
            [[ -n "$mounted" ]] || die '已有容器缺少预期配置挂载，未替换容器。'
        fi
    done
}

preflight() {
    mkdir -p -- "$COLLECTOR_DIR/data" "$COLLECTOR_DIR/flow"
    docker run --rm --network none --user "$COLLECTOR_UID:$COLLECTOR_GID" \
        --mount "type=bind,src=$config_path,dst=/app/config.ini,readonly" \
        --mount "type=bind,src=$COLLECTOR_DIR/data,dst=/app/data" \
        --mount "type=bind,src=$COLLECTOR_DIR/flow,dst=/app/flow" \
        --entrypoint /bin/sh "$image_name" -ec '
            /opt/collector/data_collector --config /app/config.ini --check-config
            for directory in /app/data /app/flow; do
                probe=$(mktemp "$directory/.deploy-write-XXXXXX") || exit 1
                rm -f "$probe"
            done
            for file in /app/data/* /app/data/.collector.lock /app/flow/*; do
                if [ -e "$file" ] && [ ! -w "$file" ]; then
                    echo "Error: runtime path is not writable: $file" >&2; exit 1
                fi
            done
        '
    docker run --rm --network none --read-only --user "$COLLECTOR_UID:$COLLECTOR_GID" \
        --mount "type=bind,src=$COLLECTOR_DIR/data,dst=/data,readonly" \
        --entrypoint python derivatives-monitor-query:local -c \
        'from query.storage import Store; s=Store("/data"); s.check_directory(); s.days(); print("Query shared directory readable")'
    docker run --rm --network none --read-only --tmpfs /tmp:mode=1777 \
        --user "$COLLECTOR_UID:$COLLECTOR_GID" --entrypoint nginx derivatives-monitor-dashboard:local -t
}

status() {
    local cid service
    for service in collector query dashboard; do
        cid=$(compose ps --all --quiet "$service")
        if [[ -z "$cid" ]]; then printf '%s: 尚未部署。\n' "$service"; continue; fi
        printf '%s: ' "$service"
        docker inspect --format 'status={{.State.Status}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}unknown{{end}} restart_count={{.RestartCount}} last_exit_code={{.State.ExitCode}}' "$cid"
    done
    compose logs --no-color --tail 100 collector | awk '/event=(health|persistence_failed|collector_failed|fatal)/ {print}'
}

[[ $# -ge 1 ]] || { usage >&2; exit 2; }
command_name=$1; shift
case "$command_name" in
    up|logs|status|stop) [[ $# -eq 0 ]] || { usage >&2; exit 2; } ;;
    verify) [[ $# -eq 1 && "$1" =~ ^[0-9]{8}$ ]] || { usage >&2; exit 2; } ;;
    --help|-h|help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
esac
check_docker
case "$command_name" in
    up)
        command -v flock >/dev/null || die '需要 flock（util-linux）。'
        exec 9>"$COLLECTOR_DIR/.deploy.lock"
        flock -n 9 || die '另一个部署操作正在运行。'
        check_existing_checkout
        create_config
        check_config
        compose build collector query dashboard
        preflight
        compose up --detach --no-build --pull never collector query dashboard
        printf '已部署 Collector、FastAPI 和 React 看板（不代表已收到真实行情）。\n看板：http://localhost:%s\nAPI：http://localhost:%s/docs\n日志：%s logs\n状态：%s status\n停止：%s stop\n' "${DASHBOARD_PORT:-8101}" "${QUERY_PORT:-8000}" "$0" "$0" "$0"
        status
        ;;
    logs) compose logs --follow --tail 100 collector query dashboard ;;
    status) status ;;
    stop)
        check_existing_checkout
        compose stop --timeout 60 collector query dashboard
        printf '三个服务已停止；配置、数据和 flow 保留。\n'
        ;;
    verify)
        [[ -f "$COLLECTOR_DIR/data/$1.sqlite" ]] || die "找不到日文件：collector/data/$1.sqlite（不会创建空库）。"
        docker run --rm --network none --read-only --user "$COLLECTOR_UID:$COLLECTOR_GID" \
            --mount "type=bind,src=$COLLECTOR_DIR/data,dst=/app/data,readonly" \
            --entrypoint /bin/sh "$image_name" /opt/collector/verify.sh "$1"
        ;;
esac
