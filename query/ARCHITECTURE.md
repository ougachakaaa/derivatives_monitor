<a id="query-internal-architecture"></a>

# Query HTTP / Composition 架构

Query 是只读 Python/FastAPI 的 HTTP 与 composition boundary。跨组件数据流、所有权与部署边界见[系统 Architecture](../ARCHITECTURE.md)；这里仅说明请求如何连接 owner 模块。

```text
data_provider.storage + data_provider.market_calendar
                    │
                    v
          data_provider.market_frame
                    │
                    v
 analytics.skew + analytics.skew_references
                    │
                    v
       analytics.skew_service
          ├─ query.app（Skew HTTP）
          └─ analytics.indicator_service（Indicator provider）→ query.app（Market Indicator HTTP）
```

- Data Provider 的 `storage.py` 在共享 Raw 只读协议内访问日 SQLite；`market_calendar.py` 解释版本化 Calendar，并为 Market Frame、coverage 与 Universe 工具提供日历能力。
- Data Provider 的 `market_frame.py` 将 Raw、显式 Universe 和 Calendar 组合为 point/minute/latest frame，是 Analytics 的行情读取边界。
- `analytics.skew` 只消费 Market Frame 与显式参考输入；`analytics.skew_references` 固定审核包、Universe 和 Calendar 的读取上下文。
- `analytics.skew_service` 选择业务时间切片并投影公共 Skew 结果；`analytics.indicator_service` 复用该结果形成通用 Market Indicator envelope。二者都不写 Raw 或派生数据库。
- `query.app` 只承接 routes、请求参数/JSON 适配、异常到 HTTP 状态映射、no-store 和依赖组装。公共路径与 wire shape 由 repository [Read Path](../docs/contracts/read-path.md)和 [Market Indicator Contract](../docs/contracts/indicators.md)拥有。

精确读取、Calendar、coverage 与 Market Frame 见 [Data Provider Contracts](../data_provider/CONTRACT.md)；Skew、参考包与 Indicator provider 见 [Analytics Contract](../analytics/CONTRACT.md)；HTTP 映射见[本级 Contract](CONTRACT.md)。
