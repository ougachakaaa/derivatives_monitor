<a id="query-internal-architecture"></a>

# Query 内部架构

Query 是只读 Python/FastAPI 组件。跨组件数据流、所有权与部署边界见[系统 Architecture](../ARCHITECTURE.md)；这里仅说明 Query 内部文件关系。

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
          └─ query.indicator_service（Indicator provider）→ query.app（Market Indicator HTTP）
```

- Data Provider 的 `storage.py` 在共享 Raw 只读协议内访问日 SQLite；`market_calendar.py` 解释版本化 Calendar，并为 Market Frame、coverage 与 Universe 工具提供日历能力。
- Data Provider 的 `market_frame.py` 将 Raw、显式 Universe 和 Calendar 组合为 point/minute/latest frame，是 Analytics 的行情读取边界。
- `analytics.skew` 只消费 Market Frame 与显式参考输入；`analytics.skew_references` 固定审核包、Universe 和 Calendar 的读取上下文。
- `analytics.skew_service` 选择业务时间切片并投影公共 Skew 结果；Query 当前的 `indicator_service.py` 复用该结果形成通用 Market Indicator envelope。二者都不写 Raw 或派生数据库。
- `app.py` 只承接 HTTP 适配。公共路径、wire shape、状态码与 no-store 由 repository [Read Path](../docs/contracts/read-path.md)和 [Market Indicator Contract](../docs/contracts/indicators.md)拥有。

精确读取、Calendar、coverage 与 Market Frame 见 [Data Provider Contracts](../data_provider/CONTRACT.md)；Skew 与参考包见 [Analytics Contract](../analytics/CONTRACT.md)，当前 Indicator provider 规则见[本级 Contract](CONTRACT.md)。
