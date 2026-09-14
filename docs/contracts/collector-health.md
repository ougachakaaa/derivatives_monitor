<a id="collector-health-semantic-authority"></a>

# Collector Health Semantic Authority

本文是 Collector Runtime Facts 与派生 Health 的唯一业务语义来源，回答“Collector 当前是否处于能够可靠采集行情的状态”。Collector 发布事实；Query 组合只读事实与 Calendar，由 Health evaluator 解释并返回 `health + reasons[]`。这不增加独立进程，也不将 Calendar 引入 C++ runtime。

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

`current_status` 回答现在的运行事实；后续 `runtime_snapshots` 回答过去每个 15 秒窗口的运行事实。两者共享事实语义但职责不同。

当前 Health 基于 `current_status + market calendar`；历史采集完整性须另行定义 `runtime_snapshots + market calendar` 的解释规则。本契约不新增历史快照存储，不以当前 healthy 追认过去完整。
