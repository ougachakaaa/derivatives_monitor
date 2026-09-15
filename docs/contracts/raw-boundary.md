<a id="raw-shared-boundary"></a>

# Raw Market Facts 共享边界

本契约只定义 Collector producer 与只读消费者共同遵守的 Raw 所有权、发布形状、锁、WAL 和运行诊断协议。Collector 如何接收、聚合和封口见 [Collector Contract](../../collector/CONTRACT.md)；Data Provider 读取见其 [Contract](../../data_provider/CONTRACT.md)，公共 HTTP 见 [Read Path](read-path.md)；挂载、目录生命周期和服务管理见 [Deployment](deployment.md)。当前实现差距只在 [Acceptance](../acceptance.md)登记。

## 所有权与已发布事实

- Collector 是 Raw 数据目录和日库的唯一 writer；Query、Dashboard、Analytics 及后续消费者不得写 Raw、修改 schema 或建立第二份行情事实。下游只能解释实际已提交的 Market Bar，不得把未保存的 callback、缺失 bucket 或推测值包装成 Raw。
- Raw schema v2 按合法 `TradingDay` 发布为一日一个 `YYYYMMDD.sqlite`。其他 schema 版本不提供迁移、双写、双读或兼容别名；打开非空非 v2 日库必须明确失败，任何组件都不得自动删除或覆盖现存文件。
- `dataset` 元数据唯一记录该日 `trading_day`、`schema_version=2`、`bar_interval_us=15000000` 和 `close_grace_us=1000000`；写入约束阻止混日、不同周期或不同 schema 混合。
- 日库 `runs` 保存 `run_id`、开始/停止/最后提交时间、订阅代码和来源，作为本库 Market Bar 的 provenance 投影。它不覆盖无行情启动，也不拥有完整 Collector Run 生命周期；该 authority 归 [Runtime DB 的 runs](collector-health.md#runs)。`run_id` 不参与 Market Bar identity；固定 Bar 周期不是 run 配置。

### `market_bars` 逻辑 schema

| 字段 | 语义与约束 |
|---|---|
| `id` | 日库内严格递增、唯一的 append position；只用于 revision watermark 和稳定存储顺序，不是行情事实 identity |
| `run_id` | 产生本 Bar 的运行 provenance，外键指向 `runs` |
| `TradingDay`, `InstrumentID`, `bucket_start_us` | 唯一 canonical identity；共同构成主键/唯一约束 |
| `bucket_end_us` | 必须等于 `bucket_start_us + 15000000`；start/end 为按 Asia/Shanghai event time 构造的 UTC epoch 微秒，start 必须自然 15 秒对齐 |
| `bar_open`, `bar_high`, `bar_low`, `bar_close` | bucket 内有效 LastPrice 的 event-time OHLC；没有有效价时全部为 NULL |
| `bar_volume`, `bar_turnover` | 相对 bucket 前可靠累计 baseline 的独立差分；不可靠时对应字段为 NULL，有效且无增长时为零 |
| `callback_count`, `valid_last_price_count` | bucket 内合法 callback 数和参与 OHLC 的 LastPrice 数；前者必须大于零 |
| `first_event_us`, `last_event_us` | event-time 排序后首末 callback 时间，均位于 `[bucket_start_us,bucket_end_us)` |
| `first_received_us`, `last_received_us` | 本地实际最早/最晚接收时间，仅供接收诊断，不决定 bucket 或行情顺序 |
| `close_received_us` | 产生 bucket-close CTP state 的 callback 接收时间 |
| `committed_us` | SQLite 事务成功发布该 Bar 的时间，不得冒充 event time |
| `is_partial`, `partial_reasons` | `is_partial` 为 0/1；`partial_reasons` 是排序去重的 JSON 字符串数组，两者必须保持“非空即 partial”的一致约束 |
| CTP `DepthMarketData` 非 reserve 字段 | event-time 最后一条合法 callback 的完整 bucket-close 市场状态；无效浮点归一化为 NULL，原始累计 `Volume/Turnover` 与 `bar_*` 不混用 |

- 每个 canonical identity 最多发布一次。写入必须使用普通 INSERT；唯一约束冲突是 invariant violation，writer 必须回滚并失败，禁止 `ON CONFLICT` ignore/update、upsert、correction 或重开历史 bucket。
- `id` 在成功事务内分配，消费者以事务开始时的 `max(id)` 作为该日 `raw_revision`，并用 `id <= raw_revision` 重建同一 append-only 切片。identity 相等判断只能使用三元组，不得使用 `id` 或 `run_id`。
- 同日重启可以追加新的、尚不存在的 canonical Bar。只有成功 commit 的行和 durable `bars_written` 才是已发布事实；内存 bucket、日志和诊断 JSON 不是行情 Source of Truth。
- 数据目录、flow 和配置有独立的挂载与保留规则，见 [Deployment Contract](deployment.md#数据与隔离)；移除服务、镜像、构建或项目文件不能作为删除 Raw 的手段。

<a id="sqlite-v2-物理契约"></a>

### SQLite v2 物理契约

- 文件头必须为 `PRAGMA application_id=1145914161`、`PRAGMA user_version=2`。日库只含 v2 事实；`snapshots` 不是 v2 的表、视图或兼容别名。
- `dataset` 的固定列为 `singleton INTEGER PRIMARY KEY`、`trading_day TEXT NOT NULL`、`schema_version INTEGER NOT NULL`、`bar_interval_us INTEGER NOT NULL`、`close_grace_us INTEGER NOT NULL`。唯一行固定 `singleton=1`，并由 CHECK 冻结 schema、周期和 grace。
- `runs` 的固定列为 `run_id TEXT PRIMARY KEY`、`started_us INTEGER NOT NULL`、`stopped_us INTEGER`、`last_commit_us INTEGER`、`instruments TEXT NOT NULL`、`source TEXT NOT NULL`。
- `market_bars` 的 Bar 固定列为 `id, run_id, TradingDay, InstrumentID, bucket_start_us, bucket_end_us, bar_open, bar_high, bar_low, bar_close, bar_volume, bar_turnover, callback_count, valid_last_price_count, first_event_us, last_event_us, first_received_us, last_received_us, close_received_us, committed_us, is_partial, partial_reasons`，随后保存下面的 CTP close-state 列；同名 `TradingDay` / `InstrumentID` 不重复建列。
- SQLite affinity 固定为：identity、所有 `*_us`、计数、`is_partial`、`bar_volume` 和 CTP 整数字段使用 `INTEGER`；`bar_open, bar_high, bar_low, bar_close, bar_turnover` 及 CTP 浮点字段使用 `REAL`；run、原因和 CTP 字符数组使用 `TEXT`。NULL 只用于契约明确允许未知的聚合数值及归一化后的 CTP 浮点值。
- CTP 字符列固定为 `TradingDay, ExchangeID, InstrumentID, ExchangeInstID, ActionDay, UpdateTime`；整数列固定为 `UpdateMillisec, Volume, BidVolume1, AskVolume1, BidVolume2, AskVolume2, BidVolume3, AskVolume3, BidVolume4, AskVolume4, BidVolume5, AskVolume5`；浮点列固定为 `LastPrice, PreSettlementPrice, PreClosePrice, PreOpenInterest, OpenPrice, HighestPrice, LowestPrice, Turnover, OpenInterest, ClosePrice, SettlementPrice, UpperLimitPrice, LowerLimitPrice, PreDelta, CurrDelta, BidPrice1, AskPrice1, BidPrice2, AskPrice2, BidPrice3, AskPrice3, BidPrice4, AskPrice4, BidPrice5, AskPrice5, AveragePrice, BandingUpperPrice, BandingLowerPrice`。升级 SDK 若改变该字段集合，必须先发布新 Raw schema 版本，不能静默改变 v2。
- 数据库 CHECK 必须执行日身份、15 秒 bucket 宽度与对齐、event time 范围、callback/有效价格计数、OHLC 全空或全有、partial flag/reasons 一致性；外键执行 `market_bars.run_id → runs.run_id`，唯一约束执行 canonical identity。writer 打开已有 v2 时还要核对 dataset 固定值；表缺失或形状不兼容在准备普通 INSERT 时明确失败。

## Writer 协调与持久性

- 每个 Raw 数据目录使用进程锁排除第二个 Collector writer。SQLite 使用单连接单 writer、WAL、`synchronous=FULL`、有界 busy timeout 和逐日事务；不承诺跨 TradingDay 原子提交。
- 一个提交批次可以包含多个已经封口的 Bar，但必须按 canonical identity 确定性排序。任何 schema、identity 或写入错误回滚该日当前事务并使 Collector 非零退出，不能继续报告健康。
- 正常停止只提交符合 [Collector 封口规则](../../collector/CONTRACT.md#生命周期与失败语义)的标准 Bar；强制终止窗口内尚未 commit 的 Bar 不属于已发布事实。

## 只读消费与 WAL

- 消费者以 SQLite URI `mode=ro`、`query_only=ON` 和短事务读取同一 Raw，不创建、迁移或修改数据库及 sidecar，也不为旧 schema 提供隐式适配。
- 活跃日库从只读挂载读取现存 WAL/SHM；不得只复制 `.sqlite` 主文件，也不得使用 `immutable=1`。离线且没有非空 WAL 时，只能在取得 Collector 共享目录锁后使用 immutable，并在连接关闭前持锁；不得根据文件年龄猜测安全性。
- 历史文件在 Collector 正常关闭且没有读事务占用时可以独立复制；其他情况使用 SQLite backup。Collector 正在采集另一天而旧日缺少 sidecar 时，消费者必须明确报告可重试的不可读状态，提示正常停机后查询；不得绕过锁或修改持久目录。

## Collector 运行诊断协议

本节拥有 Runtime DB 的唯一当前物理协议；事实和 Health 解释语义见 [Collector Health](collector-health.md)。本协议不改变 Raw Market Bar schema，不声明实现已完成；当前差距见 [Acceptance](../acceptance.md#collector-第一阶段可靠性缺口)。

### 运行库与发布

- 固定路径为 `DataDirectory/collector-runtime.sqlite`。Collector 是唯一 writer，必须先持有同目录 `.collector.lock`；运行库生命周期在该锁以内，不参与按交易日枚举。
- 运行库使用 `journal_mode=DELETE`、`synchronous=FULL`、100ms busy timeout。仅包含 `runs`、`current_status`、`instrument_status`、`runtime_snapshots` 四张事实表；不保存 Tick 明细、Market Bar 副本或派生 Health。
- 当前 schema 是唯一有效 schema，不定义 Runtime 历史版本号、迁移、双读、双写或兼容层。producer 和只读消费者须校验当前表集合、字段及约束，不能仅凭旧 `user_version` 接受数据库。已有库不符合当前 schema 时明确失败，Collector 不自动迁移、修复或删除；空库初始化为事务。开发期旧库的显式重建边界见 [Deployment](deployment.md#数据与隔离)。
- 新 Process Run 必须先成功 INSERT `runs`，再进入正式行情采集；创建失败记录错误并非零退出。任何正式 Market Bar 的 run_id 必须已存在于 Runtime runs 中。
- 主循环约每 1 秒发布 Current Runtime Facts；同一 SQLite transaction 替换 `current_status` 和全部目标 `instrument_status`，并追加已经封存、尚未持久化的 `runtime_snapshots`。全部 commit 或全部 rollback，读者只能看到完整前一份或后一份。
- `heartbeat_us` 是主循环本次签到时间，`updated_us` 与之相等；没有 Tick 也持续发布。不设置独立心跳线程，不以文件 mtime、Bar 时间或 CTP callback 代替主循环签到。
- 运行期间 publication 打开或写入失败记录 `status_write_failed`，事务回滚，保留 immutable pending snapshots，继续 Market collection，在下一 publication 重试；不得单独推进磁盘 heartbeat。完整窗口在主循环封存后即成为不可变 pending fact，重试不得重算其状态、计数或 observed_us。进程在持久化前崩溃会使这些窗口永久缺失，restart 不补造。
- 正常 stop 或可捕获 failure 最后尝试一次 Runtime transaction：追加完整 pending snapshots、替换当前两表为终止事实，并更新本 run 的 ended_us / terminal_state。current_status 为 stopped/failed，SDK 释放后的 session/订阅按下文清除。事务失败记录日志、保留最后成功事实，终止字段可保持 NULL；不等待当前未完成 Runtime 窗口结束。
- Runtime 与 Market 日库独立提交，不建立跨文件事务或外键。Market commit 成功而对应 Runtime History 缺失是合法状态，不撤销、删除或修改 Market Bar，也不补造 Runtime Snapshot。日库 runs 继续仅为本库 provenance 投影。
- 不再生成或消费 `.collector-status.json`、`.collector-coverage.json`；遗留现场文件不删除、不回退读取。

### Runs schema

| 字段 | 类型与约束 |
|---|---|
| `run_id` | TEXT PRIMARY KEY NOT NULL；32 位小写十六进制，与 Market Bar provenance 相同 |
| `started_us` | INTEGER NOT NULL；Process Run 启动时间，UTC epoch 微秒 |
| `ended_us` | INTEGER，可空；确认终止的 UTC epoch 微秒 |
| `terminal_state` | TEXT，可空；仅 stopped / failed |
| `instruments` | TEXT NOT NULL；本 Run 启动时精确 target instrument 集合，编码为去重的 JSON 字符串数组 |
| `source` | TEXT NOT NULL；行情来源 |

数据库约束执行 `(ended_us IS NULL) ⇔ (terminal_state IS NULL)`，非空 ended_us 必须不早于 started_us。每次启动追加新 run，已记录的启动事实不被新 run 覆盖；仅为确认终止写入结束字段，不事后猜测 crash 的时间或原因。NULL 的解释见 [Runs](collector-health.md#runs)。

### Runtime Snapshots schema

除明确可空字段外均 NOT NULL；identity 为复合主键 `(run_id, interval_start_us)`，run_id 外键指向本库 runs。

| 字段 | 类型与约束 |
|---|---|
| `run_id` | TEXT；所属 Process Run |
| `interval_start_us`, `interval_end_us` | INTEGER；UTC epoch 微秒，start 自然对齐 15_000_000，end = start + 15_000_000 |
| `observed_us` | INTEGER；主循环封存窗口的 UTC epoch 微秒，重试时不改变 |
| `process_state` | TEXT；starting / running，含义沿用 Current Status |
| `connected`, `logged_in` | INTEGER；0/1，logged_in <= connected |
| `target_count`, `subscribed_count`, `subscription_failed` | INTEGER；非负，后两者分别不超过 target_count |
| `tick_count` | INTEGER；非负，receive time 落在窗口内的合法 Tick 数，包含 late callback |
| `market_bar_count`, `partial_bar_count` | INTEGER；成功 Market commit time 落在窗口内的持久化行数及其中 partial 数，0 <= partial_bar_count <= market_bar_count |
| `last_tick_received_us`, `last_market_commit_us` | INTEGER，可空；截至封存时本 run 最近合法接收／成功 Market commit 时间，尚无事实时为 NULL |

上述主键、外键、枚举、布尔、计数及窗口宽度/对齐约束由数据库执行。Snapshot 仅普通 INSERT，禁止 UPDATE、upsert、correction 或 restart 回填；可为 interval_start_us 建立读取索引，不增加第二套历史表。时钟回退后的 identity 去重须同时覆盖已提交和 pending 事实，不靠覆写或冲突更新处理。

计数直接按事实发生时间归窗，不从累计数或 Market event-time bucket 反推；Market transaction 失败不计数，成功后才按 committed rows 增加 Bar 与 partial 数。Runtime 写入不推进 last_market_commit_us。封存状态、完整窗口、时钟异常及缺失解释由 [Runtime Snapshots](collector-health.md#runtime-snapshots)定义。

### Runtime 历史保留

运行库不按 TradingDay 拆分；runs 持续追加启动记录，runtime_snapshots 持续追加历史观察，current_status / instrument_status 只保留当前事实。第一阶段不做自动删除、rolling retention、compaction、archive 或分片；后续容量治理必须先修改本 authority。

### Current Status schema

`current_status` 固定一行，`singleton INTEGER PRIMARY KEY CHECK(singleton=1)`。除以下明确可空的字段外全部 NOT NULL；计数与时间为 INTEGER，字符串为 TEXT。

| 字段 | 类型与口径 |
|---|---|
| `run_id` | 32 位小写十六进制，与该 Collector 的行情 run provenance 相同 |
| `heartbeat_us`, `updated_us` | 正 UTC epoch 微秒；同一次主循环发布的时刻 |
| `process_state` | `starting / running / stopped / failed`；running 表示本 run 曾成功登录且尚未退出，断线不把它变成 Health |
| `connected`, `logged_in` | 0/1；未连接不能 logged_in，释放 SDK 后两者为 0 |
| `target_count`, `subscribed_count`, `subscription_failed` | 当前目标数、当前 connection 确认成功数、失败数；未登录或 SDK 释放后确认失效 |
| `trading_day` | 可空；本 run 合法接收中最大的源 TradingDay（YYYYMMDD） |
| `total_ticks_today`, `ticks_received` | 当前 run 内上述交易日累计、当前 run 全部交易日合法接收累计；包含 late，不等于逐笔成交数 |
| `last_tick_received_us`, `last_market_commit_us` | 可空；本 run 最近合法 callback 接收、最近成功行情 commit 时间；运行库 commit 不推进后者 |
| `connections`, `disconnections` | 本 run Front connection 建立与断开次数 |
| `callbacks_accepted`, `bars_written`, `partial_bars`, `late_callbacks` | 本 run 聚合接受数、成功持久化 Bar 数、其中 partial 数、late 拒收聚合数 |
| `invalid_trading_day`, `invalid_event_time`, `unknown_instrument`, `event_time_regressions` | 本 run 对应接入/聚合诊断计数 |

第一条合法接收前 trading_day 与最后接收为 NULL，当日和运行接收数为 0；首次成功 Market commit 前最后提交为 NULL。计数非负，`ticks_received = callbacks_accepted + late_callbacks`，`partial_bars <= bars_written`。交易日计数按源日期分组，展示最大日期；旧日期交错不令当前日倒退。重启清零，不从旧 run 或 Bar 重建 callback 数。

### Instrument Status schema

`instrument_status` 以 `instrument_id TEXT PRIMARY KEY` 保存精确目标合约，每个目标一行。`run_id TEXT`、`updated_us INTEGER` 必须与 current_status 一致。`subscription TEXT` 为 `not_sent / pending / subscribed / failed`，`error_id INTEGER` 保存响应/超时错误；SDK 释放后状态清为 not_sent、错误清零。

其余字段为 `ticks_received`、`last_tick_received_us`（可空）、`callbacks_accepted`、`bars_written`、`partial_bars`、`late_callbacks`、`invalid_event_time`。口径与总体相同、范围限于该合约；接收和 Bar 计数跨 reconnect 保留。除明确可空字段外全部 NOT NULL。逐合约计数之和须等于对应总体计数；订阅成功/失败行数须与总体汇总相等。

### 只读诊断与存活

- 消费者用 `mode=ro` / SQLite READONLY 和短事务读取；不得创建或修改运行库、journal 或 sidecar，不使用 immutable，不根据旧 JSON 兜底。库缺失与损坏/不兼容/暂不可读分别交接；拒绝符号链接库及 sidecar。
- Data Provider 校验完整运行库 schema，并在同一事务读取当前两张表，校验字段、行数、run/发布时间和计数一致性。损坏或不一致不得作为新鲜状态。Universe 工具只读取它需要的目标集合和快照身份，不解释 Health。
- 存活窗口为 `0 <= now_us - heartbeat_us <= 10_000_000`，且 process_state 为 starting/running；缺失、损坏、不可读、未来时间或超时都不能证明存活。容器 healthcheck 读取同一主循环事实，不检查行情活动。
- HTTP 的诊断形状与 unavailable 映射见 [Read Path](read-path.md#健康证据)。Health evaluator 尚未接入，进程状态不能充当 healthy/degraded/down。

## 失败与证据边界

缺失合法日库与日库不可读、schema 不兼容、identity 冲突、锁/WAL 条件不成立或查询超时必须区分；公共 HTTP 如何映射为 404/503 由 [Read Path Contract](read-path.md)定义。空目录、空数据、登录成功或模拟输入不能单独证明 Market Bar 闭环。工程和现场证据的归属见 [Acceptance](../acceptance.md)与 [Verification](../verification.md)。

技术依据：[SQLite WAL](https://www.sqlite.org/wal.html)、[同步级别](https://www.sqlite.org/pragma.html#pragma_synchronous)、[只读 URI](https://www.sqlite.org/uri.html)。
