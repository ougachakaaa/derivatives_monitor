<a id="collector-runtime-contract"></a>

# Collector 长期契约

本契约适用于 MVP 及后续下游扩展。整体定位见[系统架构](../ARCHITECTURE.md)，内部组件关系见[Collector Architecture](ARCHITECTURE.md)，共享 Raw 协议见 [Raw Boundary](../docs/contracts/raw-boundary.md)，可执行用法见[Collector 手册](README.md)。当前实现与本契约的差距只在[根 Acceptance](../docs/acceptance.md)登记。

## 边界与职责

- 唯一闭环为 `CTP DepthMarketData → AlignedBarAggregator → MarketBar → 每 TradingDay SQLite`。Python、Browser、HTTP、策略、交易、现货指数、IV/基差计算均不进入采集链路。
- Collector 是 Raw 唯一 writer。它只保存实际收到的 callback 形成的 canonical 15 秒 Bar，不承诺逐 callback 历史、逐笔成交 OHLC、断线补采或历史修正。
- C++ runtime 使用 C++17/Linux MdApi，自有 INI、固定字段校验、日志、SDK 构建规则与最小第三方 SDK；不引入服务框架、消息队列或 Python runtime。
- C++ 接受配置接口提供的精确合约代码，不做合约发现；公开清单的生成和发布由独立的 [Universe Tool Contract](scripts/CONTRACT.md)定义。

## 行情接入与配置接口

