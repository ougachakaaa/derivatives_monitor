# C++ Data Collector

Collector 接收 CTP 行情，按 event time 聚合自然时间对齐的 15 秒 Market Bar，并将已封口 Bar 写入 Raw 日 SQLite。这里提供构建、配置、直接运行和排障入口；本级工作路径见 [AGENTS](AGENTS.md)，内部关系见 [Architecture](ARCHITECTURE.md)，精确采集行为见 [Contract](CONTRACT.md)。共享持久化与读取协议见 [Raw Boundary](../docs/contracts/raw-boundary.md)，当前代码与目标契约的差距见[根 Acceptance](../docs/acceptance.md)。

相关入口：[Market Session / Universe Contract](../docs/contracts/market-session.md) · [Deployment Contract](../docs/contracts/deployment.md) · [Operations](../docs/operations.md) · [Acceptance](../docs/acceptance.md) · [Verification](../tests/README.md)

统一前台开发入口位于仓库根：`./dev doctor collector` 检查本组件，`./dev up collector` 运行本组件，`./dev up` 运行完整开发会话。参数示例和与持久部署的区别见 [Operations](../docs/operations.md#前台开发会话)；下面保留 Collector 自身的构建、直接运行和管理用法。

## 构建与测试

要求 Linux x86-64、CMake ≥ 3.16、C++17 编译器和 SQLite ≥ 3.24 开发包。完整 `offline` verification profile 还需要 `sqlite3` CLI 及 Linux Node/npm；若工具解压在被忽略的本地目录，先将各自的 `bin` 目录加入本次 shell 的 `PATH`。仓库内正式 SDK 位于 `collector/third_party/ctp/`，CMake 支持位于 `collector/cmake/ctp_sdk.cmake`；正式 Collector 不依赖 `experiments/`。

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

`config.ini`、`data/`、`flow/` 和 `build/` 默认被 Git 忽略，真实凭据不得提交。可用键、默认值、相对路径、订阅来源优先级和 CLI 覆盖规则统一见 [Collector Contract](CONTRACT.md#行情接入与配置接口)；实际模板是 [`config.example.ini`](config.example.ini)。

需要手工调整旧配置时先正常停止 Collector，删除已退役的 `SnapshotIntervalMs`，显式修改配置并保留原数据目录；不要把配置变更当作 schema 迁移。Universe、native manager 及镜像辅助命令见 [`collector/scripts` 手册](scripts/README.md)；完整三服务部署、配置准备、更新、停止与恢复步骤见 [Operations](../docs/operations.md)。

## 查看数据与运行状态

优先使用管理入口：

```bash
./scripts/deploy.sh status
./scripts/deploy.sh verify YYYYMMDD
```

日志中常用事件包括 `front_connected`、`login_response`、`subscription_response`、`health`、`bar_commit`、`persistence_failed` 和 `stop`。连接、订阅、callback 接收、Bar 写入和市场时段是不同证据；精确状态含义见 [Collector Contract](CONTRACT.md) 与 [Read Path Contract](../docs/contracts/read-path.md)。

可选的只读 SQLite 快速检查：

```bash
sqlite3 -readonly collector/data/YYYYMMDD.sqlite \
  'SELECT TradingDay,InstrumentID,bucket_start_us,bar_close,last_event_us,is_partial FROM market_bars ORDER BY id DESC LIMIT 5;'
```

这只是诊断入口，不定义 Raw schema。活跃库、WAL、锁、历史日及备份的安全读取边界见 [Raw Boundary](../docs/contracts/raw-boundary.md)，实际操作见 [Operations](../docs/operations.md)。

日库只发布 Raw schema v2 `market_bars`；不存在运行时采样间隔配置，也不兼容或迁移旧 `snapshots` 日库。精确物理 schema 与拒绝规则由 [Raw Boundary](../docs/contracts/raw-boundary.md#sqlite-v2-物理契约)冻结。

## 常见问题

- **配置检查失败**：先运行 `--check-config`，确认前置、凭据、精确合约和相对目录；不要提交真实配置。
- **已连接但没有数据**：在日志中分别核对登录、订阅响应、callback 接收与 `bar_commit`；休市或不活跃合约不能直接判定进程故障。
- **历史日读取返回错误**：不要删除 WAL 或放宽只读权限；按 [Operations](../docs/operations.md) 正常停采后检查或做隔离恢复。
- **Docker 命令不可用**：确认 `docker version` 和 `docker compose version` 均能连接 Linux Engine；不要通过清理数据目录修复环境。
- **需要 AU/AG 夜盘回归**：构建 Collector 并准备 Query 环境后运行：

  ```bash
  query/.venv/bin/python tests/night_session_smoke.py
  ```

  该测试使用合成 SDK 和压缩时间，只是 TEST DOUBLE。真实跨日状态与待补证据见 [Acceptance](../docs/acceptance.md)。

## SDK 来源

构建使用已入库的 **v6.7.13_20260225 / Linux x86-64 Market Data** 最小 SDK，无需联网下载。原包及头文件、动态库哈希见 [MANIFEST](third_party/ctp/v6.7.13_20260225/MANIFEST.txt)；头文件仅将注释由 GB18030 转为 UTF-8，二进制未改。原包名含 trader 不代表使用 Trader API。

官方入口：[上期技术](https://www.sfit.com.cn/5_2_DocumentDown_2.htm)、[SimNow](https://www.simnow.com.cn/static/apiDownload.action)。这些是查找入口，不是已确认可用的固定版本直链；重新取得原包时必须核对清单哈希。
