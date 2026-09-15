<a id="collector-health-semantic-authority"></a>

# Collector Health Semantic Authority

本文是 Collector Runtime Facts、Runtime History 与派生 Health 的唯一业务语义来源，定义当前及历史运行事实能够证明什么。Collector 发布事实；Query 组合只读事实与 Calendar，由 Health evaluator 解释并返回 `health + reasons[]`。Health evaluator 不增加独立进程，也不将 Calendar 引入 C++ runtime；外部恢复职责见 [Deployment](deployment.md#runtime-自动恢复)。

本文冻结语义，不声明实现已完成。传输格式由 [Raw Boundary](raw-boundary.md#collector-运行诊断协议)拥有，HTTP 由 [Read Path](read-path.md#健康证据)拥有，日历由 [Market Session](market-session.md)拥有；实现及未冻结项见 [Acceptance](../acceptance.md#collector-health-缺口)。

## 事实与解释

```text
Collector Runtime Facts + Market Calendar + evaluator 当前时间
                         ↓
                  Health Evaluation
                         ↓
                  health + reasons[]
```

`healthy / degraded / down` 是动态解释，不得作为 Collector 的权威运行事实保存。进程存活、CTP session、订阅覆盖、行情活动与持久化是不同证据，不能相互替代；Health 也不证明历史采集完整或指标可计算。

## Current Status

`current_status` 是 Collector 维护的当前运行事实；其 SQLite 载体由 [Raw Boundary](raw-boundary.md#运行库与发布)定义。至少包含：

| 逻辑字段 | 事实语义 |
|---|---|
| `run_id` | 当前 Collector 运行实例身份；同一 run 可经历多次 disconnect/reconnect |
| `heartbeat_us` | Collector 主循环最近一次签到的时间 |
| `connected` | 当前 CTP Front connection 是否已建立 |
| `logged_in` | 当前 connection 是否已成功完成 CTP login |
| `target_count` | Collector 当前期望订阅集合的合约数量 |
| `subscribed_count` | 当前 connection 已确认订阅成功的合约数量 |
| `total_ticks_today` | 当前 run 内当前源交易日合法接收的行情 callback 累计数量 |
| `last_tick_received_us` | 最近一条合法行情 callback 的接收时间 |
| `last_market_commit_us` | 最近一次 Market Bar 成功持久化的时间 |

时间字段表达本地 UTC epoch 微秒；接收时间与成功提交时间不得用 event time、最新 Bar 的 bucket 时间代替。合法接收要求已登录、目标合约及合法 TradingDay/event time；late callback 仍是合法接收证据，但不进入已封口 Bar，聚合拒收边界见 [Collector Contract](../../collector/CONTRACT.md#event-time-与-bucket)。累计 callback 数不是逐笔成交数。当前交易日取本 run 已合法接收的最大源 TradingDay，按源日期分组计数，旧日期交错不使当前日倒退；重启清零，以 run_id 明确范围。首次接收前交易日及接收时间未知，首次 Market commit 前提交时间未知。

## Collector Liveness

主循环固定周期更新 heartbeat，独立于 callback 与 Bar commit。检查者以自己的当前时间计算 `heartbeat_age = now - heartbeat_us`，在允许阈值内才有 `collector_alive = true`；过期则为 false。

Heartbeat 是本判定中 Collector 正常运行的唯一直接证据。`connected`、`logged_in`、最近 Tick、最近 commit 或数据库最后一根 Bar 都可能在进程死亡后保留，不能替代 heartbeat。

发布周期、存活窗口和不可读诊断的精确运行参数由 [Raw Boundary](raw-boundary.md#只读诊断与存活)拥有，不作为 Health 的长期业务常量。

## CTP Session 与订阅生命周期

不定义独立的 `session_alive`。`OnFrontConnected` 后 `connected=true, logged_in=false`，应用发起 login，成功后 `logged_in=true`。`OnFrontDisconnected` 后两者均为 false，当前 connection 的订阅确认失效，不能沿用旧成功数证明覆盖。

Collector 自己维护 target subscriptions；每次 connection login 成功后发送该集合。有效 connection 中已成功订阅的合约持续有效，运行期间可增加订阅。重连遵循 `connect → login → restore target subscriptions`。请求被受理不等于订阅成功；pending/failed instrument 是诊断明细，无需另建复杂 Health 状态机。

Collector alive 不等于 CTP connected。Collector 可以 24×7 常驻，不因午休、收盘或交易日结束主动停止，也不因下一次开盘主动重新 login。Login 由 connection 生命周期驱动，市场时段不控制进程或登录。

## Market Phase

Market Calendar 提供当前是否预期有实时行情的 `market_active`。它表达市场活动预期，Collector 不根据交易时间猜测自己的健康。

活动预期应沿用 [Calendar 的 `quote_expected`](market-session.md#calendar-session-契约)，不能直接将包含竞价的 OPEN 全部视为连续行情时段，也不要求每个不活跃合约固定推送。多市场 scope 如何归并为一个 `market_active` 尚须冻结；Calendar UNKNOWN 不得当作 false，套用休市 healthy 规则。

## Health 与判定顺序

总体状态仅有 `healthy / degraded / down`，具体异常通过 `reasons[]` 表达，不为异常组合增加 enum。固定诊断顺序为 heartbeat、connection、login、subscription、market feed、persistence。

| 条件 | Health | Reason / 解释 |
|---|---|---|
| `collector_alive == false` | `down` | `heartbeat_stale`；最高优先级，旧 session/订阅/行情事实不能证明正常 |
| alive 且 `market_active == false` | `healthy` | 无需 Tick 或 Bar 推进；休市 connection/login/订阅事实保留，不据此降级 |
| alive 且 active，`connected == false` | `degraded` | `session_disconnected` |
| alive 且 active，connected 且 `logged_in == false` | `degraded` | `session_not_logged_in` |
| alive 且 active，`subscribed_count < target_count` | `degraded` | `subscription_incomplete` |
| alive 且 active，合法 Tick 接收超过 feed freshness threshold 未推进 | `degraded` | `market_feed_stale` |
| alive 且 active，Tick 正常到达，但成功 Market Bar commit 超过允许周期未推进 | `degraded` | `market_persistence_stale` |
| alive 且 active，连接、登录、订阅数量相等、feed 与 persistence 均新鲜 | `healthy` | 无异常 reason |

非交易时段，旧 Tick、无新增 Bar 都不是故障证据；允许 CTP 前置维护、断线及自动重连。交易时段，只有 connected/logged_in 不能证明行情流动，只有 Tick 到达不能证明持久化成功。`total_ticks_today` 提供累计接收和增长趋势证据，不代替最近接收时间。

允许输出多个已成立的事实性 reasons，例如 `[subscription_incomplete, market_feed_stale]`，按上述顺序排列；不因上游断线机械推断所有下游故障。持久化陈旧的判据要求 Tick 正常到达。健康结果不得掩盖最高优先级 down。

Feed freshness 与 persistence freshness 是不同参数。后者须与 [15 秒 Bar 及 close grace](../../collector/CONTRACT.md#event-time-与-bucket)对齐，具体阈值及开盘/启动等待首个可提交 Bar 的宽限尚未冻结，不能擅自把建议参数变成业务常量。

## Current Status 与 Runtime History

Runtime DB 的逻辑组成如下；物理协议由 [Raw Boundary](raw-boundary.md#collector-运行诊断协议)拥有，本节不声明这些表已全部实现。

| 记录 | Authority 与范围 |
|---|---|
| `runs` | Collector Run 生命周期；每次进程启动的持久身份与启动事实 |
| `current_status` | 当前 Collector 整体运行事实，新 run 可替换旧状态 |
| `instrument_status` | 当前目标合约的订阅及接收/提交事实，不保存逐合约历史 |
| `runtime_snapshots` | 按 run 保存 Collector 整体的 append-only Runtime interval 观察 |

### Runs

每次 Collector Process 启动必须创建新的 `run_id` 并持久记录启动时间，即使未连接、未登录或没有产生 Market Bar，也须能够回答启动时间、历史启动次数和 Runtime History 所属实例。同一 run 可以跨交易日并经历多次 reconnect；进程 restart 必须产生新 run。

Run 启动事实必须先成功持久化，才能进入正式行情采集；创建失败的退出义务由 [发布协议](raw-boundary.md#运行库与发布)定义。正常 stop 或可捕获 failure 记录确认结束时间与 stopped/failed；未可靠记录结束时，两者均为 NULL。NULL 仅表示不知道如何结束，不得自动推导 crash。

启动事实不依赖正常 shutdown。Crash / SIGKILL 后没有结束记录不能使该 run 无效，也不能据此认定它仍在运行或推断精确退出时间。Market Bar 保留同一 `run_id` 作为 provenance，日库 `runs` 仅服务本库来源引用，不是完整 Collector 生命周期 authority。

### Runtime Snapshots

Runtime interval 使用本地 UTC epoch 微秒的 wall-clock / receive-time 时间域，为自然对齐的 `[interval_start_us, interval_end_us)`，宽度固定 `15_000_000µs`。它不按 TradingDay 分区，也不与 Market Bar 的 event-time bucket 建立一一对应关系。

只要主循环正常推进，每个完整被观察的 Runtime interval 都须封存该 run 的一条整体观察并尝试持久化，独立于连接、Tick 与 Bar 活动；CTP disconnected、ticks=0、bars=0 均不能抑制发布。快照 append-only，不保存 Tick 明细，不复制 Market Bar，不把故障后补出的空窗口冒充正常观察。

| 最低事实 | 语义 |
|---|---|
| `run_id` | 所属 Collector Run |
| `observed_us`, `process_state` | 主循环封存时间与 starting/running 生命周期状态 |
| interval 起止 | 本次运行观察所对应的自然 Runtime 窗口 |
| `connected`, `logged_in` | 观察时的 CTP session 状态 |
| target / subscribed / subscription_failed 数量 | 封存时的目标集合、当前 connection 确认成功数与失败数 |
| interval Tick 数量 | 按 receive time 归窗的合法接收数，沿用 Current Status 的合法性口径，包含 late callback |
| interval Market Bar 数量 | 按成功 Market commit 时间归窗的持久化行数，不按 Bar bucket 时间归窗 |
| interval partial Bar 数量 | 上述成功持久化行中 partial 的数量 |
| 最近 Tick receive 时间 | 本 run 最近合法接收时间；尚无接收时未知 |
| 最近 Market commit 时间 | 本 run 最近成功 Market 提交时间；尚无提交时未知，Runtime 写入不推进它 |

### 完整窗口、Restart 与时钟异常

只保存完整被观察的自然 15 秒窗口，不设计 partial Runtime Snapshot。10:00:07 启动时，首条可记录窗口是 10:00:15–10:00:30；10:00:37 结束时，不记录 10:00:30–10:00:45，也不为历史等待窗口结束。首尾边界由 runs 的启动/结束事实与相邻 snapshots 共同表达。

Snapshot 的 session、订阅及 process_state 只表示主循环封存时看到的状态，不证明整个窗口状态恒定。合法 Tick 按 received_us 归窗，成功持久化 Bar 按 committed_us 归窗；Runtime interval 与 Market event-time bucket 独立。完整窗口封存后的持久化重试不改变该观察，具体事务见 [发布协议](raw-boundary.md#运行库与发布)。

Restart 产生新 run_id，不继承旧计数、不继续旧未完成窗口、不补旧 Snapshot，从自己的第一个完整自然窗口开始。同一 interval_start_us 可属于不同 run，不能作为跨 run 的唯一身份。

Wall-clock 一次向前跨越多个 interval 时，不补中间窗口，丢弃当前无法证明完整观察的窗口，按新时间自然边界重新对齐，从下一个完整窗口恢复。Wall-clock 回退时，丢弃当前未完成窗口、重建自然边界，不修改已提交历史或产生本 run 已有 identity 的冲突。无法可靠证明完整观察的范围保持缺失，不补零、不复制上一状态。宿主时钟同步前提见 [Deployment](deployment.md#长期运行环境前提)。

### 历史解释边界

- Snapshot 存在且 ticks > 0：主循环留下观察，窗口内收到合法行情；存在且 ticks = 0：主循环留下观察，但窗口内没有合法行情接收。
- Snapshot 缺失：没有可靠 Runtime observation，即 UNKNOWN；不能单独证明进程未运行，也不能补成零 Tick 窗口。须结合 runs、相邻观察及 Market commit 判断故障的大致时间和层次，证据不足时保留未知。
- 基本运行事实须能由 Runtime DB 与 Market DB 区分：运行观察中断、restart、CTP disconnected、login 未完成、subscription 不完整、session 正常但无行情，以及 Tick 到达但 Market persistence 未推进。日志用于进一步定位，不成为这些基本事实的唯一来源。
- 单次观察的 session 状态不证明整个窗口状态未变，也不承诺捕获窗口内所有短暂断线；首次/末次不完整观察窗口不能冒充全窗覆盖。无 Market commit 的单个窗口本身不证明持久化故障，还须考虑合法 Tick、Bar 封口及允许提交周期。
- 当前 Health 仍基于 `current_status + market calendar`。运行历史不是市场历史完整性证明，不以当前 healthy 追认过去完整；完整 Calendar 历史解释和未冻结项见 [Acceptance](../acceptance.md#collector-health-缺口)。
