<a id="repository-design-principles"></a>

# 长期设计原则与取舍

本文回答“为什么这样设计，以及系统演进时应守住什么”。产品目标和停止边界由 [MVP](docs/mvp.md)定义，当前组件结构由 [Architecture](ARCHITECTURE.md)描述，任何精确行为、参数、接口和失败语义以对应 [Contract](docs/README.md) 为准，当前实现与验证程度见 [Acceptance](docs/acceptance.md)。

## 1. 先保存事实，再解释事实

系统优先保留可追溯的市场事实，派生解释位于事实记录之外。这样做使采集到的内容不会因页面、指标或研究口径变化而被覆写，也让后续算法能够针对同一输入复核。Raw 的规范事实是 Collector 根据实际收到的 CTP callback 形成的自然时间对齐 15 秒 Market Bar：它同时保存 bucket 内聚合结果和 bucket-close 市场状态，但不把未保存的事件包装成完整 tick 历史或逐笔成交 OHLC。

因此，面向展示或分析的新需求不应反向塑造 Raw；派生结果应携带足够的输入身份和来源，在无法计算时保留原因，而不是修正、补齐或替换原始事实。具体数据所有权见 [Architecture](ARCHITECTURE.md)，保存和读取不变量见 [Raw Boundary](docs/contracts/raw-boundary.md)及其链接的 provider/consumer Contracts。

## 2. 将采集保持为最小、独立的故障域

行情接收和持久化是系统最需要连续性的路径。分析、HTTP、浏览器或运维辅助能力的失败不应阻断这一链路，也不应成为采集成立的前置条件。代价是下游只能通过明确的持久化和只读边界观察数据，但这比把快速演进的解释层耦合进采集进程更容易恢复和审计。

系统演进可以增加新的消费者，但不能未经重新设计就让消费者控制采集生命周期或取得 Raw 写所有权。当前依赖方向和组件边界见 [Architecture](ARCHITECTURE.md)；精确生命周期与失败语义见 [Contracts](docs/README.md)。

## 3. 对时间、采样和未知保持诚实

市场数据同时具有事件、接收、持久化和展示等不同时间语义，它们不能相互冒充。Collector 以 `ActionDay + UpdateTime + UpdateMillisec` 组成的 CTP event time 决定固定 15 秒 bucket，以 `TradingDay` 决定日库分区；接收和提交时间只证明本地观察与发布过程。Raw Bar 是有界观察，不等于逐事件历史、自然分钟线或断线回补。

这项取舍减少了伪造确定性的风险：没有 callback 的 bucket 不造行，不以历史 close 填充；观察连续性或累计 baseline 失效时以 partial 和原因表达，不能猜测成交增量。缺失、陈旧、无效、休市和未知仍应分别表达，历史值不能披上当前时间。具体时钟、分区、聚合和质量阈值属于 Contracts，本文不重复维护数值。

## 4. 将参考事实作为显式、可版本化输入

日历、挂牌清单、产品规则和估值参数来自与行情不同的来源。它们用于解释市场事实，但不应改写源行情、猜测缺失值或隐式控制采集。版本化、审核过的显式输入可以让历史解释复查，也能把“交易所事实”“项目选择”和“运行时观测”分开。

外部材料只是依据，不会仅因被保存就成为系统决定。项目采用的精确来源、有效性和拒绝规则由对应 Contract 冻结；必要来源说明放在对应模块。

## 5. 让派生结果可重放、可丢弃

派生计算通过受契约约束的只读 Market Frame 消费事实，并显式携带输入 revision、参考版本和算法身份。这样可以区分“同一历史输入的重建”与“当时已经产出的结果”，也避免分析代码依赖 Raw 表结构或隐藏的当前状态。

Analytics 按 Query 请求计算可重建派生值，不另建第二份权威派生库或常驻调度器；这不改变派生结果不能成为市场事实来源的跨模块边界。

## 6. 失败语义是业务输出的一部分

市场分析系统最危险的结果不是空值，而是看似正常但来源、时间或质量不成立的数字。因此系统宁可显式不可用，也不静默使用旧行情、默认参考值、替代价格或宽松容差。诊断健康、市场活跃、输入完整与指标可计算是不同层次，不能合并成一个绿色状态。

Collector Health 同样遵循“先保存事实，再解释事实”：heartbeat 证明运行活动，市场时段决定是否期待行情，派生诊断不覆盖运行事实。这使休市静默与采集故障保持可区分，精确规则见 [Collector Health Contract](docs/contracts/collector-health.md)。

