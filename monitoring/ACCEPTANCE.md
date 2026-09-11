# Monitoring Acceptance

本文件只记录 Monitoring 当前实现、验证证据与缺口；冻结行为见[本级 Contract](CONTRACT.md)，产品及跨模块完成边界见[根 MVP](../docs/mvp.md)和[根 Acceptance](../docs/acceptance.md)。计划中的 milestone、未来命令或测试安排不是实现证据。

<a id="monitoring-delivery-status"></a>

## Monitoring v1 交付状态

2026-09-10，分支 `feature/realtime-monitoring-alerts` 已在 M0 文档冻结之上完成 M1 Feature service / HTTP 工程切片；Monitoring runtime 仍未实现，M2–M5 仍待交付。交接见 [Monitoring execution plan](../docs/monitoring-execution-plan.md)。

| 交付层次 | 当前状态/证据 | 缺口 |
|---|---|---|
| M0 设计冻结 | 产品平行边界、领域模型、依赖/ownership、状态机、事务和投递恢复已落位 authority；milestone 拆为独立 commits | 文档证据仅证明设计和结构检查，不证明业务运行 |
| M1 Feature service / HTTP | 已实现；Query 局部实现与测试证据见 [Query Acceptance](../query/ACCEPTANCE.md#query-feature-evidence) | 当时 packaging 因 Docker 不可用未执行成功；真实 MO/官方参考仍沿用根 G2/G3 缺口 |
| M2 Rule Engine | 待实现 | 纯规则、crossing、UNKNOWN、去重及 representative TEST DOUBLE 回归未执行 |
| M3 持久事件 / runtime | 待实现 | application SQLite、原子提交、独立进程和恢复验证未执行 |
| M4 webhook delivery | 待实现 | 独立投递、尝试记录、有限重试和不确定性恢复验证未执行 |
| M5 工程交付 | 待实现 | 隔离端到端与故障回归、实际运行手册待交付 |
| 真实运行 / 通知 | 未验 | 无真实 Skew Monitoring 运行、实际 webhook 接收或用户收到通知的证据；既有官方参考与真实指标缺口仍保留 |

M0 文档基线检查：`artifacts/harness/20260909T152645Z-docs-a8bc6e08/result.json`（PASS）；领域文档检查：`artifacts/harness/20260909T153512Z-docs-0b2c4144/result.json`（PASS）。报告保留当时 HEAD/dirty patch、平台与日志哈希，只检查文档链接/authority 入口、既有依赖与构建边界，不验证新状态机或未来接口。

完整交接文档检查：`artifacts/harness/20260909T154127Z-docs-30337ce2/result.json`（PASS），`git diff --check` 通过；人工核对仅有 Markdown 变更，业务实现、Skew 机器策略及 oracle 未变。报告后的改动仅补充当时证据登记，并澄清响应 scope 的实际交易日与缺口关闭的去重边界；最终内容以 M0 两个 Git commits 为准。

M0 没有执行 analytics/offline/native/browser/packaging/docker，没有启动/停止真实服务、读取实盘数据或发送 webhook。basis、return、ATM IV 只有扩展性测试规划，未实现生产指标，也未执行这些 TEST DOUBLE 测试。根 G1–G6/P1/P2 均不因 M0 文档冻结签收。

M1 的两个提交、service/provider 与 HTTP 测试数、完整 Query/analytics/docs 结果和 packaging NOT_RUN 边界均保存在 [Query Acceptance](../query/ACCEPTANCE.md#query-feature-evidence)。M1 没有实现或测试 Rule Engine、application SQLite、Monitoring runtime、webhook 或 basis/return/ATM IV，也没有启动/停止真实服务、读取实盘或发送通知。

上述工程 TEST DOUBLE 和文档证据不签收真实 Feature/通知，不改变根 G1–G6/P1/P2，也不关闭 M2–M5。

## S6 authority embedding 证据

2026-09-11，S6 仅迁移并登记本目录的长期 semantic authority，没有增加 Monitoring runtime、配置样例、application SQLite、启动命令或未来子模块。`python3 harness/run.py docs` 为 PASS，报告 `artifacts/harness/20260911T054957Z-docs-90006cb0/result.json`；完整 `harness/tests` 共 33 项通过，包含旧中央 Monitoring Contract 路径不得回流的回归。

该结果只证明当前工作树的文档链接、authority topology/claims、退役路径和既有依赖边界通过离线检查，不验证 Rule Engine、状态机、事务、恢复或 webhook 行为。M2–M5 与真实运行/通知状态保持未实现、未验。
