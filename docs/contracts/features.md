<a id="feature-shared-contract"></a>
<a id="query-feature-provider-contract"></a>

# Feature 查询契约 v1

状态：**FROZEN**，2026-09-09。本文定义共享 Feature 的语义、查询接口及失败边界；实现与验证状态唯一见 [Acceptance](../acceptance.md)。产品范围见 [MVP](../mvp.md)，物理归属与依赖见 [Architecture](../architecture.md)。

## 1. 语义与消费者边界

| 层次 | 输出与职责 | 不承担 |
|---|---|---|
| Market State | 已保存事实的 as-of/minute/latest 解释，含时间、session、quality、completeness、revision | 定价、金融指标、用户规则判断 |
| Feature / Indicator | 按版本化定义计算的描述性数值、单位、有效性和输入证据 | 用户阈值、crossing、机会生命周期 |
| Conclusion | 用户规则在一次 Evaluation 中得到的 MATCH / NOT_MATCH / UNKNOWN | 新市场事实、盈利保证 |
| Opportunity Event | 系统实际观察并提交的一次机会成立记录 | 可随行情修订重算覆盖的指标、通知成功证明 |

Market State 的精确行为沿用 [Market State Contract](market-state.md)。Feature 的公式、输入质量、时间选择、窗口和参考要求由对应指标 Contract 决定；通用层不把某个金融指标的规则推广为全部指标的默认口径。Conclusion 与 Event 属于 [Monitoring Contract](monitoring.md)。

Query 内部增加薄 Feature service 和简单的 `feature_id → provider` 注册表，复用既有业务 service。provider 不依赖 Monitoring；引擎不认识 provider 的金融字段。生产注册表只纳入已有指标契约的实现，TEST DOUBLE 通过测试注入，不增加生产绕过开关。无动态插件加载、DSL、通用计算图或后台指标调度器。

## 2. 只读 HTTP 接口

`POST /api/features/evaluate`：JSON body 承载一次、一个 Feature 的结构化查询；不写状态，不批量查询。沿用 Query 本地 HTTP 和 `Cache-Control: no-store` 边界。现有 Skew GET 接口保持兼容。

请求字段均必需：

| 字段 | v1 含义 |
|---|---|
| `schema_version` | 整数 `1` |
| `feature_id` | 指标定义的版本化 ID；首个生产 provider 为 `mo-skew-25d-v1` |
| `scope` | 指标接受的显式业务对象；Skew 为 `exchange=CFFEX, product=MO, month=YYMM` |
| `parameters` | 指标参数对象；Skew v1 为 `{}`，不开放冻结模型/质量参数覆盖 |
| `requested_at` | 带时区 ISO datetime；是显式评估时刻，不得偷偷替换为 provider 的当前时钟 |

不接受任意 SQL、文件路径、用户表达式或隐含选月。结构错误、未知字段/版本、未注册 Feature、错误 scope 或参数、无时区时间均返回 400；不以忽略参数实现兼容。Skew 历史固定 revision/bundle 的回放继续走已有 Skew 接口，本接口不另建历史查询体系。

响应为单一 Feature envelope：

| 字段 | 含义与不变量 |
|---|---|
| `schema_version, feature_id, parameters` | 通用协议版本及实际使用的指标定义/参数 |
| `scope` | 实际业务对象，包含实际逻辑交易日；未知项明确 null，不用当前自然日补齐 |
| `value, unit` | 完整精度的有限标量及契约单位；不可算为 null，不用 0、NaN/Inf 代替失败 |
| `status, reasons` | `OK / UNAVAILABLE` 与原因列表；OK 不意味着当前可用于 Monitoring |
| `effective_at` | 指标估值/采样生效时间，不能用请求或发送时间冒充；未能选择时为 null |
| `evaluated_at` | 本次请求的 `requested_at`；实际 HTTP 接收/完成时间不是这个字段 |
| `historical, current_usable` | provider 的历史及当前适用性判定；计算成功与当前可用分开 |
| `sample_key` | 同一逻辑采样位置的稳定、不透明字符串；位置未知为 null |
| `evidence` | provider 的完整公共业务结果，含算法身份、输入 revision、参考身份/哈希及 provenance；不输出私有路径或整张 Raw frame |

