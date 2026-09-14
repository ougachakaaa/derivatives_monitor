<a id="raw-shared-boundary"></a>

# Raw Market Facts 共享边界

本契约只定义 Collector producer 与只读消费者共同遵守的 Raw 所有权、发布形状、锁、WAL 和运行诊断协议。Collector 如何接收、聚合和封口见 [Collector Contract](../../collector/CONTRACT.md)；Data Provider 读取见其 [Contract](../../data_provider/CONTRACT.md)，公共 HTTP 见 [Read Path](read-path.md)；挂载、目录生命周期和服务管理见 [Deployment](deployment.md)。当前实现差距只在 [Acceptance](../acceptance.md)登记。

## 所有权与已发布事实

- Collector 是 Raw 数据目录和日库的唯一 writer；Query、Dashboard、Analytics 及后续消费者不得写 Raw、修改 schema 或建立第二份行情事实。下游只能解释实际已提交的 Market Bar，不得把未保存的 callback、缺失 bucket 或推测值包装成 Raw。
- Raw schema v2 按合法 `TradingDay` 发布为一日一个 `YYYYMMDD.sqlite`。其他 schema 版本不提供迁移、双写、双读或兼容别名；打开非空非 v2 日库必须明确失败，任何组件都不得自动删除或覆盖现存文件。
- `dataset` 元数据唯一记录该日 `trading_day`、`schema_version=2`、`bar_interval_us=15000000` 和 `close_grace_us=1000000`；写入约束阻止混日、不同周期或不同 schema 混合。
- `runs` 保存 `run_id`、开始/停止/最后提交时间、订阅代码和来源。`run_id` 只回答哪次运行产生事实，不参与 Market Bar identity；固定 Bar 周期不是 run 配置。

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

本节拥有运行诊断存储与读取协议；事实和 Health 解释语义见 [Collector Health](collector-health.md)。运行库与行情日库分别版本化，不改变 Raw Market Bar schema。

### 运行库与发布

- 固定路径为 `DataDirectory/collector-runtime.sqlite`，`PRAGMA user_version=1`。Collector 是唯一 writer，必须先持有同目录 `.collector.lock`；运行库生命周期在该锁以内。运行库不参与按交易日枚举。
- 运行库使用 `journal_mode=DELETE`、`synchronous=FULL`、100ms busy timeout。只有下述两张表；producer 核对版本和建表定义，不自动修复坏库或迁移不兼容库。空库初始化及状态替换均为事务。
- 主循环约每 1 秒发布一份完整快照，启动、正常停止、异常退出另行发布。总体与全部目标合约行在同一事务替换，读者只能看到完整前一份或后一份；新 run 覆盖当前状态，不累计历史快照。
- `heartbeat_us` 是主循环本次签到时间，`updated_us` 与之相等；没有 Tick 也持续发布。不设置独立心跳线程，不以 SQLite 文件 mtime、Bar 时间或 CTP 回调心跳代替主循环签到。
- 打开或写入失败记录 `status_write_failed`，事务回滚，继续采集并在下个周期重试；不得单独更新磁盘 heartbeat。行情写入失败仍按 Collector 的致命错误语义处理。终止时尽力发布 stopped/failed；写失败只能保留上次成功记录。
- 不再生成或消费 `.collector-status.json`、`.collector-coverage.json`；遗留现场文件不删除、不回退读取。

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
- Data Provider 同一事务读取两张表并校验 schema、字段、行数、run/发布时间和计数一致性。损坏或不一致不得作为新鲜状态。Universe 工具只读取它需要的目标集合和快照身份，不解释 Health。
- 存活窗口为 `0 <= now_us - heartbeat_us <= 10_000_000`，且 process_state 为 starting/running；缺失、损坏、不可读、未来时间或超时都不能证明存活。容器 healthcheck 读取同一主循环事实，不检查行情活动。
- HTTP 的诊断形状与 unavailable 映射见 [Read Path](read-path.md#健康证据)。Health evaluator 尚未接入，进程状态不能充当 healthy/degraded/down。

## 失败与证据边界

缺失合法日库与日库不可读、schema 不兼容、identity 冲突、锁/WAL 条件不成立或查询超时必须区分；公共 HTTP 如何映射为 404/503 由 [Read Path Contract](read-path.md)定义。空目录、空数据、登录成功或模拟输入不能单独证明 Market Bar 闭环。工程和现场证据的归属见 [Acceptance](../acceptance.md)与 [Verification](../verification.md)。

技术依据：[SQLite WAL](https://www.sqlite.org/wal.html)、[同步级别](https://www.sqlite.org/pragma.html#pragma_synchronous)、[只读 URI](https://www.sqlite.org/uri.html)。
