<a id="indicator-shared-contract"></a>

# Market Indicator 查询契约 v1

状态：**FROZEN**，2026-09-13。本文定义共享 Market Indicator 的语义、查询接口及失败边界；实现与验证状态见 [Analytics Acceptance](../../analytics/ACCEPTANCE.md)与 [Query Acceptance](../../query/ACCEPTANCE.md#query-indicator-evidence)。产品范围见 [MVP](../mvp.md)，物理归属与依赖见 [Architecture](../../ARCHITECTURE.md)。

## 1. 语义边界

| 层次 | 输出与职责 | 不承担 |
|---|---|---|
| Market Frame | 已保存事实的 as-of/minute/latest 解释，含时间、session、quality、completeness、revision | 定价和金融指标 |
| Market Indicator | 按版本化定义计算的描述性数值、单位、有效性和输入证据 | 改写 Market Frame 或 Raw，以及定义特定消费者流程 |

Market Frame 的精确行为沿用 [Market Frame Contract](../../data_provider/contracts/market-frame.md)。Indicator 的公式、输入质量、时间选择、窗口和参考要求由对应指标 Contract 决定；通用层不把某个金融指标的口径推广为全部指标的默认口径。

Analytics 的注册表、provider 与内部依赖规则见 [Analytics Contract](../../analytics/CONTRACT.md#analytics-indicator-provider-contract)。

## 2. 只读 HTTP 接口

`POST /api/indicators/evaluate`：JSON body 承载一次、一个 Indicator 的结构化查询；不写状态，不批量查询。沿用 Query 本地 HTTP 和 `Cache-Control: no-store` 边界。现有 Skew GET 接口保持兼容。

请求字段均必需：

| 字段 | v1 含义 |
|---|---|
| `schema_version` | 整数 `1` |
| `indicator_id` | 指标定义的版本化 ID；首个生产 provider 为 `mo-skew-25d-v1` |
| `scope` | 指标接受的显式业务对象；Skew 为 `exchange=CFFEX, product=MO, month=YYMM` |
| `parameters` | 指标参数对象；Skew v1 为 `{}`，不开放冻结模型/质量参数覆盖 |
| `requested_at` | 带时区 ISO datetime；是显式评估时刻，不得偷偷替换为 provider 的当前时钟 |

不接受任意 SQL、文件路径、用户表达式或隐含选月。结构错误、未知字段/版本、未注册 Indicator、错误 scope 或参数、无时区时间均返回 400；不以忽略参数实现兼容。Skew 历史固定 revision/bundle 的回放继续走已有 Skew 接口，本接口不另建历史查询体系。

响应为单一 Indicator envelope：

| 字段 | 含义与不变量 |
|---|---|
| `schema_version, indicator_id, parameters` | 通用协议版本及实际使用的指标定义/参数 |
| `scope` | 实际业务对象，包含实际逻辑交易日；未知项明确 null，不用当前自然日补齐 |
| `value, unit` | 完整精度的有限标量及契约单位；不可算为 null，不用 0、NaN/Inf 代替失败 |
| `status, reasons` | `OK / UNAVAILABLE` 与原因列表；计算成功与当前可用性分开 |
| `effective_at` | 指标估值/采样生效时间，不能用请求或发送时间冒充；未能选择时为 null |
| `evaluated_at` | 本次请求的 `requested_at`；实际 HTTP 接收/完成时间不是这个字段 |
| `historical, current_usable` | provider 的历史及当前适用性判定；计算成功与当前可用分开 |
| `sample_key` | 同一逻辑采样位置的稳定、不透明字符串；位置未知为 null |
| `evidence` | provider 的完整公共业务结果，含算法身份、输入 revision、参考身份/哈希及 provenance；不输出私有路径或整张 Raw frame |

该流内 `effective_at` 是采样的时间顺序，`sample_key` 用于同一位置相等判断，不得解析键或以字符串排序推断时间。相同位置的 Raw/参考修订不改变键；修订身份属于 evidence。请求时钟也不进入键。当前 provider 每个有效时间位置只有一个样本；需要其他排序模型的 provider 必须先扩展契约。

UNAVAILABLE 仍保留已经知道的时间/身份/原因，未知身份保持 null 或空，不伪造证据。Raw 读取的 Data Provider not-found/unavailable 错误由 Query 映射为 404/503；不把读库错误包装为正常不可算数值。provider 未预期异常通过 HTTP 失败暴露，不复用此前结果。

## 3. MO Skew provider 映射

首个生产 provider 为 `mo-skew-25d-v1`；其字段映射、采样键身份与投影边界属于 provider 级细节，唯一见 [Analytics Contract](../../analytics/CONTRACT.md#analytics-indicator-provider-contract)。本文只冻结通用 envelope、消费者边界与错误/版本规则。

## 4. Rolling window 与后续指标

需要 rolling market window 的 Indicator provider 通过 Market Frame 的显式历史读取形成输入窗口，窗口选择和计算语义由 provider 所属指标 Contract 负责。

窗口必须由对应指标 Contract 冻结长度、采样时钟、session 边界、缺口、参考身份和读取一致性；同一 Raw 日内固定 revision，多输入的实际身份必须显式保留，不能假称跨库原子快照。当前不新增窗口库或通用窗口框架。需要缓存时保持可重建、可失效，不能获得 Market Facts 写所有权。

新 provider 需有明确指标定义及证据；注册要求见 [Analytics Contract](../../analytics/CONTRACT.md#analytics-indicator-provider-contract)。模块演进原则属于 [Design](../../DESIGN.md)，实现位置属于 [Architecture](../../ARCHITECTURE.md)。调整边界前后相同输入必须保持数值、时间、质量和追溯语义一致。

## 5. 兼容与变更

新增指标可以增加 provider；改变已有指标业务含义必须遵守其版本规则。通用接口发生不兼容变更需新 schema_version，不能以迁移模块名静默改变业务含义。provider 的等价性、回归覆盖与容差要求见 [Analytics Contract](../../analytics/CONTRACT.md#analytics-indicator-provider-contract)；接口工程通过不代表实盘参考或数据已验收，当前证据见 [Analytics Acceptance](../../analytics/ACCEPTANCE.md)与 [Query Acceptance](../../query/ACCEPTANCE.md#query-indicator-evidence)。
