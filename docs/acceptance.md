# 当前 MVP 状态

**MVP 未完成。** 完成标准见 [MVP](mvp.md)；工程 TEST DOUBLE 回归不替代真实行情、人工使用或性能证据。

| 门槛 | 当前状态 | 剩余缺口 |
|---|---|---|
| G1 连续真实运行 | 待验 | 固定环境连续三个完整交易日，含 AU/AG 夜盘、跨午夜及交易日切换 |
| G2 可信数据 | Collector 已实现并离线验证 Raw v2 `market_bars`、event-time bucket、partial/continuity、累计 baseline、唯一写入与 WAL；read path 尚未适配 | Data Provider/Query 仍读取旧 schema；完成下游 v2 只读适配及真实 MO 月链验证 |
| G3 正确指标 | Skew 数值核心已实现于旧 observation 输入；新 Bar provenance/时钟尚未实现 | 先完成 Market Frame/Analytics 的 bucket/event-time 接入，再审核官方日参考包并完成至少十个真实时点独立对账 |
| G4 可用页面 | 汇报首页已实现；人工使用待验 | 真实输入上三次日常使用，验证三十秒理解且无需 SQL/日志 |
| G5 恢复可靠 | 恢复机制有工程回归；现场待验 | 最终部署版本回归及真实数据隔离备份恢复验证 |
| G6 可以交付 | 开发、原生与 Docker 入口已提供；最终交付待验 | 固定版本可复现部署，审核限制和阻断项 |
| P1 查询性能 | 未验 | 真实一天完整目标链，至少一百次核心查询，P95 ≤ 2 秒并记录错误 |
| P2 显示延迟 | 未验 | 配对同一 Bar 的 bucket、最后 event、接收、提交和显示时间，实测 ≤ 30 秒目标 |

## Collector Health 缺口

[Collector Health 语义](contracts/collector-health.md)已冻结核心事实、生命周期与三态判定；尚未实现完整 evaluator，也未完成业务验收。当前 Collector 发布诊断 v2（2 秒周期），Data Provider `Store.heartbeat()` 仍消费旧字段并返回 unknown/stale 等诊断状态，Query `/api/health` 仅组合既有诊断，未结合 Calendar 产生新语义结果。旧诊断状态不等于新的 Health enum。

- 尚需冻结 `current_status` 的 wire/schema 与旧字段映射；运行累计 `callbacks_accepted` 不等于 `total_ticks_today`，交易日身份、切换、重启累计口径及未收到首个 Tick/commit 的表示仍需明确。
- 约 1 秒 heartbeat / 约 2 秒 alive threshold 仅为建议；现有 Raw Boundary 的 2 秒发布 / 10 秒阈值仍是当前协议参数，变更需同步 producer、consumer 与 healthcheck。
- 尚需冻结多市场活动 scope 的归并、UNKNOWN Calendar、缺失/损坏事实的输出及原因、feed/persistence 阈值和开盘/启动宽限；不得把未知当休市或据此报告 healthy。
- 尚需接入 evaluator 与 HTTP envelope，并验证休市、活跃时段、断线重连、订阅不完整、停 Tick、Tick 正常但 commit 停滞、heartbeat 过期及交易日切换。`runtime_snapshots` 和历史完整性尚未定义或实现。

模块状态：[Data Provider](../data_provider/ACCEPTANCE.md) · [Analytics](../analytics/ACCEPTANCE.md) · [Query](../query/ACCEPTANCE.md) · [Dashboard](../dashboard/ACCEPTANCE.md)。

运行与恢复见 [Operations](operations.md)，验证命令见 [Repository Verification](../tests/README.md)，结果边界见[证据语义](verification.md)。真实验证使用[现场记录模板](live-acceptance-template.md)，原始证据单独保存，不在本文累计测试流水。
