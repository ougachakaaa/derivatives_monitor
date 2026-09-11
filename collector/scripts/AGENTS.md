# Collector tools 工作入口

本目录工作先读[根工作协议](../../AGENTS.md)、[Collector guidance](../AGENTS.md)和本级[入口](README.md)。Universe 抓取、校验或发布改动读取本级 [Contract](CONTRACT.md)及共享 [Market Session Contract](../../docs/contracts/market-session.md)；native/systemd 或镜像辅助脚本改动读取根 [Deployment Contract](../../docs/contracts/deployment.md)与 [Operations](../../docs/operations.md)。

本 scope 是工具集合，不是 C++ Collector runtime。保留 `universe.py` 对 `query/market_calendar.py` 的已登记工具依赖；不要据此增加 Collector runtime 对 Query 的依赖。`native.py` 协调三个服务，但系统生命周期 authority 仍在根，不在本目录复制。

Universe 修改运行 `python3 -m unittest discover -s collector/tests -p 'test_universe.py' -v`；healthcheck、verify 或 native 修改选择相应部署/离线替身测试。所有样本明确标记 TEST DOUBLE。文档修改从 `python3 harness/run.py docs` 开始，不运行会更改真实 service、Universe、配置或数据的命令。
