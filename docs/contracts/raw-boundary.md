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

本节拥有诊断传输格式与当前运行参数；Runtime Facts 与 Health 判定的业务语义唯一见 [Collector Health](collector-health.md)。`current_status` 是逻辑事实视图，不等同于已发布的新 schema。下述 v2 字段不得未经映射和计数口径核对直接冒充该视图；当前差距见 [Acceptance](../acceptance.md#collector-health-缺口)。

- Collector 持有 Raw writer 锁期间，每 2 秒原子替换数据目录中的 `.collector-status.json`，诊断 `schema_version=2`。内容至少包括 `run_id`、`updated_us`、`process_state`、连接/登录状态、订阅汇总、`callbacks_accepted`、`bars_written`、`partial_bars`、`late_callbacks`、非法 TradingDay/event-time 计数以及最后 callback 接收/成功提交时间。
- `.collector-coverage.json` 同步使用诊断 schema v2，逐合约区分订阅状态、callback 计数、最近接收时间、Bar 写入/partial/late 计数；它是 coverage 证据，不是 Raw 行情表。
- 心跳由 Collector 主循环产生，独立于 callback 和 Bar commit。超过 10 秒、时钟明显倒退、内容损坏或缺失时，消费者不得判定进程存活；SIGKILL 后遗留文件也不能继续证明健康。
- 进程存活、CTP 已连接、订阅状态、callback 最近更新和 Bar 成功提交是不同证据。休市无 callback 不等于进程停止；状态输出失败由 Collector 记录但不停止采集，消费者故障也不进入采集控制路径。

## 失败与证据边界

缺失合法日库与日库不可读、schema 不兼容、identity 冲突、锁/WAL 条件不成立或查询超时必须区分；公共 HTTP 如何映射为 404/503 由 [Read Path Contract](read-path.md)定义。空目录、空数据、登录成功或模拟输入不能单独证明 Market Bar 闭环。工程和现场证据的归属见 [Acceptance](../acceptance.md)与 [Verification](../verification.md)。

技术依据：[SQLite WAL](https://www.sqlite.org/wal.html)、[同步级别](https://www.sqlite.org/pragma.html#pragma_synchronous)、[只读 URI](https://www.sqlite.org/uri.html)。
