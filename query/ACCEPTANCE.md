# Query 当前状态

HTTP 行为见 [Contract](CONTRACT.md)和 [Read Path](../docs/contracts/read-path.md)；数据与指标行为分别见 [Data Provider](../data_provider/CONTRACT.md)和 [Analytics](../analytics/ACCEPTANCE.md)。系统门槛见[根状态矩阵](../docs/acceptance.md)。

<a id="query-indicator-evidence"></a>

| 能力 | 当前状态 | 未验证事项 |
|---|---|---|
| Skew HTTP adapter | 已实现当前、分钟和日序列的参数适配、wire 与错误映射 | 真实业务闭环与性能；业务证据见 Analytics Acceptance |
| Market Indicator HTTP adapter | 已实现严格 JSON/content-type、只读 POST `/api/indicators/evaluate`、异常映射与 no-store；有 composition/error 回归 | 真实 Market Indicator 可用性；业务证据见 Analytics Acceptance |

工程回归只证明其 TEST DOUBLE 场景，不签收 G3/P1/P2。当前版本需要的回归按 [Repository Verification](../tests/README.md)执行，不从历史通过推断当前部署可用。
