# derivatives_monitor

本地衍生品监控项目，MVP 聚焦一个 MO 到期月的可信 Skew 观察与分钟回看。产品范围、当前架构、精确契约和实现状态不在本入口重复维护，请从[长期文档入口](docs/README.md)按职责查阅。

- Agent 工作规则：[AGENTS.md](AGENTS.md)
- 产品、设计与结构：[MVP](docs/mvp.md)、[Design](docs/design.md)、[Architecture](docs/architecture.md)
- 精确行为：[Contracts](docs/contracts/)
- 当前状态与证据缺口：[Acceptance](docs/acceptance.md)
- 实际部署、维护与恢复：[Operations](docs/operations.md)
- Build / run / usage / examples / troubleshooting：[Collector](collector/README.md)、[Query](query/README.md)、[Dashboard](dashboard/README.md)
- 安全回归与证据语义：[Harness](harness/README.md)
- 外部来源与历史记录：[References](docs/references/README.md)、[Archive](docs/archive/README.md)

`experiments/` 原位保留，并由其局部文档说明用途；它不是正式 Architecture 或 Contract 的替代来源。
