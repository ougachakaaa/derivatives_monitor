<a id="data-provider-market-frame-contract"></a>

# Minute Market Frame / Latest Market Frame

Python 契约 v2；当前实现差距见[本级 Acceptance](../ACCEPTANCE.md)，系统收尾门槛见[根验收矩阵](../../docs/acceptance.md)。

## 架构位置

Collector 的 callback、15 秒聚合和封口行为见 [Collector Contract](../../collector/CONTRACT.md#event-time-与-bucket)；Raw identity、schema、只读和 WAL/锁协议见 [Raw Boundary](../../docs/contracts/raw-boundary.md)。Python `Store.connect` 在该共享边界内提供事务和执行预算。`Calendar` 提供版本化产品时段（含竞价）；这些机制不改写 Raw event time 或 TradingDay。

纯 Python `data_provider/market_frame.py` 复用 Store 和 Calendar，提供可导入的 scope/frame/latest 契约及 JSON CLI。Analytics 只依赖本模块输出，不理解文件路径、表名或 SQL；本模块不新增 HTTP、调度任务、常驻缓存或写路径。

## Scope 与完整性

一个 scope 只含一个 exchange/product，可为 instrument、product、month 或 option_chain。instrument 显式指定一个代码；其他 scope 必须传入带 trading_day、version、完整性声明的显式 Universe，按产品/月筛选并固定排序、去重。绝不默认读取 universe/current，也不从 Raw Bar 推断全部上市合约。

Universe 不完整时，即使已知代码都有 Bar，frame 也不能 COMPLETE。输出 expected、observed、usable、missing、stale、invalid、raw_partial 和 quote-continuity-partial 数量；无 observation 为 EMPTY；清单完整且全部成员有有效、不过期 observation 为 COMPLETE；其余为 PARTIAL。missing 成员仍占输出位置且 observation 为 null；空 scope 明确 EMPTY。完整链仅指显式清单，不合成缺失行权价。

## 时间、Bar identity 与选择

- 输入必须是带时区 datetime，统一解释到 Asia/Shanghai，微秒运算使用整数。每条 observation 的行情身份固定为 `(TradingDay, InstrumentID, bucket_start_us)`；`id` 只用于 revision/存储顺序，`run_id` 只用于 provenance。
- canonical 选择时钟是 `bucket_end_us` 和 `last_event_us`。point as-of 只允许 `bucket_end_us <= as_of_us` 的已结束 Bar，等号包含；不会选当前未结束 bucket。分钟标签必须整分钟，代表 `[minute,minute+1min)`，在 minute end 选择 `bucket_end_us <= minute_end_us` 的最近 Bar。
- 未封口分钟以 `min(evaluated_at, minute_end)` 为选择上限；`evaluated_at` 早于 minute start 拒绝。`sealed = evaluated_at >= minute_end` 只表示分钟时间结束，不声称当时数据库已经看见所有将在 grace 后提交的 Bar。
- 每个成员按 `bucket_end_us DESC,id DESC` 选一条。目标 bucket 没有行时，允许在同一个 Calendar period 内选择更早的真实 Bar并保留其三元 identity、event time 和 age；这是只读 as-of，不是 Raw forward-fill、插值或新报价。不得跨竞价/连续切换、午休、日夜 period 或 TradingDay 继承。
- `ActionDay` 跨午夜但 `TradingDay` 不变不会切断同一 Calendar period；Calendar 仍决定 period 边界。请求 day 必须匹配 period 的逻辑 TradingDay，休市/休息分钟和未知日历不可当作可重建交易分钟。
- 每次 frame 在一个只读事务开始时读取 `max(id)` 作为 `raw_revision`，所有查询限制 `id <= raw_revision`；可传回该上限重建相同 append-only 切片。相同 Raw、scope/Universe、Calendar、时间、策略和 revision 产生相同输出，不读取隐含 now。

## Observation timing、质量与 partial

- observation 保留 bucket start/end、bar OHLCV、callback counts、`last_event_us`、首末/close receive 时间、commit 时间、完整 bucket-close CTP state、partial reasons、`id` 和 `run_id`。接收/提交时间只作诊断，不参与 bucket、as-of、age 或跨合约同步选择。
- `quote_age_us = age_reference_us - last_event_us`；stale 当 age 严格大于显式 `stale_after_us`（默认 60 秒）。未来 event、identity/bucket 不一致、时间不在 bucket、commit 早于必要接收证据，或一级买卖价/量非有限、价格非正、挂量非正、买价大于卖价均为 invalid。最新 Bar invalid 时保留并报告，不退回较老的好看 Bar。
- `LastPrice` 或 Bar OHLC 可为空，不影响一级双边报价质量。Market Frame 不计算 mid，也不把 `bar_volume`/`bar_turnover` NULL 当作 Bid/Ask invalid。
- counter-only reasons 为 `volume_baseline_missing`、`turnover_baseline_missing`、`volume_counter_invalid`、`turnover_counter_invalid`、`volume_counter_reset`、`turnover_counter_reset`；它们增加 raw_partial 诊断，但不降低 Bid/Ask usability。
- quote-continuity reasons 为 `collector_start`、`trading_day_init`、`reconnect`、`invalid_event_time`、`event_time_regression`、`late_event`。它们不删除实际观察到的 close state，也不阻止下游保留计算值，但必须作为机器可读 quality/reason 传给 Analytics，使使用该 observation 的当前业务结果不可判为 current usable。
- `first_received_us`、`last_received_us`、`close_received_us`、`committed_us` 不得替代 `last_event_us` 计算 age；较晚 commit 不会把旧行情变新。

## Latest 与失败

Latest 必须传入 `at`。OPEN 使用当前 period 截至 at 已结束的 Bar；刚开盘没有已结束 observation 就 MISSING，不继承上一段。BREAK/CLOSED 只返回最近已经结束 period 的历史 frame，标记 `historical=true`、`effective_as_of` 为该 period end（exclusive），age reference 仍是请求 at。最新竞价也可作为历史 period，不误用 Calendar.latest_session 的仅连续时段定义。

Latest 分开报告 `calendar_trading_day` 和 frame 实际 TradingDay，调用方 Universe 必须匹配后者。UNKNOWN 不猜测时段，返回无 frame 的明确状态。缺文件抛 `DataNotFoundError`，不可读或非 schema v2 抛 `DataUnavailableError`；Query 分别映射为 404/503，不伪装 EMPTY，也不跨库搜索旧日。

## SQL、部署与下游边界

一帧一个 `Store.connect` 只读事务，使用 `market_bars(InstrumentID,bucket_end_us,id)` 索引做有界 top-1 查询；绑定全部参数。清单最多 10000 成员，沿用 3 秒 SQL 预算，超时明确失败。不建立 Derived SQLite，不写缓存、Raw 或 sidecar，不改变 Collector、日历或部署挂载。

下游 IV Chain → Skew 获得有序 scope、canonical Bar observation、session、revision、quality、completeness 与 partial reasons。MO Skew v1 按[下游契约](../../analytics/contracts/analytics-skew.md)选择 age、同步和报价；其他派生业务不得默认沿用为通用口径。本模块不实现 IV、Skew、Basis、定价或 Analytics。

## 验证语义

目标回归必须使用临时 schema v2 SQLite/WAL、固定时钟及受控 writer，覆盖四个 bucket 边界、分钟封口、同 period as-of、缺 bucket、平局、partial reason 分类、跨 session、ActionDay 午夜、迟到/revision、只读和错误。测试输入必须标记 TEST DOUBLE；其他 schema 的 fixture 不能证明本契约。

审核 Skew 读取上下文可显式注入已加载 Calendar；一旦提供即固定该对象。该注入只固定参考 identity，不改变 Bar as-of、session、age 或 revision 规则。
