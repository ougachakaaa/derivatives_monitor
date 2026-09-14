<a id="data-provider-calendar-contract"></a>

# Data Provider 组件契约

Data Provider 是只读源码模块，拥有 Raw read adapter、Calendar、coverage 与 Market Frame。共享 Raw、Calendar/Universe 协议分别见 [Raw Boundary](../docs/contracts/raw-boundary.md)和 [Market Session Contract](../docs/contracts/market-session.md)，Market Frame 精确行为见[领域 Contract](contracts/market-frame.md)。

## Raw 只读适配

`Store` 使用参数绑定和短事务读取 Raw schema v2 `market_bars`，遵守共享 WAL/锁边界，不创建、迁移或修改数据库及 sidecar，也不兼容读取其他 schema。无效请求、日库不存在和 schema/文件暂时不可安全读取分别抛出不含 HTTP 状态的 `DataProviderInputError`、`DataNotFoundError`、`DataUnavailableError`；HTTP 400/404/503 映射由 Query 拥有。

`market_calendar.py` 使用纯标准库加载 [版本化年历](calendars/README.md)，可从已核对哈希的原字节初始化。JSON 更新在下次调用生效，profile 代码变化需重启承载它的 Query 进程。CLI 使用同一解释结果并提供 `--validate`。

Data Provider 不联网生成 Calendar、不控制 Collector、不写 Raw，也不依赖 Analytics 或 Query。HTTP 参数和错误映射仍由 [Read Path Contract](../docs/contracts/read-path.md)与 Query adapter 拥有。

## Coverage

Coverage 按 exchange/product 分组，按共享 Universe manifest 中各产品目标日期核对清单，并分别表达订阅、callback 接收、Bar 写入/partial/late、缺口、stale/error 与进程健康。Calendar 状态不得改写 Collector 事实或控制 Collector。Collector 诊断通过 [运行库协议](../docs/contracts/raw-boundary.md#collector-运行诊断协议)只读获取同一事务的 current_status 与 instrument_status；缺失不证明当前 coverage，损坏、不兼容或不一致抛 `DataUnavailableError`。
