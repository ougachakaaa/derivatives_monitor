# Monitoring v1

Monitoring 是已冻结但尚未实现的本地机会检测与通知模块。当前目录只包含冻结的设计、契约和当前状态，没有可执行包、启动命令、配置样例或 application SQLite。

按任务读取：

- 取舍理由：[Design](DESIGN.md)
- 内部目标结构：[Architecture](ARCHITECTURE.md)
- Rule、Evaluation、crossing、UNKNOWN、application state、Event、事务、恢复和 delivery 精确语义：[Contract](CONTRACT.md)
- 当前实现、验证与缺口：[Acceptance](ACCEPTANCE.md)
- 共享 Feature protocol：[Feature Contract](../docs/contracts/features.md)
- 跨模块访问、隔离与系统 lifecycle：[Deployment Contract](../docs/contracts/deployment.md)及[根 Architecture](../ARCHITECTURE.md)
- 产品范围与永久不自动交易边界：[MVP](../docs/mvp.md)
