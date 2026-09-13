<a id="query-read-contract"></a>

# Query 组件契约

本文件定义 Query 的 HTTP 适配与当前 Market Indicator provider 规则。Raw read、Calendar、coverage 与 Market Frame 由 [Data Provider](../data_provider/CONTRACT.md)拥有；共享 HTTP 与 Market Indicator envelope 分别见 [Read Path](../docs/contracts/read-path.md)和 [Market Indicator](../docs/contracts/indicators.md)。

Query 将 Data Provider 的无效输入、缺失数据和不可用错误分别映射为 400、404、503，并保持公共 `{"error": ...}` wire。HTTP 参数、方法、JSON 和 no-store 由 Query 与共享 Read Path 拥有；Query 不解释 SQLite、Calendar、Market Frame 或 coverage 内部规则。

<a id="query-indicator-provider-contract"></a>

## Market Indicator provider

Query 使用显式的 `indicator_id → provider` 注册表。生产注册表只纳入已有指标契约的实现，TEST DOUBLE 仅通过测试注入，不提供生产绕过开关；不加载动态插件、DSL、通用计算图或后台指标任务。通用引擎不理解 provider 的金融字段。

`mo-skew-25d-v1` provider 复用 `SkewService.query('latest', month=显式月份, at=requested_at)` 的结果，不另建金融实现。它到通用 envelope 的映射如下：

| Market Indicator 字段 | 既有 Skew 结果来源 |
|---|---|
| `value / unit` | `skew_25d_vp / unit`（`vol_point`） |
| `scope / status / reasons` | 同名字段 |
| `effective_at / evaluated_at` | `valuation_at / evaluated_at` |
| `historical / current_usable` | 同名字段 |
| `sample_key` | 实际交易日、业务 scope 与封口分钟的确定性身份；不含 raw_revision、参考修订或请求时间 |
| `evidence` | 包括 algorithm、quality、raw_revision、Universe/Calendar/ReferenceBundle 身份和哈希、provenance 的完整公共结果 |

完整结果放入 `evidence`，通用字段直接投影，不重新计算、不按显示精度舍入、不重选分钟或报价。冻结的模型、单位、数值容差、官方参考准入、封口分钟选择及当前报价质量全部沿用 [mo-skew-25d-v1](../analytics/contracts/analytics-skew.md)及其[机器策略](../analytics/contracts/analytics-skew-v1.json)。特别是 PARTIAL 可以有合格 Skew；历史有效值或当前陈旧值可以保留数值，但不能因此成为当前有效判断。未选到分钟时不构造采样键。

这里新增的是通用投影，不新增 basis、return 或 ATM IV 定义。Skew 中的单合约求解结果、两翼 IV 和平价远期不自动成为独立 ATM IV 或 IM basis。basis 的现货输入尚无本次授权的正式来源；示例测试不得替代数据源及指标契约。envelope、错误与版本语义仍由 repository [Market Indicator Contract](../docs/contracts/indicators.md)拥有。

provider 回归必须验证与既有 Skew latest 在相同输入下数值、时间、状态、质量和证据一致，并覆盖缺参考、历史/休市、未封口、PARTIAL、陈旧、404/503、参数拒绝与生产拒绝 TEST DOUBLE；独立验证门槛与容差不放宽，沿用 [Skew v1 §8](../analytics/contracts/analytics-skew.md#8-独立验证与收尾门槛)。

未来 provider 必须先有明确指标定义和证据，再登记同一接口。rolling market window 的归属、输入选择、身份要求与写权边界唯一见 repository [Market Indicator Contract §4](../docs/contracts/indicators.md#4-rolling-window-与后续指标)。
