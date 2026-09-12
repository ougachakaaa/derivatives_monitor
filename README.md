# derivatives_monitor

本地衍生品监控项目，MVP 聚焦一个 MO 到期月的可信 Skew 观察与分钟回看。产品范围、当前架构、精确契约和实现状态不在本入口重复维护，请从[长期文档入口](docs/README.md)按职责查阅。

## 本地前台开发

准备好三个组件各自的运行依赖和已有 Collector 配置后，从仓库根目录使用统一入口：

```bash
./dev doctor       # 联合启动前检查
./dev up           # 前台运行 Collector、Query、Dashboard
```

`./dev doctor collector|query|dashboard` 可单独检查组件，`./dev up collector|query|dashboard` 可单独运行组件。联合参数见 `./dev up --help`，单组件参数见 `./dev up COMPONENT --help`。用 Ctrl-C 结束本次会话。该入口不安装、构建或接管 systemd/Docker，完整准备步骤、参数示例及三种运行方式的区别见 [Operations](docs/operations.md#前台开发会话)。

- Agent 工作规则：[AGENTS.md](AGENTS.md)
- 产品、设计与结构：[MVP](docs/mvp.md)、[Design](DESIGN.md)、[Architecture](ARCHITECTURE.md)
- 精确行为：[当前契约入口](docs/README.md)
- 当前状态与证据缺口：[Acceptance](docs/acceptance.md)
- 实际部署、维护与恢复：[Operations](docs/operations.md)
- Build / run / usage / examples / troubleshooting：[Collector](collector/README.md)、[Query](query/README.md)、[Dashboard](dashboard/README.md)
- 已冻结、尚未实现的 Monitoring：[Monitoring](monitoring/README.md)
- 安全回归：[Harness README](harness/README.md)；结果与证据语义：[Harness Contract](harness/CONTRACT.md)
- 探索性工作入口：[CTP experiment](experiments/ctp/README.md)、[Data Coverage experiment](experiments/data_coverage/README.md)

`experiments/` 原位保留并服从各自局部文档；它不是正式 Architecture 或 Contract 的替代来源。
