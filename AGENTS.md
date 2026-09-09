# Agent 工作协议

## 阅读与 authority

先读本文件和[文档入口](docs/README.md)，再按任务定位唯一的长期信息源，不默认一次加载全部文档。产品范围与完成边界读 [MVP](docs/mvp.md)；设计原则和取舍理由读[设计原则](docs/design.md)；当前组件、数据流和所有权读[系统架构](docs/architecture.md)；精确行为、接口、不变量及失败语义只读所改领域的 `docs/contracts/`；当前实现和证据缺口读[验收矩阵](docs/acceptance.md)；实际操作读[运行与恢复](docs/operations.md)及对应模块 README。

发生冲突时按信息职责裁决，而不是把较新的文字一概当作权威：Contract 决定精确行为，MVP 决定产品边界，Architecture 决定当前结构，Design 解释长期理由，Acceptance 只陈述实现/验证状态，Operations 和模块 README 只提供操作与用法。代码是当前实现证据，但不会静默改写设计或契约；历史归档和外部资料都不是现行要求。用户当前指令优先。

## 修改规则

- 只修改任务涉及的 SoR，并用链接连接其他职责文档，不复制同一套事实。改变产品边界、设计理由、系统结构或精确行为时，分别同步 MVP、Design、Architecture 或对应 Contract；再按影响更新验收矩阵与必要测试。
- 不恢复 `docs/tasks/` 或积累 T1/T2 类过程 specs。模块 README 长期只承载 build / run / usage / examples / troubleshooting；发现其中重复设计或契约时，优先链接其 SoR。
- 发现代码、文档或证据不一致时，先指出不一致及各自 authority，再在任务范围内修正；不要用旧报告覆盖当前事实，也不要因测试通过把尚缺业务证据的能力写成已完成。
- `experiments/` 的实验文档、SDK、demo 和局部 coverage harness 服从其目录内的局部说明与任务范围；仓库级文档治理不把它们改写成正式系统 SoR，也不在未明确要求时搬动、复制或重构。

## 现场保护与验证

- 不清理 `collector/data/`、配置、flow、构建依赖、日志或未跟踪现场证据；真实凭据不入 Git。文档或离线回归不执行会影响真实服务的原生/容器管理命令。
- 新人或 agent 从 `python3 harness/run.py docs` 开始，并按 [Harness 说明](harness/README.md)选择与改动相称的安全回归。测试数据必须标记 TEST DOUBLE；未执行、跳过或缺少证据均不能写成通过。
- Analytics 改动必须先读[冻结的 Skew v1 Contract](docs/contracts/analytics-skew.md)及其机器策略；不得另选模型、参数或事后放宽验收容差。
