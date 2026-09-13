<a id="analytics-component-contract"></a>

# Analytics 组件契约

Analytics 只通过 [Market Frame](../data_provider/contracts/market-frame.md)消费市场数据，并结合显式、已审核的 ReferenceBundle 计算 Market Indicator。冻结的 MO Skew 公式、时间、质量、revision、reference、provenance 和验证容差唯一见 [Skew v1](contracts/analytics-skew.md)及其机器策略。

参数或 Market Frame 位置不合法抛 `AnalyticsRequestError`，执行预算耗尽抛 `AnalyticsUnavailableError`；二者不携带 HTTP 状态。Query 分别映射为 400/503，Data Provider 的 not-found/unavailable 错误保持穿透到 Query。业务前提不成立仍返回契约化 `UNAVAILABLE`，不得混同基础设施错误。

参考包布局、不可变导入、生产/TEST DOUBLE 准入及固定读取上下文见 [Reference adapter](contracts/references.md)。Analytics 不直接读取 Raw、不联网、不建立缓存或派生数据库，也不依赖 Query。

<a id="analytics-indicator-provider-contract"></a>

## Market Indicator provider

Analytics 使用显式的 `indicator_id → provider` 注册表。生产注册表只纳入已有指标契约的实现，TEST DOUBLE 仅通过测试注入，不提供生产绕过开关；不加载动态插件、DSL、通用计算图或后台指标任务。通用引擎不理解 provider 的金融字段。

`mo-skew-25d-v1` provider 复用 `SkewService.query('latest', month=显式月份, at=requested_at)` 的结果，不另建金融实现。它到通用 envelope 的映射如下：

| Market Indicator 字段 | Skew 结果来源 |
|---|---|
| `value / unit` | `skew_25d_vp / unit`（`vol_point`） |
| `scope / status / reasons` | 同名字段 |
| `effective_at / evaluated_at` | `valuation_at / evaluated_at` |
| `historical / current_usable` | 同名字段 |
| `sample_key` | 实际交易日、业务 scope 与封口分钟的确定性身份；不含 raw_revision、参考修订或请求时间 |
| `evidence` | 包括 algorithm、quality、raw_revision、Universe/Calendar/ReferenceBundle 身份和哈希、provenance 的完整公共结果 |

完整结果放入 `evidence`，通用字段直接投影，不重新计算、不按显示精度舍入、不重选分钟或报价。冻结的模型、单位、数值容差、官方参考准入、封口分钟选择及当前报价质量全部沿用 [mo-skew-25d-v1](contracts/analytics-skew.md)及其[机器策略](contracts/analytics-skew-v1.json)。特别是 PARTIAL 可以有合格 Skew；历史有效值或当前陈旧值可以保留数值，但不能因此成为当前有效判断。未选到分钟时不构造采样键。

这里新增的是通用投影，不新增 basis、return 或 ATM IV 定义。Skew 中的单合约求解结果、两翼 IV 和平价远期不自动成为独立 ATM IV 或 IM basis。basis 的现货输入尚无本次授权的正式来源；示例测试不得替代数据源及指标契约。envelope、错误与版本语义仍由 repository [Market Indicator Contract](../docs/contracts/indicators.md)拥有。

provider 回归必须验证与既有 Skew latest 在相同输入下数值、时间、状态、质量和证据一致，并覆盖缺参考、历史/休市、未封口、PARTIAL、陈旧、404/503、参数拒绝与生产拒绝 TEST DOUBLE；独立验证门槛与容差不放宽，沿用 [Skew v1 §8](contracts/analytics-skew.md#8-独立验证与收尾门槛)。未来 provider 必须先有明确指标定义和证据，再登记同一接口。