正式 Collector 仅使用 MdApi；交易接口能力边界见 [MVP](../docs/mvp.md#行情接入能力边界)。`UserID` 和 `Password` 可缺省或为空，已有值继续走 MdApi 登录且遵守 SDK 字段限制；本地接受空值不证明任意前置允许匿名接入，实际结果由 MdApi 响应表达。

- `FrontMdAddr` 必填；`BrokerID` 与 `UserProductInfo` 按接入方要求填写。
- 订阅代码由 `Instruments`、可选 `InstrumentsFile` 或重复的 `--instrument CODE` 提供；命令行覆盖文件，文件覆盖 `Instruments`。结果必须非空、精确、去重。
- `DataDirectory` 默认 `data`；`FlowPath` 默认 `flow` 且每个运行实例使用独立目录。相对路径以配置文件目录为基准。
- Bar 周期固定为 15 秒且不可配置；未列出的配置键必须拒绝。`StatusIntervalSeconds` 默认 `10`，`ConnectTimeoutSeconds` 默认 `20`，`RetryIntervalSeconds` 默认 `5`，`SubscriptionBatchSize` 默认 `100`。`RunSeconds` 默认 `0`，表示持续运行。
- CLI 为 `--config PATH`、可重复的 `--instrument CODE`、`--run-seconds N`、`--check-config` 和 `--help`。

## Event time 与 bucket

- callback 到达时立即复制 SDK 结构、记录本地 UTC epoch 微秒接收时间和进程内递增接收序号；不持有厂商指针，不在 callback 中做 SQLite I/O 或 sleep。
- event time 只由 `ActionDay + UpdateTime + UpdateMillisec` 按 Asia/Shanghai 解释并转换为 epoch 微秒。`ActionDay` 必须是真实日历日期，`UpdateTime` 必须为 `HH:MM:SS`，`UpdateMillisec` 必须为 `0..999`。`received_us`、登录日和 `TradingDay` 均不得替代 event time。
- 每分钟只有 `[00,15)`、`[15,30)`、`[30,45)`、`[45,60)` 四个 bucket；范围为 `[bucket_start_us,bucket_end_us)`，宽度固定 `15_000_000µs`，边界不受进程启动时间影响。
- 分区和状态 identity 使用 callback 中合法的 `TradingDay`；不得以本地日期、`ActionDay` 或登录日替代。非法/空 TradingDay、未知合约或非法 event time 的 callback 拒收并计数。可识别合约的非法 event time 同时令该合约 continuity 失效。
- 同一 `(TradingDay, InstrumentID)` 按 event time 排序，同一毫秒以接收序号排序。event time 小于此前已接受时间即为 regression；尚未封口的受影响 bucket 仍按上述顺序聚合并标记 partial。
- 本地墙钟到达 `bucket_end_us + 1_000_000µs` 时 bucket 封口。grace 内可接收属于该 bucket 的 callback；封口后不可重新打开。指向已封口 bucket 的 callback 是 late event：拒绝聚合、累计诊断、保持历史不变并令该合约 continuity/baseline 失效。

## Market Bar 聚合

- 每个存在至少一条合法 callback 的 `(TradingDay, InstrumentID,bucket_start_us)` 最多生成一条 Bar。没有 callback 的 bucket 不生成行，不造 synthetic OHLC，不 forward-fill，不把缺失观察表示成零成交。
- `callback_count` 统计 bucket 内全部合法 callback；`valid_last_price_count` 只统计 `LastPrice` 有限、不是 CTP 极大哨兵且严格大于零的 callback。
- `bar_open/high/low/close` 分别取有效 LastPrice 按 event-time 顺序的第一条、最大值、最小值和最后一条。没有有效 LastPrice 时四者均为 NULL，但仍保存状态 Bar；这本身不构成 partial。
- bucket-close market state 取 event-time 顺序最后一条合法 `DepthMarketData`，并保存全部非 padding/reserve 字段。CTP 原 `OpenPrice/HighestPrice/LowestPrice/ClosePrice/Volume/Turnover` 是该 close callback 的原始市场状态，不得冒充 `bar_*` 聚合值。
- 所有 CTP 非有限或极大哨兵浮点值归一化为 NULL，源字符串保持原值；不由合约代码猜测交易所、品种或合约元数据。
- Bar 保存首末 event time、首末 received time、close-state 对应 received time、commit time、callback 数量、partial 状态和 run provenance。精确发布形状由 [Raw Boundary](../docs/contracts/raw-boundary.md#所有权与已发布事实)拥有。

## 累计量、continuity 与 partial

- CTP `Volume` 与 `Turnover` 是累计状态。`bar_volume`、`bar_turnover` 分别等于 bucket-close cumulative 减去 bucket 开始前该字段最近可靠的 cumulative baseline；禁止用 bucket last 减 bucket first。
- 两个 baseline 按 `(TradingDay, InstrumentID)` 独立维护，跨正常 bucket、没有 callback 的 bucket 及仅 `ActionDay` 跨午夜保留；`TradingDay` 改变时必须重置。累计值有效且没有增加时，delta 明确为零。
- 任一字段 baseline 缺失、close cumulative 无效或按 event-time 顺序发生回退时，仅对应 `bar_volume` 或 `bar_turnover` 为 NULL；另一字段可独立计算。任一此类情况都令 Bar partial。
- 合法的 bucket-close cumulative 可在异常 Bar 结束后为对应字段重新建立 baseline；close cumulative 仍无效时保持 baseline 未知。continuity 重建且完整观察下一标准 bucket 后，后续 Bar 可恢复非 partial，partial 不无限传播。
- `partial_reasons` 是排序、去重的稳定 JSON 字符串数组，`is_partial` 当且仅当数组非空。稳定 reason 为：`collector_start`、`trading_day_init`、`reconnect`、`invalid_event_time`、`event_time_regression`、`late_event`、`volume_baseline_missing`、`turnover_baseline_missing`、`volume_counter_invalid`、`turnover_counter_invalid`、`volume_counter_reset`、`turnover_counter_reset`。
- Collector 启动后首次触及的 bucket、首次出现的 TradingDay、断线/重连覆盖的 bucket，以及 event-time 异常实际影响的 bucket 使用对应 continuity reason。异常发生在已封口区间而不能修改历史时，reason 施加到下一根有 callback 的 Bar；该 Bar 的合法 close state 用于重建后续 continuity。

<a id="collector-lifecycle-contract"></a>

## 生命周期与失败语义

- Connection/login/订阅事实的生命周期及常驻运行约束由 [Collector Health](../docs/contracts/collector-health.md#ctp-session-与订阅生命周期)统一定义；Collector 发布事实，不保存派生 Health 为权威事实。
- SDK 断线后由应用在每次连接后登录并重新订阅。请求返回 0 只表示本地受理；订阅响应单独跟踪，区分 pending、成功、失败和已订阅但无行情。
- 主线程负责有间隔的登录重试、订阅批次、请求超时检测、自然 bucket 封口和事务提交；首次连接/登录超时不退出，等待 SDK 重连并持续签到；callback 不阻塞在这些工作上。断线立即破坏 observation continuity，但不修改已提交 Bar。
- Raw writer 锁、SQLite 持久性和逐日事务边界统一见 [Raw Boundary](../docs/contracts/raw-boundary.md#writer-协调与持久性)。写入失败必须明确日志并非零退出；成功 commit 后才累计 durable Bar 数。
- SIGINT/SIGTERM 先停止并释放 SDK，SPI 在 callback 收尾期间保持有效。对于已经到达 bucket end、但仍处于 1 秒 grace 的 bucket，正常停止最多等待剩余 grace 后提交；不得等待当前未结束 bucket 到期，也不得把它作为半根 Bar 写入。强制终止可能丢失所有尚未 commit 的内存 Bar。
- canonical identity 冲突、schema 不兼容或持久化失败均为 invariant/persistence failure；不得 upsert、忽略冲突、修正历史或继续报告健康。

## 运行诊断与验收约束

- 日志和诊断使用 callback/bar 词汇，至少包含 run ID、连接/登录/断线/重连、逐合约订阅、`callbacks_accepted`、`bars_written`、`partial_bars`、`late_callbacks`、非法 day/event-time、最近接收/成功提交时间及持久化错误；不得输出凭据。
- 独立运行库的共享字段和 freshness 见 [Raw Boundary](../docs/contracts/raw-boundary.md#collector-运行诊断协议)。连接、订阅、callback、Bar commit 和市场时段是不同证据。
- 核心聚合、四个自然边界、ActionDay 午夜、TradingDay 切换、baseline、partial 恢复、event regression/late event、事务冲突、停止和 SDK 生命周期必须可用明确标记的 TEST DOUBLE 离线验证。
- 实盘连接、真实订阅和真实持续行情分别记录证据。前置不可达或非交易时段只能报告已验证部分；空库、登录成功或模拟行情均不能证明本契约。

技术依据：[本仓库 SDK](third_party/ctp/v6.7.13_20260225/linux64/mdapi/ThostFtdcMdApi.h)。
