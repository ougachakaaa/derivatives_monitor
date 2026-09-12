# Monitoring 工作指引

本目录工作先读[根工作协议](../AGENTS.md)、本级[入口](README.md)及与任务对应的 [Design](DESIGN.md)、[Architecture](ARCHITECTURE.md)、[Contract](CONTRACT.md)或 [Acceptance](ACCEPTANCE.md)。共享 Feature 请求和 envelope 只读[根 Feature Contract](../docs/contracts/features.md)；跨模块访问、存储隔离和系统生命周期只读[根 Deployment Contract](../docs/contracts/deployment.md)及[根 Architecture](../ARCHITECTURE.md)。

不得让 Monitoring 读写 Raw、导入 Query 私有模块、计算金融指标、接管其他服务或进入自动交易链路。Rule/Evaluation、crossing、UNKNOWN、状态、Event、事务、恢复和投递语义已经冻结；实现任务不得另选状态机、重试参数或失败含义。尚未实现的 CLI、配置文件布局和 SQL schema 不得从计划示例补造为当前能力，也不要预建空子模块。

文档修改从 `python3 tests/run.py docs` 开始。代码改动按本级 Contract 与用户任务选择验证，使用临时目录、随机端口和明确 TEST DOUBLE；不得读取真实配置/Raw、启动或停止真实服务，或发送真实 webhook。
