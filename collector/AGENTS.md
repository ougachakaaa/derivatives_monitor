# Collector 工作入口

本目录工作先读[根工作协议](../AGENTS.md)和本级[入口](README.md)，再按任务读取[内部结构](ARCHITECTURE.md)或[运行契约](CONTRACT.md)。涉及 Raw writer、WAL、只读或诊断协议时同时读取[共享 Raw Boundary](../docs/contracts/raw-boundary.md)；涉及 systemd、Compose 时读取[根 Deployment Contract](../docs/contracts/deployment.md)，涉及 developer runner 时读取 [Developer Runner Contract](../docs/contracts/developer-runner.md)；实际操作见 [Operations](../docs/operations.md)。

`collector/scripts/` 是独立工具 scope；修改其文件时继续读取该目录的 [AGENTS](scripts/AGENTS.md)。特别不要把 Universe 工具对 Data Provider Calendar 的合法依赖推广成 C++ Collector runtime 依赖，也不要把 repository integration 的生命周期规则下沉到 Collector。

Collector 行为修改至少运行对应 CTest；配置、SDK lifecycle、采样、存储或进程停止改动按 [Repository Verification](../tests/README.md)选择相称的离线 profile。测试输入必须明确标记 TEST DOUBLE。文档修改从 `python3 tests/run.py docs` 开始；不得为验证启动、停止或更新真实服务，也不得读取或清理真实配置、data、flow 与日志。
