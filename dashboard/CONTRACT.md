<a id="dashboard-read-contract"></a>
<a id="dashboard-session-contract"></a>
<a id="dashboard-skew-contract"></a>

# Dashboard presentation contract

本文件只拥有 React 页面如何呈现和清理已取得的业务/诊断结果。公共 HTTP 路径、参数、wire shape、状态和错误码仍以[共享 Read Path](../docs/contracts/read-path.md)为准；Calendar/Universe 协议见[共享 Market Session](../docs/contracts/market-session.md)，指标时间选择、质量、数值、series 及 reference 语义见 [Analytics Skew](../analytics/contracts/analytics-skew.md)与 [Reference adapter](../analytics/contracts/references.md)。页面不得改写这些语义。

## 汇报首页与轮询

- 首屏采用 MO Skew 汇报模式。页面从 coverage 中列出的 MO 月份显式选择 `month`，展示 latest 返回的对象、`skew_25d_vp`、`valuation_at`、`historical/current_usable`、`quality` 和 `reasons`；series 的 `baseline/change_vp/points` 用于当日变化和走势，minute 用于指定分钟回看。
- 当前水平、当日变化、数据时间和可信程度位于主要汇报区域；Collector / CTP / coverage / database / session 诊断保留在默认折叠的独立区域，不与 Skew 业务可用性合并为一个状态。
- 页面每 5 秒请求 Skew latest/series 与诊断资源，单次请求 4 秒超时；最后接收时间统一显示为北京时间。轮询和超时只影响展示状态，不改变 API 的评估时刻、分钟封口、quote age 或 current usability。
- Skew 与页面展示的翼 IV 保留两位小数。显示舍入不得反向参与插值、当日变化或其他计算；图表只对 API 数值做显示缩放，不在浏览器计算 IV、delta、forward 或 Skew。

## 当前、历史与失败状态

- 当前视图直接呈现 API 的 `historical`、`current_usable`、完整性和原因。数值存在但 `current_usable=false` 时仍可显示该封口分钟结果，但必须标为当前不可用/当前报价已陈旧，不得显示为实时有效；`PARTIAL` 不得被页面改写为完整。
- 历史表单以交易日和带时区整分钟调用 minute。历史结果明确标为历史，不复用当前日变化；切换 MO 月份时，基准与序列必须一起切换，不能混用上一月份的当日变化。
- 当日走势直接消费 series 的点序和逐点状态，只连接成功点；失败分钟不补点、不 forward-fill。无有效基准时变化保持空，不暗中使用昨日收盘。
- latest 请求失败同时清空当前值和旧序列；series 单独失败清空变化与走势，但可保留本次已经成功的 latest，并明确标注 series 失败。任何显示或计算错误都不得留下有效绿色标志。
- `SYNTHETIC` 参考包在首屏显式标记 `TEST DOUBLE`。测试数据不得呈现为真实市场证据。

## 诊断与市场时段

- 健康、coverage、日列表、summary/market-bars 和 sessions 各自失败时清除相应健康/新鲜证据；如保留旧数据，必须明确标为旧值，不能继续显示绿色成功。诊断失败不清除本次成功的 Skew 业务结果，Skew 失败也不把诊断状态改写为失败。
- 页面提供独立市场时段表，允许同时显示例如 CFFEX `CLOSED` 与 SHFE `OPEN`，且不重新解释 API 返回的 session 状态。sessions 请求失败时清空旧时段状态并显示未知，绝不改变 Collector 健康的定义。

## 边界

Dashboard 只通过同源 `/api/` 消费 JSON，不读取 Raw/SQLite，不生成合约、不求值、不选择替代分钟或参考包，也不持久化第二份事实或派生结果。部署、监听地址、代理和挂载属于[共享 Deployment Contract](../docs/contracts/deployment.md)；实际启动、构建与排障命令见[本级 README](README.md)。
