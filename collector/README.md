# C++ Data Collector

Collector 接收 CTP 行情，在内存维护最新状态并定期物化到 Raw 日 SQLite。这里提供构建、配置、运行和排障入口；组件所有权与依赖方向见[系统架构](../docs/architecture.md)，精确采集、持久化、时间和失败语义见 [Collector Contract](../docs/contracts/collector.md)。

相关入口：[Market Session / Universe Contract](../docs/contracts/market-session.md) · [Deployment Contract](../docs/contracts/deployment.md) · [Operations](../docs/operations.md) · [Acceptance](../docs/acceptance.md) · [Harness](../harness/README.md)

统一前台开发入口位于仓库根：`./dev doctor collector` 检查本组件，`./dev collector` 运行本组件，`./dev up` 运行完整开发会话。参数示例和与持久部署的区别见 [Operations](../docs/operations.md#前台开发会话)；下面保留 Collector 自身的构建、直接运行和管理用法。

## 构建与测试

要求 Linux x86-64、CMake ≥ 3.16、C++17 编译器和 SQLite ≥ 3.24 开发包。完整 `offline` Harness 还需要 `sqlite3` CLI 及 Linux Node/npm；若工具解压在被忽略的本地目录，先将各自的 `bin` 目录加入本次 shell 的 `PATH`。仓库内正式 SDK 位于 `collector/third_party/ctp/`，CMake 支持位于 `collector/cmake/ctp_sdk.cmake`；正式 Collector 不依赖 `experiments/`。

从仓库根目录执行：

```bash
cmake -S collector -B collector/build/Release -DCMAKE_BUILD_TYPE=Release
cmake --build collector/build/Release -j
ctest --test-dir collector/build/Release --output-on-failure
```

没有管理员权限时，可显式传入本地 SQLite 开发包：

```bash
cmake -S collector -B collector/build/Release -DCMAKE_BUILD_TYPE=Release \
  -DSQLite3_INCLUDE_DIR=/path/to/include \
  -DSQLite3_LIBRARY=/path/to/libsqlite3.so
```

构建后的正式入口是 `collector/build/Release/bin/data_collector`。共享 SDK 模式下，同目录还需 `thostmduserapi_se.so`；用 `ldd` 检查运行依赖。测试使用的合成 SDK 只用于 TEST DOUBLE，不能加载到正式采集进程。

## 配置与直接运行

```bash
cp collector/config.example.ini collector/config.ini
# 编辑 config.ini，填入有效接入信息和精确合约代码
collector/build/Release/bin/data_collector --config collector/config.ini --check-config
collector/build/Release/bin/data_collector --config collector/config.ini
```

`config.ini`、`data/`、`flow/` 和 `build/` 默认被 Git 忽略。真实凭据不得提交；相对路径以配置文件目录为基准。

| 参数 | 默认值 / 使用说明 |
|---|---|
| `FrontMdAddr` | 必填的行情前置地址；可用性以现场验证为准 |
| `BrokerID`、`UserID`、`Password`、`UserProductInfo` | 按接入方要求填写 |
| `Instruments` | 冒号或逗号分隔的精确合约代码 |
| `InstrumentsFile` | 可选逐行代码文件；命令行合约覆盖文件，文件覆盖 `Instruments` |
| `DataDirectory` | 默认 `data` |
| `FlowPath` | 默认 `flow`；每个运行实例使用独立目录 |
| `SnapshotIntervalMs` | 默认 `15000` |
| `StatusIntervalSeconds` | 默认 `10` |
| `ConnectTimeoutSeconds` | 默认 `20` |
| `RetryIntervalSeconds` | 默认 `5` |
| `SubscriptionBatchSize` | 默认 `100` |
| `RunSeconds` | `0` 表示持续运行 |

CLI 提供 `--config PATH`、可重复的 `--instrument CODE`、`--run-seconds N`、`--check-config` 和 `--help`。完整取值约束、优先级、采样及停止语义以 [Collector Contract](../docs/contracts/collector.md) 为准。

Docker 部署脚本复用已有配置；原生 `up` 的订阅文件配置准备见下节。需要手工调整旧配置时先正常停止 Collector，显式修改配置并保留原数据目录；不要把配置变更当作 schema 迁移。

## 原生 WSL 管理

准备好 Collector build、`query/.venv`、Dashboard 依赖和用户级 systemd 后，从仓库根目录执行：

```bash
./collector/scripts/native.sh up
./collector/scripts/native.sh status
./collector/scripts/native.sh logs
./collector/scripts/native.sh update
./collector/scripts/native.sh stop
```

`up` 校验依赖和配置、刷新 Universe，并管理 Collector、Query、Dashboard 三个用户服务；`update` 可手工刷新公开清单。系统级生命周期、定时更新、重启及数据保护规则见 [Deployment Contract](../docs/contracts/deployment.md) 和 [Operations](../docs/operations.md)。

原生 `up` 会将已有配置备份到 `collector/tmp/native-backups/`，校验候选配置后将 `InstrumentsFile` 设为 `data/universe/current/instruments.txt` 并替换配置文件；它不是只读检查或单纯前台启动。该命令还会启用并重启三个用户服务、启动 Universe timer；`stop` 停止服务和 timer，但不取消 enable。

Windows 浏览器默认访问 **http://localhost:8101**，FastAPI 文档为 **http://localhost:8000/docs**。WSL 或 Windows 停止、睡眠时采集不会继续。若需长期禁用自动启动：

```bash
systemctl --user disable derivatives-monitor-{collector,query,dashboard}.service derivatives-monitor-universe.timer
```

## Docker / WSL 部署

要求 Linux x86-64 Docker Engine、Compose v2、Git 和 Bash。在仓库根目录执行：

```bash
./scripts/deploy.sh up
```

| 命令 | 用途 |
|---|---|
| `./scripts/deploy.sh up` | 首次配置、构建、预检并后台启动；更新代码后也使用此命令 |
| `./scripts/deploy.sh logs` | 跟随 Collector、Query、Dashboard 三服务日志 |
| `./scripts/deploy.sh status` | 查看三服务状态、重启次数和采集健康摘要 |
| `./scripts/deploy.sh stop` | 正常停止并保留数据 |
| `./scripts/deploy.sh verify YYYYMMDD` | 在隔离容器中只读检查指定交易日 |

首次运行会创建权限受限的 `collector/config.ini`；已有配置原样复用。默认页面端口为 8101、API 端口为 8000，可通过 `DASHBOARD_PORT` 和 `QUERY_PORT` 调整。Compose 和各服务 build boundary 的权威定义见 [Deployment Contract](../docs/contracts/deployment.md)，更新、停止、备份和恢复步骤见 [Operations](../docs/operations.md)。

不要同时运行原生 Collector 和 Docker Collector 写同一数据目录。需要保留 Query/Dashboard 而只停止容器 Collector 时：

```bash
docker stop --time 60 "$(docker ps -q --filter label=com.docker.compose.project=derivatives-monitor --filter label=com.docker.compose.service=collector)"
```

恢复采集仍执行 `./scripts/deploy.sh up`。

## Universe discovery

公开合约清单工具独立于行情 callback。手工运行：

```bash
python3 collector/scripts/universe.py --data-dir collector/data
python3 collector/scripts/universe.py --data-dir collector/data --date YYYYMMDD
```

输出保存在 `collector/data/universe/`；原生管理器使用 `current/instruments.txt`。工具的来源、日期选择、完整性、保留旧清单和失败行为由 [Market Session / Universe Contract](../docs/contracts/market-session.md) 定义。查看完整参数用 `--help`，运行工具测试：

```bash
python3 -m unittest discover -s collector/tests -p 'test_*.py' -v
```

## 查看数据与运行状态

优先使用管理入口：

```bash
./collector/scripts/native.sh status
./collector/scripts/native.sh logs
./scripts/deploy.sh status
./scripts/deploy.sh verify YYYYMMDD
```

日志中常用事件包括 `front_connected`、`login_response`、`subscription_response`、`health`、`snapshot_commit`、`persistence_failed` 和 `stop`。连接、订阅、接收、写入和市场时段是不同证据；精确状态含义见 [Collector Contract](../docs/contracts/collector.md) 与 [Read Path Contract](../docs/contracts/read-path.md)。

可选的只读 SQLite 快速检查：

```bash
sqlite3 -readonly collector/data/YYYYMMDD.sqlite \
  'SELECT TradingDay,InstrumentID,UpdateTime,LastPrice,received_us FROM snapshots ORDER BY id DESC LIMIT 5;'
```

这只是诊断入口，不定义 Raw schema。活跃库、WAL、锁、历史日及备份的安全读取方式见 [Read Path Contract](../docs/contracts/read-path.md) 和 [Operations](../docs/operations.md)。

## 常见问题

- **配置检查失败**：先运行 `--check-config`，确认前置、凭据、精确合约和相对目录；不要提交真实配置。
- **已连接但没有数据**：在日志中分别核对登录、订阅响应、接收与 `snapshot_commit`；休市或不活跃合约不能直接判定进程故障。
- **历史日读取返回错误**：不要删除 WAL 或放宽只读权限；按 [Operations](../docs/operations.md) 正常停采后检查或做隔离恢复。
- **Docker 命令不可用**：确认 `docker version` 和 `docker compose version` 均能连接 Linux Engine；不要通过清理数据目录修复环境。
- **需要 AU/AG 夜盘回归**：构建 Collector 并准备 Query 环境后运行：

  ```bash
  query/.venv/bin/python tests/night_session_smoke.py
  ```

  该测试使用合成 SDK 和压缩时间，只是 TEST DOUBLE。真实跨日状态与待补证据见 [Acceptance](../docs/acceptance.md)。
