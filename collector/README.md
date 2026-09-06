# C++ Data Collector

独立链路：CTP → 内存最新行情 → 定时 snapshot → 按交易日 SQLite。仅依赖 C++17/Linux、CTP 行情 SDK、SQLite 和系统线程库，无 Python/Browser/HTTP 服务。

[设计约束](../docs/Data_Collector_Constraints_CN.md) · [Task Specs](../docs/tasks/data-collector/README.md) · [验收记录](../docs/Data_Collector_Acceptance_CN.md)

## Docker / WSL 一条命令部署

另一台机器只需 Git、Bash、可用的 Linux x86-64 Docker Engine 和 Compose v2。无需在宿主安装 CMake、G++、SQLite 或 Python。将代码放到 WSL 的 Linux 用户目录，例如 `~/repo/derivatives_monitor`，确认 Docker Desktop 已启动且启用该 WSL 的集成；容器无法在 Windows 睡眠或 WSL 停止时继续采集。

拉取包含 Docker 部署实现的代码后，在仓库根目录执行：

```bash
./collector/scripts/deploy.sh up
```

首次运行依次询问前置、BrokerID、UserID、隐藏输入的密码和精确合约代码。账号按前置要求填写，可留空；合约必填，先选一个已确认的期货和一个活跃期权。连接地址的示例默认值不代表现场一定可用。

脚本以 0600 权限保存 `collector/config.ini`，然后构建镜像、运行五项 CTest、校验配置及目录权限，最后后台启动。首次拉取基础镜像及安装编译依赖需要联网，建议开盘前提前完成。首次非交互运行必须预先准备 INI，脚本不会猜测合约。

已有配置原样复用，不再次询问或覆盖。Docker 入口要求以下值（省略时沿用相同默认值）：

```ini
DataDirectory=data
FlowPath=flow
RunSeconds=0
```

如果之前手工设置了绝对目录或定时退出，请自行调整以上三项。首次生成的 Docker 配置使用 `ConnectTimeoutSeconds=120`、`SnapshotIntervalMs=1000`、`StatusIntervalSeconds=10`；已有配置中的其他有效参数保持原值。数据与 flow 保留在宿主对应目录，配置只读挂载，文件按调用用户 UID/GID 写入；通常不要用 sudo 执行部署脚本。

| 命令 | 用途 |
|---|---|
| `./collector/scripts/deploy.sh up` | 首次配置、构建及后台启动；更新代码后也运行此命令 |
| `./collector/scripts/deploy.sh logs` | 跟随最近 100 行日志；Ctrl+C 只结束日志查看 |
| `./collector/scripts/deploy.sh status` | 查看容器状态、重启次数、最近退出码和采集健康日志 |
| `./collector/scripts/deploy.sh stop` | 发送 SIGTERM，最多等待 60 秒完成尾部提交；保留全部数据 |
| `./collector/scripts/deploy.sh verify 20260907` | 在临时容器中只读验收指定交易日，日期按实际文件修改 |

构建或预检失败不会先停止原容器；新配置验证通过后才更新服务。每个 Docker Engine 使用固定 Compose 项目名 `derivatives-monitor`，只管理一个 Collector；另一 checkout 不能通过 `up/stop` 替换或停止原 checkout 的实例。需要迁移时先从原目录正常停止并移除原 Compose 容器，再安排数据目录迁移。不要同时运行原生 Collector 和 Docker Collector 写同一目录。

