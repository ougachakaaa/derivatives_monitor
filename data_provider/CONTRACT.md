<a id="data-provider-calendar-contract"></a>

# Data Provider 组件契约

Data Provider 是只读源码模块；当前拥有 Calendar 的加载与解释。交易日、时段、UNKNOWN、Universe 日期交接及 Collector 隔离语义唯一见共享 [Market Session Contract](../docs/contracts/market-session.md)。

`market_calendar.py` 使用纯标准库加载 [版本化年历](calendars/README.md)，可从已核对哈希的原字节初始化。JSON 更新在下次调用生效，profile 代码变化需重启承载它的 Query 进程。CLI 使用同一解释结果并提供 `--validate`。

Data Provider 不联网生成 Calendar、不控制 Collector、不写 Raw，也不依赖 Analytics 或 Query。HTTP 参数和错误映射仍由 [Read Path Contract](../docs/contracts/read-path.md)与 Query adapter 拥有。