一个规则固定 Feature 定义、scope 和参数。该流内 `effective_at` 是采样的时间顺序，`sample_key` 用于同一位置相等判断，消费者不得解析键或以字符串排序推断时间。相同位置的 Raw/参考修订不改变键；修订身份属于 evidence。请求时钟也不进入键。首版 provider 每个有效时间位置只有一个样本；需要其他排序模型的未来 provider 必须先扩展契约，不能让引擎猜测。

UNAVAILABLE 仍保留已经知道的时间/身份/原因，未知身份保持 null 或空，不伪造证据。Raw 读取的 QueryError 404/503 原样保留；不把读库错误包装为正常不可算数值。provider 未预期异常通过 HTTP 失败暴露，不复用此前结果；Monitoring 按请求失败处理。

## 3. MO Skew provider 映射

复用 `SkewService.query('latest', month=显式月份, at=requested_at)`。完整结果放入 `evidence`；通用字段直接投影，不重新计算、不按显示精度舍入、不重选分钟或报价。

| Feature 字段 | 既有 Skew 结果来源 |
|---|---|
| `value / unit` | `skew_25d_vp / unit`（`vol_point`） |
| `scope / status / reasons` | 同名字段 |
| `effective_at / evaluated_at` | `valuation_at / evaluated_at` |
| `historical / current_usable` | 同名字段 |
| `sample_key` | 实际交易日、业务 scope 与封口分钟的确定性身份；不含 raw_revision、参考修订或请求时间 |
| `evidence` | 包括 algorithm、quality、raw_revision、Universe/Calendar/ReferenceBundle 身份和哈希、provenance 的完整公共结果 |

冻结的模型、单位、数值容差、官方参考准入、封口分钟选择及当前报价质量全部沿用 [mo-skew-25d-v1](analytics-skew.md)及其[机器策略](analytics-skew-v1.json)。特别是 PARTIAL 可以有合格 Skew；历史有效值或当前陈旧值可以保留数值，但不能因此成为当前有效判断。未选到分钟时不构造采样键。

这里新增的是通用投影，不新增 basis、return 或 ATM IV 定义。Skew 中的单合约求解结果、两翼 IV 和平价远期不自动成为独立 ATM IV 或 IM basis。basis 的现货输入尚无本次授权的正式来源；示例测试不得替代数据源及指标契约。

## 4. Rolling window 与后续指标

rolling market window 属于 Feature provider 的输入选择/计算状态，不属于 Rule Engine。未来收益率等指标通过 Market State 的显式历史读取形成窗口，不通过 Monitoring 轮询积累价格来定义市场窗口。

窗口必须由对应指标 Contract 冻结长度、采样时钟、session 边界、缺口、参考身份和读取一致性；同一 Raw 日内固定 revision，多输入的实际身份必须显式保留，不能假称跨库原子快照。当前不新增窗口库或通用窗口框架。需要缓存时保持可重建、可失效，不能获得 Market Facts 写所有权。

新 provider 需有明确指标定义及证据，再注册到同一接口；规则判断和通知不增加品种/指标分支。拆包条件属于 [Design](../design.md)，实现位置属于 [Architecture](../architecture.md)。拆分前后相同输入必须保持数值、时间、质量和追溯语义一致。

## 5. 验证与变更

验证新接口与已有 Skew latest 在相同输入下数值、时间、状态、质量和证据一致；覆盖缺参考、历史/休市、未封口、PARTIAL、陈旧、404/503、参数拒绝和生产拒绝 TEST DOUBLE。既有 Analytics 回归和 oracle 容差不得放宽。

新增指标可以增加 provider；改变已有指标业务含义必须遵守其版本规则。通用接口发生不兼容变更需新 schema_version，不能以迁移模块名静默改变业务含义。接口工程通过不代表实盘参考或数据已验收，当前证据见 [Acceptance](../acceptance.md)。
