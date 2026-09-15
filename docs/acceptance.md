# 当前 MVP 状态

**MVP 未完成。** 完成标准见 [MVP](mvp.md)；工程 TEST DOUBLE 回归不替代真实行情、人工使用或性能证据。

| 门槛 | 当前状态 | 剩余缺口 |
|---|---|---|
| G1 连续真实运行 | 待验 | 固定环境连续三个完整交易日，含 AU/AG 夜盘、跨午夜及交易日切换 |
| G2 可信数据 | Collector 已实现并离线验证 Raw v2 `market_bars`、event-time bucket、partial/continuity、累计 baseline、唯一写入与 WAL；read path 尚未适配 | Data Provider/Query 仍读取旧 schema；完成下游 v2 只读适配及真实 MO 月链验证 |
| G3 正确指标 | Skew 数值核心已实现于旧 observation 输入；新 Bar provenance/时钟尚未实现 | 先完成 Market Frame/Analytics 的 bucket/event-time 接入，再审核官方日参考包并完成至少十个真实时点独立对账 |
| G4 可用页面 | 汇报首页已实现；人工使用待验 | 真实输入上三次日常使用，验证三十秒理解且无需 SQL/日志 |
| G5 恢复可靠 | 已有部分恢复机制工程回归；heartbeat stale 自动重启闭环尚缺，现场待验 | 完成下述 Collector 可靠性缺口、最终部署版本回归及真实数据隔离备份恢复验证 |
| G6 可以交付 | 开发、原生与 Docker 入口已提供；最终交付待验 | 固定版本可复现部署，审核限制和阻断项 |
| P1 查询性能 | 未验 | 真实一天完整目标链，至少一百次核心查询，P95 ≤ 2 秒并记录错误 |
| P2 显示延迟 | 未验 | 配对同一 Bar 的 bucket、最后 event、接收、提交和显示时间，实测 ≤ 30 秒目标 |

## Collector 第一阶段可靠性缺口

**Collector 第一阶段未完成。** 完成条件由 [MVP](mvp.md#collector-第一阶段完成条件)拥有，不等同于整体 MVP；完整 Query Health evaluator 与下游页面/指标不阻塞此阶段。

| 能力 | 当前实现事实 | 剩余缺口 |
|---|---|---|
| Runtime History | 代码仍使用旧两表格式（user_version=1），仅有 `current_status`、`instrument_status`，新 run 覆盖当前状态；日 Market DB 的 runs 只覆盖日库 provenance | 实现 Runtime runs 的逐次启动持久记录及 append-only 整体 runtime_snapshots；不能把现有日库记录当完整启动历史 |
| History 发布协议 | 当前运行状态写失败回滚并重试，现有 schema 校验恰好两张表，启动发布失败也会继续 | 按已冻结的 [Raw Boundary](contracts/raw-boundary.md#运行库与发布)实现四表 schema、Run 创建失败退出、pending 历史原子发布及重试、终止事务、跨库独立提交；适配 Data Provider、Universe、healthcheck 等只读 schema 校验，验证完整窗口、restart、时钟跳变与不兼容库拒绝规则；不建立迁移或兼容层 |
| Heartbeat 自动恢复 | 主循环约每秒发布、存活窗口 10 秒；Compose 有 healthcheck 和 unless-stopped；native 有异常退出重启，未提供主循环 watchdog 闭环 | 按 [Deployment](contracts/deployment.md#runtime-自动恢复)补齐 stale 后实际终止/重启，分别冻结两种部署的检测、终止、重启参数与总上界，证明 session down 不触发进程重启 |
| 部署环境 | 已有 data/flow 持久目录约束与 Docker 日志轮转配置 | 固定环境的时钟同步、运行身份可写、剩余空间、Market/Runtime DB 增长观察及原生日志容量/保留限制仍需证据 |
| 真实连续运行 | 尚缺该阶段完整现场证据 | 按 [现场模板](live-acceptance-template.md#collector-第一阶段可靠性验收)完成连续运行、断网、强杀、heartbeat stall 和持久性安全验收，关联故障前后 Runtime/Market 事实，证明实际恢复采集 |

历史观察的业务语义与物理协议已冻结，存储实现、消费者适配及相应失败场景验证尚未完成；窗口内短暂 session 变化及缺失观察的解释能力受 [History 证据边界](contracts/collector-health.md#历史解释边界)约束。不得由文档检查、已有 TEST DOUBLE 或仅 unhealthy 的结果关闭上述门槛。

## Collector Health 缺口

[Collector Health 语义](contracts/collector-health.md)已冻结核心事实、生命周期与三态判定。Collector 当前状态和逐合约事实已实现于独立运行库，Data Provider、Query、coverage、Universe 与 healthcheck 从该库读取；不再使用两份 Collector JSON。具体参数和计数口径见 [Raw Boundary](contracts/raw-boundary.md#collector-运行诊断协议)。运行事实的 TEST DOUBLE 工程验证不证明实盘或完整 Health 已完成。

- 完整 Calendar Health evaluator 尚未实现，当前 HTTP 仅投影进程状态与运行事实。
- 尚需冻结多市场活动 scope 的归并、UNKNOWN Calendar、缺失/损坏事实对应的 Health 输出及原因、feed/persistence 阈值和开盘/启动宽限；不得把未知当休市或据此报告 healthy。
- 仓库整体 offline 回归仍有 developer-runner 工作目录断言不一致，以及 smoke fixture 使用已退役 `SnapshotIntervalMs` 的缺口；运行事实独立闭环不替代完整开发会话验收。
- Runtime History 的基础事实目标已定义，存储实现和真实证据见[第一阶段可靠性缺口](#collector-第一阶段可靠性缺口)；结合 Calendar 的完整历史采集完整性解释尚未冻结，不由当前 Health 推导。

模块状态：[Data Provider](../data_provider/ACCEPTANCE.md) · [Analytics](../analytics/ACCEPTANCE.md) · [Query](../query/ACCEPTANCE.md) · [Dashboard](../dashboard/ACCEPTANCE.md)。

运行与恢复见 [Operations](operations.md)，验证命令见 [Repository Verification](../tests/README.md)，结果边界见[证据语义](verification.md)。真实验证使用[现场记录模板](live-acceptance-template.md)，原始证据单独保存，不在本文累计测试流水。
