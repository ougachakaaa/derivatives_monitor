<a id="repository-product-boundary"></a>

# MVP：可信的单月期权 Skew 观察

目标用户是项目所有者，使用场景为本地个人盯盘与研究。完成定义：连续几个交易日通过页面完成真实市场观察，知道数据是否可信，并能追溯或回看结果。

## 行情接入能力边界

项目只接入 CTP MdApi 的行情推送，不接入 TradeApi / TraderApi；不提供报单、撤单、资金、持仓或成交查询等交易接口能力。行情订阅与接收所需的 MdApi 连接/登录流程保留，不因排除交易接口而删除。此边界不缩减已有只读查询、分析与页面能力。

## 固定范围

- 业务闭环：选定 **MO 一个到期月**，查看 Skew 当前水平、当日分钟变化和指定分钟回看；同时看到数据时间、质量与不能计算的原因。
- 现有采集范围保留：CFFEX IF/IH/IC/IM、TS/TF/T/TL、IO/HO/MO，以及 SHFE AU/AG 期货。分析不要求同时扩展至所有品种/月。
- 业务结果通过[当前系统架构](../ARCHITECTURE.md)定义的采集、只读解释、分析、JSON 和汇报页面闭环交付；当前实现及证据缺口只在[验收矩阵](acceptance.md)登记。
- 长期取舍理由见[设计原则](../DESIGN.md)，精确数据、时间、质量、分析与部署行为由对应 [Contracts](contracts/) 定义。

## Collector 第一阶段完成条件

Collector 第一阶段以能够长期部署并完成真实连续采集验收为目标，独立于下述单月 Skew 产品收尾。已完成的 Market Bar 聚合、CTP reconnect、SQLite Raw persistence 和 TradingDay rollover 不在这里重复定义。

1. **历史运行事实**：具备 [Runtime History](contracts/collector-health.md#current-status-与-runtime-history)，持久记录每次启动和主循环运行观察；仅凭 Runtime DB 与 Market DB 即可关联 restart、session/login/订阅、接收与提交事实，日志用于进一步排障。证据不足时明确未知。
2. **自动恢复**：进程退出及 heartbeat stale 后，正式 supervisor 实际重启 Collector 并恢复采集；检测到新进程启动的时间有界，CTP 断线仍由 Collector 自恢复。要求由 [Deployment](contracts/deployment.md#runtime-自动恢复)定义。
3. **可靠部署环境**：满足[系统时钟、持久存储、磁盘和日志前提](contracts/deployment.md#长期运行环境前提)，更新及故障恢复不删除已提交历史。
4. **真实连续运行和恢复验收**：固定部署环境至少连续三个完整交易日，覆盖日盘、夜盘、跨午夜和 TradingDay rollover；验证断网恢复、强制终止后重启、主循环 stall 后实际重启，以及事务完整、canonical Bar 不重复不修改、同日多 run 继续追加且交易日不混写。断线允许真实行情缺口，不要求补采。按[现场模板](live-acceptance-template.md#collector-第一阶段可靠性验收)保留证据。

该阶段完成后，无需 Dashboard，也应能由持久化事实和日志回答当前是否活着、过去是否留下运行观察、是否 restart、无行情发生在哪一层，以及故障后是否自动恢复并继续采集；历史事实的可判定范围遵守 [Health Contract](contracts/collector-health.md#历史解释边界)。

Dashboard、完整 Query Health evaluator、`healthy / degraded / down` UI、Runtime History 可视化、告警推送、Analytics / IV / Skew / Basis、自动交易、per-instrument Runtime history、复杂 event sourcing、断线行情补采和 Runtime DB 按日拆分均不阻塞此阶段。此边界不改变整体 MVP 的指标、页面及 G1–G6/P1/P2 要求，也不改变禁止自动交易的产品边界。当前缺口见 [Acceptance](acceptance.md#collector-第一阶段可靠性缺口)。

## 业务指标边界

MVP 使用 **`mo-skew-25d-v1`** 作为唯一 Skew 指标定义。模型、远期、参考输入、时间选择、报价质量、数值求解、失败语义和验证容差的唯一完整来源是 [Analytics / Skew Contract](../analytics/contracts/analytics-skew.md)及其[机器策略](../analytics/contracts/analytics-skew-v1.json)；本文件只规定该指标必须支撑上述单月观察闭环，不复制其算法。

## 六个收尾条件

1. **真实运行**：在声明的机器、配置、合约范围下连续 3 个完整交易日，无日常人工修复，无无法解释的数据中断。AU/AG 既已纳入采集范围，需补真实夜盘开盘、跨零点、次日日盘、下一真实 TradingDay 的连续证据。
2. **可信数据**：清单、订阅、callback 接收、Bar partial、陈旧、无效分别表达；缺失/过期不产出貌似正常指标；历史值有明确 bucket 与 event time。不能要求不活跃合约固定推送，也不能把 Bar 行数或 callback count 当逐笔成交数。
3. **正确指标**：完整闭环可用；至少 10 个时点独立核对，覆盖正常/异常输入与时段边界，按预定误差验收。结果能定位 Raw revision、Universe、Calendar、参数和算法版本。
4. **可用页面**：30 秒内看懂对象、水平与变化、数据时间、可信程度；连续 3 次日常观察无需 SQL/日志。诊断明细可展开，首页采用汇报模式。
5. **恢复可靠**：断线重连、异常退出后重启、Query 独立停启通过；健康失效及时显示，已提交数据保留；完成一次真实数据备份恢复并验证历史查询。
6. **可以交付**：固定验收版本；在声明支持的部署方式上可复现部署；启动/停止/更新/恢复说明齐全；阻断问题清零，其余限制可查。原生和 Docker 的证据分开记录。

性能门槛：固定机器、真实一天数据、单人使用，核心查询 P95 ≤ 2 秒；至少 100 次成功请求并记录错误数，不能把失败请求从报告中隐藏。持续活跃且输入可用时，在固定 15 秒 bucket、1 秒封口 grace 与页面轮询配置下，页面接收至显示延迟目标 ≤ 30 秒；分别记录 bucket、最后 event、接收、提交与显示时间。这是待实测目标，非现有性能保证。

“核心查询”包括当前/指定分钟 Skew 及当天变化；health/market-bars 诊断接口通过不替代 Skew 业务查询性能验收。验收样本需覆盖完整目标月链及积累一天后的库，不能仅测空库。

## 阻断与后续事项

错交易日、丢已提交数据、错误/不可追溯指标、旧数据假装当前、频繁人工修复、缺真实业务验收，均阻止收尾。测试全绿只证明已覆盖的工程条件。

更多品种分析、更多指标、复杂图表、策略研究/回测、云部署/认证、WebSocket、Dev Container 不纳入本版单月 Skew 观察闭环。系统未来可以基于市场分析结果支持用户定义的观察条件和通知，但永远不进入自动下单或交易执行。

当前状态及证据缺口见[验收矩阵](acceptance.md)。这里定义目标，不将底座验收完成改称整个产品完成。
