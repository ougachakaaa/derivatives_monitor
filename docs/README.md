# 长期文档入口

本目录按信息职责维护项目的长期 system of record。每类事实只有一个主要 authority；其他文档应链接它，而不是复制一套容易漂移的描述。代码和测试是当前实现证据，不自动改变产品、设计或契约。

## Authority hierarchy

这些文档不是按“后一份覆盖前一份”排序，而是各自回答不同问题。内容冲突时，先按问题类型回到对应 authority：

| Authority | 唯一负责 | 不负责 |
|---|---|---|
| [MVP](mvp.md) | 产品目标、MVP scope、完成边界 | 当前实现状态、精确接口与运行步骤 |
| [Design](design.md) | 长期设计原则、关键取舍及 rationale | 当前模块清单、精确参数与接口字段 |
| [Architecture](architecture.md) | 当前组件职责、数据流、依赖方向、数据所有权和模块边界 | 取舍理由、精确行为与验收结论 |
| [`contracts/`](contracts/) | 精确行为、不变量、接口及失败语义 | 实现进度、操作教程 |
| [Acceptance](acceptance.md) | 当前实现/验证程度、证据及缺口 | 定义产品或设计 |
| [Operations](operations.md) | 运行、维护、恢复和实际操作说明 | 定义架构或业务契约 |
| 模块 README | build / run / usage / examples / troubleshooting | 第二套 Architecture 或 Contract |

[外部参考](references/README.md)保存来源、版本与原件，不会自动成为项目决定；[历史归档](archive/README.md)只保存过去观察，不证明当前状态。Harness 是验证与证据入口，不定义产品行为。

## 渐进式阅读

新人先读 [MVP](mvp.md)，再用 [Design](design.md)理解取舍、用 [Architecture](architecture.md)定位当前结构。开始具体工作后，只加载对应的 Contract 和模块 README；判断“现在做到哪里”时再读 [Acceptance](acceptance.md)，执行部署、维护或恢复时再读 [Operations](operations.md)。Agent 还须先遵守根 [AGENTS.md](../AGENTS.md)。

精确契约入口：

- [Collector](contracts/collector.md)
- [Read Path](contracts/read-path.md)
- [Market State](contracts/market-state.md)
- [Calendar / Universe](contracts/market-session.md)
- [Deployment](contracts/deployment.md)
- [Analytics / Skew v1](contracts/analytics-skew.md)及其[机器策略](contracts/analytics-skew-v1.json)
- [Feature 查询 v1](contracts/features.md)（已冻结；实现与验证状态见 [Acceptance](acceptance.md)）
- [Monitoring / Opportunity / Notification v1](contracts/monitoring.md)（已冻结，待实现）

可执行模块手册：[Collector](../collector/README.md)、[Query](../query/README.md)、[Dashboard](../dashboard/README.md)。验证入口和证据语义见 [Harness](../harness/README.md)。

## 维护约定

一次性 execution plan 不是长期 system of record；任务完成后应将稳定规则归入对应 authority、在 Acceptance 登记实际证据，并移除活动计划及导航，必要历史从 Git 追溯。不恢复 `docs/tasks/` 或积累逐任务过程 specs。

[Monitoring v1 execution plan](monitoring-execution-plan.md)同样只承载有完成边界的实施交接。本阶段为 M0 文档冻结，M1–M5 留待后续分别实施；产品、领域行为及状态分别以 MVP、Feature/Monitoring Contracts 和 Acceptance 为准，完成后移除活动导航。

修改信息时只更新其 authority，并检查引用它的入口是否仍准确。文档状态用词中，“已实现”必须有代码证据，“已验证”必须说明版本、环境、数据来源与证据；“待实现/待验”不得省略。当前结论统一登记到 Acceptance，不回填为设计定义。旧过程 specs 不再维护，可从 Git 历史追溯。
