# Dashboard 工作指引

本目录工作先读[根工作协议](../AGENTS.md)、本级[入口](README.md)和[页面契约](CONTRACT.md)；判断当前实现、测试证据或缺口时再读[本级 Acceptance](ACCEPTANCE.md)。

Dashboard 只拥有 presentation 行为。公共 HTTP 路径、参数、wire shape 与错误码由[共享 Read Path](../docs/contracts/read-path.md)拥有，Calendar/Universe 交接由[共享 Market Session](../docs/contracts/market-session.md)拥有，Indicator envelope 由[Indicator Contract](../docs/contracts/indicators.md)拥有；Market Frame、Skew/Analytics、solver 与 reference semantics 属于 [Query](../query/README.md)。不得根据 React 当前实现补造这些上游契约，也不得把显示舍入、轮询状态或浏览器缓存反向写成指标语义。

文档修改从 `python3 tests/run.py docs` 开始。修改 React 行为至少运行 `npm test` 与 `npm run build`，涉及真实浏览器交互时按 [Repository Verification](../tests/README.md)选择 browser profile。测试场景必须明确标记 TEST DOUBLE；文档或离线回归不读取真实配置/Raw，不启动、停止或更新真实服务。
