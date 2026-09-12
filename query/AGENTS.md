# Query 工作指引

本目录工作先读[根工作协议](../AGENTS.md)、本级[入口](README.md)及与任务对应的本级 Design、Architecture 或 Contract。修改 Market Frame 或 Analytics 时分别读取 [Market Frame](contracts/market-frame.md)与冻结的 [Skew v1](contracts/analytics-skew.md)及其[机器策略](contracts/analytics-skew-v1.json)；参考包读写适配同时读取 [Reference adapter](contracts/references.md)。

Query 只读消费共享 [Raw Boundary](../docs/contracts/raw-boundary.md)，HTTP wire contract、Feature envelope 和 Calendar/Universe protocol 仍在 repository scope。不得让局部实现改写这些共享协议；不得让 Analytics 直接读取 Raw、联网取得参考值或重新生成 oracle expected 来修复回归。

文档或离线回归不读取真实 `collector/data/`、不启动或停止真实服务。先运行 `python3 tests/run.py docs`；Analytics/Skew 变更还必须运行 `python3 tests/run.py analytics`，并按 [Repository Verification](../tests/README.md)核对实际执行项。缺 QuantLib/mpmath 或 Query 环境时如实记为 NOT_RUN，不得签收。
