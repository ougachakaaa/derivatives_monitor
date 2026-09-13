# Data Provider 工作指引

本目录工作先读[根工作协议](../AGENTS.md)、本级[入口](README.md)及适用 Contract。Calendar 改动同时读取共享 [Market Session Contract](../docs/contracts/market-session.md)。本模块只读解释市场事实和参考数据，不控制 Collector，不写 Raw，也不依赖 Analytics 或 Query。

测试输入必须明确标记 TEST DOUBLE。文档修改从 `python3 tests/run.py docs` 开始；Calendar 修改运行 `query/.venv/bin/python -m unittest data_provider.tests.test_calendar -v`，不得读取真实 `collector/data/` 或管理真实服务。
