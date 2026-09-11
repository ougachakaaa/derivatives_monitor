# Dashboard Acceptance

本文件只记录 Dashboard 当前实现、工程证据与局部缺口；页面规范见[本级 Contract](CONTRACT.md)，系统 G1–G6/P1/P2 门槛仍由[根 Acceptance](../docs/acceptance.md)拥有。历史 PASS 只证明指定版本和环境中的 TEST DOUBLE 场景，不证明当前版本、真实 Skew 或人工可用性。

## 当前实现与覆盖缺口

当前 `src/App.jsx` 实现汇报首页、默认 5 秒轮询、4 秒 abort、两位 Skew/变化显示、当前与指定分钟视图、折叠诊断及独立失败清值；日期时间 formatter 也固定使用 Asia/Shanghai。组件测试可缩短轮询并覆盖主要状态，但没有单独以真实 4 秒时钟断言超时边界；返回当前视图控件、除最后接收时间外的具体时区格式、具体中文标签和诊断表列属于当前代码证据，既有规范未把这些细节冻结为独立业务 Contract。

<a id="dashboard-presentation-evidence"></a>

## 汇报首页工程证据（2026-09-09）

React 组件 7 项通过，覆盖当前 Skew、当日变化、完整性与 TEST DOUBLE 标记、PARTIAL、STALE、UNAVAILABLE、指定分钟回看、Skew API 断线清值/恢复以及诊断独立失效；`npm run build` 通过。`browser` 结果为 `artifacts/harness/20260909T005859Z-browser-2446e812/result.json`（PASS），在实际 Chromium 中覆盖同样的 Skew TEST DOUBLE 状态、移动端无整页溢出，并保留真实临时 C++ → SQLite → FastAPI 诊断路径。`packaging` 结果为 `artifacts/harness/20260909T005808Z-packaging-957813a7/result.json`（PASS），证明 Dashboard 生产构建输入仍符合镜像 allowlist。

这些数值和参考均为 TEST DOUBLE，没有已审核的真实官方日包、真实完整 MO 月链或人工日常使用记录。因此本节只表明汇报页工程行为可回归，**不签收 G4**。

## 待验

- 在已审核真实日参考包与完整 MO 月链上完成 3 次日常观察，记录是否能在 30 秒内理解对象、水平、变化、时间与可信程度，且无需 SQL/日志；此前未取得该证据。
- 页面接收至显示的真实延迟仍须按根 P2 配对 observation 源、received、snapshot 和显示时间；默认轮询/超时配置本身不是性能证据。
- 当前 S5 只迁移 authority，不运行 browser、packaging、Docker 或真实服务；本版本的结构验证不覆盖上述历史报告。

## S5 迁移时局部复核（2026-09-11）

在 `main@414e043` 加 S5 文档工作树上，`npm test` 实际执行 7 项组件测试并全部通过，`npm run build` 成功构建 24 个模块。此轮没有修改 `src/`、样式、测试、package manifest 或 lockfile；结果只确认现有前端仍可测试和构建，不是新的 browser/packaging/实盘证据，也不签收 G4/P2。4 秒超时仍缺单独的真实时钟组件断言。
