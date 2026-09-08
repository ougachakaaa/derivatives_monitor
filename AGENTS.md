# 项目工作约定

先读 [文档入口](docs/README.md)、[MVP](docs/mvp.md)、[架构](docs/architecture.md)，再读所改模块的契约与 README。Analytics 实现必须先读[冻结的 Skew v1](docs/contracts/analytics-skew.md)及其机器策略，不能另选模型/利率/delta或事后放宽验收容差。当前实现及验收缺口以 [验收矩阵](docs/acceptance.md) 为入口；历史报告不代表当前版本已经通过。

- C++ Collector 独立接收、物化并唯一写入 Raw 日 SQLite。Python/Browser/Analytics 的故障不能进入采集链路。
- 分区只取源 TradingDay；保留源、接收、物化时间。默认 15 秒 dirty snapshot 不等于 tick 或自然分钟线，不补造行情。
- Query 只读 Raw，保留 WAL/锁和错误语义；Analytics 经 Market State 契约消费，不直接依赖 Raw SQL。不为页面修改 Raw schema。
- 独立 React 提供页面，FastAPI 只提供 JSON；本地回环访问。公开清单和日历是参考数据，不是 CTP 行情，也不控制采集时段启停。
- `experiments/` 本轮冻结，包括其文档、SDK、demo 和 coverage harness。Collector 仍复用其中 SDK/common；不要搬动或复制 SDK。
- 不清理 `collector/data/`、配置、flow、构建依赖或未跟踪的现场证据。真实凭据不入 Git。原生/容器管理命令会影响真实服务，文档或离线回归不需要执行它们。
- 维护现行设计和长期契约，不再积累 T1/T2 类过程 specs。改变设计时同步修改对应契约、验收矩阵和必要 harness；用户指令优先。没有自动要求逐任务提交或额外批准的流程。
- 新人/agent 从 `python3 harness/run.py docs` 开始；按 [harness 使用说明](harness/README.md)选择回归范围。测试数据标记 TEST DOUBLE；未执行、跳过、缺少证据都不能写成通过。
- 本仓库文档是设计记录，代码是当前实现证据；发现不一致先指出并修正，不用旧报告覆盖当前事实。MVP 尚未完成的业务能力不能因底座测试通过而改成已完成。
