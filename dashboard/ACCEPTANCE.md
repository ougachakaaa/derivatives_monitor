# Dashboard 当前状态

页面行为见 [Contract](CONTRACT.md)，系统门槛见[根状态矩阵](../docs/acceptance.md)。

<a id="dashboard-presentation-evidence"></a>

| 能力 | 当前状态 | 未验证事项 |
|---|---|---|
| 汇报首页 | 已实现月份选择、当前值与变化、质量原因、指定分钟回看和折叠诊断 | 真实官方参考与完整 MO 月链上的三次日常使用、三十秒理解 |
| 轮询与失败处理 | 已实现超时、断线清值和诊断独立失效；有组件与浏览器 TEST DOUBLE 回归 | 独立真实四秒时钟的超时边界断言、真实接收至显示延迟 |

当前诊断 UI 仍适配旧行情事实路径与 Collector 诊断字段；`/api/market-bars`、schema v2 callback/Bar/partial/late 字段和 event-time provenance 尚未实现。旧浏览器回归不能证明新的诊断契约。

工程 TEST DOUBLE 不签收 G4/P2；当前版本浏览器和部署验证需按 [Repository Verification](../tests/README.md)实际执行。
