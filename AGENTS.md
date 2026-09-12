# Agent 工作协议

## 阅读入口

先读本文件和[文档入口](docs/README.md)，再按任务读取模块 README、适用祖先 AGENTS 和相关 Contract。系统结构见 [Architecture](ARCHITECTURE.md)，不默认加载全部文档。用户当前指令优先。

除非用户明确提到 `experiments/` 或任务专门要求处理其中内容，否则完全忽略 `experiments/` 及其所有下级内容：不读取、不搜索、不分析，也不将其纳入上下文、实现、验证或文档治理范围。

## 修改规则

- 只修改任务涉及的 SoR，并用链接连接其他职责文档，不复制同一套事实。改变产品边界、设计理由、系统结构或精确行为时，分别同步 MVP、Design、Architecture 或对应 Contract；再按影响更新当前缺口与必要测试。
- 长期文档只记录当前系统和稳定约束，不累计实施计划、迁移历史或测试流水；模块 README 提供用法，重复设计和契约改为链接其定义。
- 发现代码、文档或证据不一致时，先指出不一致及各自 authority，再在任务范围内修正；不要用旧报告覆盖当前事实，也不要因测试通过把尚缺业务证据的能力写成已完成。
- 仅在上述例外成立时，`experiments/` 的实验文档、SDK、demo 和局部 coverage 验证资产才进入任务范围，并服从其目录内的局部说明；仓库级文档治理不把它们改写成正式系统 SoR，也不搬动、复制或重构任务未涉及的实验内容。

## 现场保护与验证

- 不清理 `collector/data/`、配置、flow、构建依赖、日志或未跟踪现场证据；真实凭据不入 Git。文档或离线回归不执行会影响真实服务的原生/容器管理命令。
- 新人或 agent 从 `python3 tests/run.py docs` 开始，并按 [Repository Verification](tests/README.md)选择与改动相称的安全回归。测试数据必须标记 TEST DOUBLE；未执行、跳过或缺少证据均不能写成通过。
- Analytics 改动必须先读[冻结的 Skew v1 Contract](query/contracts/analytics-skew.md)及其机器策略；不得另选模型、参数或事后放宽验收容差。Raw producer/consumer 改动同时读取[共享边界](docs/contracts/raw-boundary.md)。
