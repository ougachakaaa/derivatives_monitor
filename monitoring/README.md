# Monitoring v1

Monitoring 是已冻结但尚未实现的本地机会检测与通知 scope。当前目录只包含长期 semantic authority 和证据入口，没有可执行包、启动命令、配置样例或 application SQLite；不要把 execution plan 中的未来命令/结构当成现有能力。

按任务读取：

- 取舍理由：[Design](DESIGN.md)
- 内部目标结构：[Architecture](ARCHITECTURE.md)
- Rule、Evaluation、crossing、UNKNOWN、application state、Event、事务、恢复和 delivery 精确语义：[Contract](CONTRACT.md)
- 当前实现、验证与缺口：[Acceptance](ACCEPTANCE.md)
- 共享 Feature protocol：[Feature Contract](../docs/contracts/features.md)
- 跨模块访问、隔离与系统 lifecycle：[Deployment Contract](../docs/contracts/deployment.md)及[根 Architecture](../ARCHITECTURE.md)
- 产品范围与永久不自动交易边界：[MVP](../docs/mvp.md)

后续实现顺序仍由独立存续的 [Monitoring execution plan](../docs/monitoring-execution-plan.md)安排。只有对应 milestone 真正交付可执行入口后，才在本 README 增加实际配置、启动、停止与排障用法。
