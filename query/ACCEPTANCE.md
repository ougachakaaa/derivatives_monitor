# Query 当前状态

行为见 [Contract](CONTRACT.md)、[Market Frame](contracts/market-frame.md)、[Skew](contracts/analytics-skew.md)和[参考适配](contracts/references.md)。系统门槛见[根状态矩阵](../docs/acceptance.md)。

<a id="query-feature-evidence"></a>

| 能力 | 当前状态 | 未验证事项 |
|---|---|---|
| Market Frame 与 Skew 数值核心 | 已实现；有固定独立 oracle 与 TEST DOUBLE 回归 | 已审核生产参考包、完整真实 MO 月链及至少十个真实时点对账 |
| Skew JSON 与参考适配 | 已实现当前、分钟和日序列、固定身份重放、参考准入与失败语义 | 真实业务闭环与性能 |
| Feature service / HTTP | 已实现通用 v1 envelope、显式注册表、mo-skew-25d-v1 provider 和只读 POST /api/features/evaluate；有投影等价与错误回归 | 真实 Feature 可用性；basis、return、ATM IV 尚未实现生产 provider |

工程回归只证明其 TEST DOUBLE 场景，不签收 G3/P1/P2。当前版本需要的回归按 [Repository Verification](../tests/README.md)执行，不从历史通过推断当前部署可用。
