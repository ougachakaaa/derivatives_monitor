# 设计与证据入口

本目录是项目的长期设计记录（system of record）。只维护一套 MVP 目标与架构；代码、测试和证据用于验证其实现程度。当前 MVP **尚未收尾**；[Analytics / Skew 七项契约](contracts/analytics-skew.md)已冻结，数值核心、只读参考包适配和 Skew JSON 查询已实现；真实业务验收仍待完成。

| 阅读顺序 | 文档 | 回答的问题 |
|---|---|---|
| 1 | [MVP 范围](mvp.md) | 给谁用、解决什么问题、做到哪里停止 |
| 2 | [系统架构](architecture.md) | 模块职责、依赖方向、数据所有权与未实现部分 |
| 3 | [Collector](contracts/collector.md)、[只读 API](contracts/read-path.md)、[Market State](contracts/market-state.md)、[日历和清单](contracts/market-session.md)、[部署](contracts/deployment.md)、[Analytics / Skew](contracts/analytics-skew.md) | 不可破坏的契约和故障语义 |
| 4 | [验收矩阵](acceptance.md)、[Harness](../harness/README.md) | 每个收尾条件如何证明，哪些还没证明 |
| 5 | [运行与恢复](operations.md) | 如何部署、检查、备份和恢复 |
| 6 | [外部参考](references/README.md) | 券商咨询与回复原件、SDK 来源、官方规则 |

[Collector 手册](../collector/README.md)、[Query 手册](../query/README.md)、[Dashboard 手册](../dashboard/README.md)保留可执行命令及模块用法。详细契约由上表对应文档负责，不在各处维护不同版本的设计。

文档状态用词：**已实现**要有代码，**已验证**要说明版本、环境、数据来源与证据，**待实现/待验**不能省略。验收矩阵记录当前状态；[历史验收归档](archive/README.md)只保留过去观察，不是运行手册或新的设计要求。

维护规则：修改行为时同步更新唯一对应契约；修改目标时更新 MVP 和验收条件；日志及大体积行情留在被忽略的证据目录，Git 保存脱敏结论与可定位证据。外部参考保存原件/出处/版本/哈希，与项目自身的设计决定分开。旧过程 specs 已从工作树移除，可从 Git 历史追溯。