当前状态会被覆盖，不能承担历史故障解释；持久化启动事实和独立于行情活动的 Runtime History，才能区分无行情与没有正常运行观察。Run 生命周期独立于 Market 日库，使未产出行情的启动也有来源证据；缺失观察保持未知，不用后补零值制造连续性。启动身份先持久化，使行情来源可追溯；运行期历史发布与 Market 独立提交，使诊断写入失败不撤销已成立的行情事实。精确职责见 [Runtime History](docs/contracts/collector-health.md#current-status-与-runtime-history)。

CTP session failure 与 Collector Runtime failure 分属不同恢复层：应用能够自行重连外部 session，而已经停止推进的主循环需要外部 supervisor 恢复。将恢复控制留在部署层，避免行情静默触发无意义重启，也避免只报告 unhealthy 却无法继续采集；具体闭环见 [Deployment](docs/contracts/deployment.md#runtime-自动恢复)。

错误分类、状态码和可计算条件属于 Contract；页面和运维视图只投影这些语义，不各自发明判断。

## 7. 以本地、可恢复的个人观察闭环控制范围

当前产品服务本地个人盯盘与研究，因此优先选择可检查的持久化、只读访问、明确服务边界和可演练恢复，而不是交易执行、外网暴露或分布式基础设施。服务生命周期与数据生命周期分离，使软件更新和单个组件重启不等同于删除历史事实。

本地开发会话与持久部署使用独立的生命周期所有权，使结束调试不会意外停止长期采集，也使开发工具无需接管系统服务。统一开发入口只降低组合现有组件的操作成本，不成为新的业务依赖；精确边界见 [Developer Runner Contract](docs/contracts/developer-runner.md#repository-developer-runner-contract)。

若未来产品目标变化，应先修改 MVP；若因此改变取舍理由、组件结构或精确行为，再分别修改 Design、Architecture 和 Contracts，并在 Acceptance 中重新评估已有证据。

## 8. 用证据驱动复杂度和演进

缓存、额外存储、调度或更宽部署面只应由明确的产品需求和真实性能/运维证据驱动。工程回归证明的是已覆盖行为，TEST DOUBLE、跳过项和历史报告不能替代实盘观察。探索性实验可以提供证据，但在明确纳入 Architecture 和 Contracts 前，不是正式运行时设计。

## 9. 统一市场分析领域语言

系统沿以下稳定语义关系演进；它描述领域概念及依赖方向，不表示每一层当前都已实现为独立模块：

```text
Raw Market Data
→ Market Frame
→ Market Indicator
→ Market State
→ Candidate Selection
→ Human Decision
```

- **Raw Market Data** 是 Collector 保存的市场事实。
- **Market Frame** 是按明确 scope、time 与 revision 组织的结构化市场数据视图。
- **Market Indicator** 是从市场数据计算出的描述性分析结果，例如 Skew、IV Gradient 或 Return。
- **Market State** 是综合多个 Market Indicators 后形成的市场决策状态；当前尚未实现。
- **Candidate Selection** 结合 Market State 与 position/risk context 形成具体交易候选；当前尚未实现。
- **Human Decision** 是系统外的最终交易判断。
- **Market Session State** 只表示 `OPEN / BREAK / CLOSED / UNKNOWN` 交易时段状态，不是 Market State。

实现职责与领域输出分开：Data Provider 产生 Market Frame，Analytics 计算 Market Indicator。Analytics 是计算能力，不是与 Market Indicator 平级的领域输出。系统不为派生结果或机会判断引入平行领域层，也不因保留未来术语就预建 Market State Engine 或 Candidate Selector。

## 10. 以稳定语义共享 Analytics

Data Provider、Analytics 与 Query 是同一 Python 环境和 Query 进程内的三个源码包。Data Provider 负责事实读取，Analytics 负责可重放计算与薄 Indicator provider，Query 只负责 HTTP 和依赖组装；源码 ownership 清晰，但不为此增加独立发布包、镜像、IPC 或服务。无真实消费者或失败模式时，不预建计算图、动态插件和窗口框架。

只有出现独立发布需求、进程级故障隔离需求，或性能证据表明当前物理边界不合适时，才值得进一步拆成独立运行单元；新增一个指标本身不足以触发。边界调整必须保持 Indicator ID、数值、时间、质量和追溯语义，并用相同输入对等验证，不借搬迁变更业务。当前物理边界见 [Architecture](ARCHITECTURE.md)，公共语义见 [Market Indicator Contract](docs/contracts/indicators.md)。
