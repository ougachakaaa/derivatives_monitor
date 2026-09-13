# Analytics 工作指引

本目录工作先读[根工作协议](../AGENTS.md)、本级[入口](README.md)、冻结的 [Skew v1 Contract](contracts/analytics-skew.md)及其[机器策略](contracts/analytics-skew-v1.json)。参考包改动同时读取 [Reference adapter](contracts/references.md)，不得另选模型、参数、容差或重生成 expected 来修复回归。

Analytics 只消费 Data Provider public API 和显式参考输入，不直接读取 Raw、联网取得参考值、依赖 Query，或写派生事实。修改后运行 `python3 tests/run.py analytics`；缺少依赖或证据必须如实记为 NOT_RUN。