容器采用 `unless-stopped`：8:50 前置未就绪时，连接/登录超时退出后由 Docker 自动重新启动；已登录后的断线恢复仍由 SDK 处理。显式 `stop` 后保持停止，下一次 `up` 恢复。持久化或登录持续失败也可能反复重启，需观察 `restart_count` 和错误日志，不能把 `running` 当成行情健康。首次退出过快时 Docker 的重启策略也有启动监控条件，详见 [Docker 官方重启说明](https://docs.docker.com/engine/containers/start-containers-automatically/)。

日志保存在 Docker，由 `json-file` 驱动轮转（每份 10MB、保留三份）。更新容器可能丢弃旧容器日志，重要验收证据可在更新前导出：

```bash
mkdir -p collector/logs
docker logs "$(docker ps -aq --filter label=com.docker.compose.project=derivatives-monitor --filter label=com.docker.compose.service=collector)" > collector/logs/docker-acceptance.log 2>&1
```

`verify` 检查 schema 版本、交易日身份、非空 snapshot、外键与 `integrity_check`，输出各合约行数、最近接收时间和 run 来源。它只证明当时文件有效；开盘后要间隔执行两次，并结合 `logs` 确认行情和写入推进。

验收器的目录挂载与 SQLite 连接都只读。对于正常停机且没有 WAL 的库，验收器在持有 Collector 目录共享锁期间使用 `immutable`，避免 SQLite 尝试创建 sidecar；该模式不会用于正在写入的数据。若正在采集其他交易日，而所查历史日缺少 sidecar，请正常 `stop` 后再验收。异常结束留下的 WAL 不得删除；必要时先正常启动 Collector 完成 SQLite 恢复再查询。

Docker 未就绪、配置错误、构建失败、目录不可写、日文件不存在或验收失败均返回非零退出码。`up` 的“已部署”不表示已通过真实 CTP 验收。周一仍需确认登录、逐合约订阅、持续接收和 `snapshot_commit`，见 [实盘验收步骤](../docs/Data_Collector_Acceptance_CN.md)。

部署实现与验证边界见 [Docker 验收记录](../docs/Data_Collector_Docker_Acceptance_CN.md)。

## 构建与测试

Linux x86-64，CMake ≥ 3.16，C++17 编译器，SQLite ≥ 3.24 开发包。Ubuntu/Debian 可用 `build-essential cmake libsqlite3-dev`（`sqlite3` 命令行工具可选）。使用仓库内官方 v6.7.13 SDK，CMake 共享原 demo 的 SDK 查找/链接规则。

在仓库根目录：

```bash
cmake -S collector -B collector/build/Release -DCMAKE_BUILD_TYPE=Release
cmake --build collector/build/Release -j
ctest --test-dir collector/build/Release --output-on-failure
```

没有管理员权限时，可以将开发包解压到用户目录，再显式指定 `-DSQLite3_INCLUDE_DIR=/path/to/include -DSQLite3_LIBRARY=/path/to/libsqlite3.so`。不自动下载编译依赖。部署仅需 `bin/data_collector`、同目录的 `thostmduserapi_se.so`、系统 SQLite 运行库和配置；测试程序/`libfake_md.so` 不属于部署产物。CTP 动态库通过 `$ORIGIN` 加载，可用 `ldd` 确认无缺失依赖。

CTest 五项：config、state、storage、runtime、process。全部离线；process 仅对子进程通过 `LD_PRELOAD` 注入合成 SDK，执行真实 Collector CLI，日志明确 `TEST DOUBLE`。官方 SHARED 模式下启用该进程测试；STATIC 需要另备官方静态库，当前仓库没有。正式采集时不要加载测试库。

## 配置与启动

```bash
cp collector/config.example.ini collector/config.ini
# 编辑 config.ini，填入当前有效的精确合约代码与接入信息
collector/build/Release/bin/data_collector --config collector/config.ini --check-config
collector/build/Release/bin/data_collector --config collector/config.ini
```

`config.ini`、默认 `data/`、`flow/`、`build/` 已忽略。真实配置和凭据不要提交。示例 `Instruments` 故意留空，空 universe 会拒绝启动，不会把只登录的探测误当成采集。行情 API 不查询上市合约；合约清单由操作人维护。

| 参数 | 默认/语义 |
|---|---|
| `FrontMdAddr` | 必填，沿用券商示例前置；可用性以现场验证为准 |
| `BrokerID`, `UserID`, `Password`, `UserProductInfo` | 沿用 demo，按 SDK 固定字段长度校验；是否需账号取决于前置 |
| `Instruments` | 冒号或逗号分隔的精确代码，去重；最多 10000 个 |
| `DataDirectory` | `data`，所有每日数据及 `.collector.lock` 所在目录 |
| `FlowPath` | `flow`，SDK 会话文件；每个运行实例使用独立目录 |
| `SnapshotIntervalMs` | `1000`，1–60000ms；控制物化间隔，不保证硬实时 |
| `StatusIntervalSeconds` | `10`，1–3600 秒 |
| `ConnectTimeoutSeconds` | `20`，1–3600 秒；启动连接/登录总窗口，也是单次登录/订阅响应超时 |
| `RetryIntervalSeconds` | `5`，1–300 秒；登录及本地订阅请求拒绝后的重试间隔 |
| `SubscriptionBatchSize` | `100`，1–100；最多每秒发一批（保守应用选择，并非声称 SDK 固定上限） |
| `RunSeconds` | `0` 持续运行；正数表示首次成功登录后的运行秒数，断线期间仍计时 |

INI 相对路径均以配置文件所在目录为基准。持久目录应放在本地可靠磁盘，独立于构建/可执行文件生命周期；不要使用网络共享文件系统。显式 `CsvOutputPath` 被 Collector 拒绝，原始 CSV 探测仍使用实验 demo。

CLI：`--config PATH`、可重复 `--instrument CODE`（整体覆盖配置 universe）、`--run-seconds N`、`--check-config`、`--help`。可在任意工作目录启动，但请明确传入配置路径。

## 采样和交易日

- callback 复制 SDK 行情到 `(TradingDay, InstrumentID)` 最新状态，记录本地 UTC epoch 微秒接收时间。主循环用单调时钟定期物化，再写 SQLite，SQLite 不进入 callback。
- 每窗口每合约保存最后收到的一次更新；相同内容的新 callback 也算更新；没有新 callback 不重复写。这是 sampled snapshot，不是逐笔成交，也不承诺保存所有 CTP 回调。
- 同日更新以本地接收顺序为准，不以源时间强制排序/去重。`sequence` 表示 run 内接收次序，允许间断。系统时钟校正可能导致 epoch 时间回退，不能仅据此推断丢包。
- 每条 snapshot 只写入其源 `TradingDay` 对应的 `YYYYMMDD.sqlite`。合法性校验包含年月日及闰年，**不拿本地自然日、登录日或 ActionDay 兜底**；非法/空日拒收并计数。登录日仅用于日志。
- 保留至多两个交易日 × universe 的内存状态；相邻两日乱序分开保存。更旧日拒收；第三日只有在最旧日没有待物化更新时才淘汰，否则显式失败。日界前后的尾部事实不会移入新日。
- snapshot 保留 SDK 46 个非 reserve 源字段，包括五档价格数量、成交量额、持仓、前结算/昨收盘、涨跌停、delta、均价和带价。`DBL_MAX`、`-DBL_MAX`、NaN/Inf 写 NULL；零和负值保持原值，空字符串仍为空字符串。不使用 reserve 字段作身份补全。

## 数据契约 v1

每个数据库有 `PRAGMA user_version=1`、应用标识及三张表。不兼容或交易日不符的数据库会拒绝写入，不做自动迁移。

| 表 | 内容 |
|---|---|
| `dataset` | 单行 `trading_day`、`schema_version`，数据库身份 |
| `runs` | `run_id`、`started_us`、`stopped_us`、`last_write_us`、采样间隔、配置 universe、SDK 来源 |
| `snapshots` | `id`、`run_id`、`sequence`、`received_us`、`snapshot_us`，及 SDK 原名的 46 个源字段 |

源字段定义见 [SDK 字段表](../experiments/ctp/docs/ctp-depth-market-data-fields.csv)，忽略其中 `reserve1`/`reserve2`。通过 `PRAGMA table_info(snapshots)` 查看完整列。浮点事实为 nullable REAL，数量为 INTEGER，源标识/时间为 TEXT。`TradingDay` 有 SQL CHECK 与文件身份一致。

`(run_id, sequence)` 唯一；同一物化批次重放不会重复插入。同日重启产生新 run 并追加，不跨 run 消除源事实重复。`id` 只在单个日文件内唯一。索引 `(InstrumentID, received_us, id)` 支持合约时间范围读取。

`runs.stopped_us IS NULL` 表示未记录正常结束，可能是进程仍运行、异常退出或强制终止；需结合当前进程/日志判断。每个有数据写入的交易日记录该 run，没有有效行情时不创建空日数据库，启动尝试通过日志追踪。

## 写入可靠性与停机

每数据目录持有非阻塞进程锁；第二个 Collector 非零退出。文件锁只约束遵循协议的 Collector，操作人仍须遵守 C++ 唯一 writer、下游只读的约定。

逐日事务、prepared statements、WAL、`synchronous=FULL`、1000ms busy timeout。提交成功后才增加 `written`。持久化出错记录 `persistence_failed` 并非零退出；跨日批次不承诺跨文件原子性，先前成功提交的日文件保持有效。

Ctrl+C/SIGTERM 和定时结束会先停止 SDK 回调并 Release，再提交尾部更新，标记正常停止。SIGKILL/崩溃可能丢失尚在内存或未提交的窗口，已提交事务通过 SQLite 恢复。磁盘很慢时多次 callback 会合并进后续 snapshot；不建设额外无界队列。SQLite 事务 durability 仍取决于操作系统与磁盘正确落实同步。

SDK 自动重连；重连后重新登录、重新订阅。初次连接/登录超时退出；首次登录后的断线保持进程运行，等待 SDK 恢复，登录失败有间隔地重试。本地订阅调用拒绝会重试；前置明确订阅失败或响应超时标记 `failed`，此 session 不盲目重试无效合约，配置修正后重启或下次连接重新订阅。CTP 不提供本程序所需的断线历史回补。

## 健康检查

stdout 建议重定向到持久日志文件。关键事件：`start`、`front_connected`、`front_disconnected`、`login_response`、`subscription_response`、`subscription_timeout`、`instrument_status`、`health`、`snapshot_commit`、`persistence_failed`、`stop`。

- 连接：`connected`/`logged_in`；`connections>1`、`disconnections` 标识当次 run 的恢复情况。
- 订阅：每个合约的 `subscription` 为 `not_sent/pending/subscribed/failed`，并记录 `error_id`。本地调用返回 0 不等于订阅确认。
- 接收：每合约 `session_received`、`last_received_us`、`age_seconds`，全局 `accepted` 与拒收计数。连接恢复会重置 session 的合约接收统计。
- 写入：`written`、`last_commit_us` 与 `snapshot_commit` 应在有有效新行情时增长。
- `receiving_within_30s` 仅表示最近 30 秒有接收，不内置交易时段日历；休市或不活跃合约可以已订阅但不推送。停止日志的连接状态是释放前最近一次 session 观测。

退出码 0 表示正常结束，**不等于已取得真实行情**；需要同时检查订阅确认、接收和写入证据。无行情、全部订阅失败或休市不会伪造 snapshot。

## 独立只读查询

SQLite CLI（可选）：

```bash
sqlite3 -readonly collector/data/20260907.sqlite \
  'SELECT TradingDay,InstrumentID,UpdateTime,LastPrice,received_us FROM snapshots ORDER BY id DESC LIMIT 5;'
```

后续 Python 标准库可以直接读，以下不是 Collector 启动步骤：

```python
from pathlib import Path
import sqlite3

path = Path("collector/data/20260907.sqlite").resolve()
with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1) as db:
    print(db.execute("SELECT trading_day, schema_version FROM dataset").fetchone())
    rows = db.execute(
        "SELECT InstrumentID, received_us, LastPrice, BidPrice1, AskPrice1, Volume, OpenInterest "
        "FROM snapshots WHERE InstrumentID=? ORDER BY received_us DESC, id DESC LIMIT 10",
        ("IF2609",),
    ).fetchall()
    print(rows)
```

实时查询使用短事务；长读事务会固定旧视图并阻止 WAL 完全 checkpoint。活跃数据库不要设置 `immutable=1`，不要只拷贝主 `.sqlite` 而遗漏 WAL。正常停机且所有读连接关闭后可复制每日文件；需要在线备份时使用 SQLite backup。只读 WAL 的使用条件参见 [SQLite 官方说明](https://www.sqlite.org/wal.html#read_only_databases)，URI 只读语义见 [SQLite URI](https://www.sqlite.org/uri.html)。

跨日查询由下游选择多个文件完成。Collector 不补现货指数、合约到期/行权信息或利率；后续基差、IV 等计算需要额外来源。
