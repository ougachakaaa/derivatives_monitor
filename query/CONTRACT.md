<a id="query-read-contract"></a>

# Query 组件契约

本文件定义 Query 的 HTTP 适配与 composition boundary。Raw read、Calendar、coverage 与 Market Frame 由 [Data Provider](../data_provider/CONTRACT.md)拥有；Skew 与 Market Indicator provider 由 [Analytics](../analytics/CONTRACT.md)拥有；共享 HTTP 与 Market Indicator envelope 分别见 [Read Path](../docs/contracts/read-path.md)和 [Market Indicator](../docs/contracts/indicators.md)。

Collector Health 由 Query 组合只读 Runtime Facts、Calendar 与 evaluator，语义只由 [Collector Health Contract](../docs/contracts/collector-health.md)定义；不在 HTTP adapter 内重写 Calendar 或存储规则，具体 wire 由 [Read Path](../docs/contracts/read-path.md#健康证据)拥有。

Query 将 Data Provider 的无效输入、缺失数据和不可用错误分别映射为 400、404、503，并保持公共 `{"error": ...}` wire。HTTP 参数、方法、JSON 和 no-store 由 Query 与共享 Read Path 拥有；Query 不解释 SQLite、Calendar、Market Frame 或 coverage 内部规则。

Query 将 `AnalyticsRequestError`（包括 `IndicatorRequestError`）映射为 400，将 `AnalyticsUnavailableError` 映射为 503；契约化 `UNAVAILABLE` 仍是 200 业务响应。Query 只解析 Indicator 请求的 content-type、严格 JSON 与 HTTP query，不重新校验 provider scope、参数或业务结果。未预期异常保持 500，不包装为正常业务失败。
