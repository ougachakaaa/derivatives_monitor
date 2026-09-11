<a id="query-read-contract"></a>

# Query 组件契约

本文件定义 Query 内部读取、Calendar/coverage 适配与 Feature provider 规则。共享 Raw、HTTP、Feature envelope 及 Calendar/Universe protocol 分别见 [Raw Boundary](../docs/contracts/raw-boundary.md)、[Read Path](../docs/contracts/read-path.md)、[Feature](../docs/contracts/features.md)和 [Market Session](../docs/contracts/market-session.md)。

## 只读数据适配

Query 按共享 Raw Boundary 打开日库，查询使用参数绑定，不接受任意 SQL 或文件路径。`Store.connect` 使用只读事务与既有执行预算，并将缺失日库与不可读、不兼容、锁/WAL 条件不成立或查询超时分成明确的 `QueryError`；公开 404/503 映射只由 repository [Read Path](../docs/contracts/read-path.md#sqlite-只读限制)定义。Query 不写 Raw、WAL/sidecar、参考包或派生数据库。

`GET /api/health` 只投影共享 Collector 运行诊断，不建立第二套心跳、存活或行情新鲜定义。日文件、summary 与 snapshot 读取不跨库猜测数据；参数和公开响应仍以 repository HTTP contract 为准。

<a id="query-calendar-contract"></a>

## Calendar 与 coverage 适配

`market_calendar.py` 是纯标准库模块，加载随 Query 发布的版本化年历；可从已核对哈希的原字节初始化。文件缺失、损坏、范围外或下一交易日无法确认时明确返回 UNKNOWN，不用工作日或自然日兜底。JSON 更新在下次请求生效，profile 代码变化才需重启 Query。

`/api/sessions` 和 Calendar CLI 使用同一解释结果；CLI 同时提供 `--validate`。Query coverage 按 exchange/product 分组，并按共享 Universe manifest 中各产品的目标日期核对清单；它分别表达订阅、接收、缺口、stale/error 与进程健康，不以 Calendar 状态改写 Collector 事实或控制 Collector。

<a id="query-feature-provider-contract"></a>

## Feature provider

Query 使用显式的 `feature_id → provider` 注册表。生产注册表只纳入已有指标契约的实现，TEST DOUBLE 仅通过测试注入，不提供生产绕过开关；不加载动态插件、DSL、通用计算图或后台指标任务。provider 不依赖 Monitoring，通用引擎也不理解 provider 的金融字段。

`mo-skew-25d-v1` provider 复用 `SkewService.query('latest', month=显式月份, at=requested_at)`，严格实现 repository [Feature Contract 的 Skew 映射](../docs/contracts/features.md#3-mo-skew-provider-映射)。它不重新计算、舍入、重选分钟或报价，也不自定义 sample key。

未来 provider 必须先有明确指标定义和证据，再登记同一接口。rolling market window 若由指标需要，属于 provider 的输入选择/计算状态，须按指标契约从 Market State 显式历史读取并保留 revision/reference 身份；不得由 Monitoring 轮询积累价格来定义窗口，也不得获得 Market Facts 写权。
