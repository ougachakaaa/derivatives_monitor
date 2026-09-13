<a id="analytics-component-contract"></a>

# Analytics 组件契约

Analytics 只通过 [Market Frame](../data_provider/contracts/market-frame.md)消费市场数据，并结合显式、已审核的 ReferenceBundle 计算 Market Indicator。冻结的 MO Skew 公式、时间、质量、revision、reference、provenance 和验证容差唯一见 [Skew v1](contracts/analytics-skew.md)及其机器策略。

参数或 Market Frame 位置不合法抛 `AnalyticsRequestError`，执行预算耗尽抛 `AnalyticsUnavailableError`；二者不携带 HTTP 状态。Query 分别映射为 400/503，Data Provider 的 not-found/unavailable 错误保持穿透到 Query。业务前提不成立仍返回契约化 `UNAVAILABLE`，不得混同基础设施错误。

参考包布局、不可变导入、生产/TEST DOUBLE 准入及固定读取上下文见 [Reference adapter](contracts/references.md)。Analytics 不直接读取 Raw、不联网、不建立缓存或派生数据库，也不依赖 Query。
