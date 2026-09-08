# MVP 验收矩阵

状态基线：2026-09-08 文档整理。**MVP 未完成**。工程回归由 harness 生成当次结果；历史报告只是指定时间的证据，不能证明本版本/本机当前实盘状态。下面的“待验”不是测试通过。本轮已执行的离线/原生/浏览器/打包检查和完整 Docker 网络限制见[整理验收记录](archive/reorganization-20260908.md)。

| ID | 收尾门槛 | 现有证据/实现 | 还需取得的证据 |
|---|---|---|---|
| G1 | 固定环境连续 3 个完整交易日，AU/AG 真实跨午夜至日盘/新交易日 | [CFFEX 短时实连](archive/acceptance/CFFEX_Coverage_Acceptance_CN.md)、[SHFE 短时夜盘](archive/acceptance/Market_Session_SHFE_Acceptance_CN.md)；合成夜盘脚本 | 持久保存三日检查点、run/配置身份、接收/提交推进、断线说明、真实夜盘各边界；待验 |
| G2 | 数据质量诚实，历史与当前分开 | Collector/Query/Calendar/Market State 测试；Skew JSON 当前/分钟/日序列、质量/历史/失败缺口及参考拒绝已做 TEST DOUBLE 回归；浏览器断线恢复 | 真实完整 MO 月链的分钟质量及异常证据；业务 JSON 已实现，真实业务待验 |
| G3 | 一个 MO 月 Skew 闭环，10 时点独立对账和追溯 | [七项 Analytics 契约与数值核心](contracts/analytics-skew.md)、独立 oracle；审核包离线导入、当前/日序列/历史 JSON、输入哈希与固定 revision 回放已实现并做合成回归 | 取得并审核真实官方日参考包；按固定误差做至少10个真实时点独立对账（≥6可算、≥4异常）；JSON 切片已实现，G3仍待验 |
| G4 | 30 秒理解汇报首页，3 次日常使用无需 SQL/日志 | 当前是采集诊断看板；有 React/真实浏览器回归 | 汇报首页、当前指标/当日变化/分钟回看、三次使用记录；待实现 |
| G5 | 故障后恢复，保留已提交数据，备份恢复可读 | CTest、原生/容器独立停启/重启追加/心跳过期 | 本版本选择部署方式的回归；真实数据备份恢复的哈希/完整性/查询记录；现场待验 |
| G6 | 固定验收版本、可复现部署、说明完整、无阻断问题 | 原生/Docker 入口、锁文件、操作与契约已提供 | 对最终版本部署，保存构建/环境和结果，审核限制与阻断项；待验 |
| P1 | 真实一天库、完整目标链、单人核心查询 P95 ≤ 2 秒 | 既有 3 秒 SQL 预算是失败上限，不是性能证据 | 取得真实官方日包后，通过业务 API 记录≥100次业务查询耗时/错误、机器与库规模、冷热条件 |
| P2 | 活跃有效报价接收至页面显示目标 ≤ 30 秒 | 默认约15秒物化、5秒轮询、4秒前端请求超时 | 同一 observation 源/received/snapshot/显示时间配对；页面实测，待验 |

## 工程 harness 与门槛映射

| Harness 检查 | 覆盖 | 不能证明 |
|---|---|---|
| `docs` | 文档链接/长期入口、参考原件与 SDK 哈希、构建白名单必要输入 | 业务语义正确或实盘可用 |
| `analytics-contract` | 七项冻结状态、策略/oracle哈希、固定数值样本与独立float64对照；G3设计基线 | 生产行为、真实输入可用性或实盘对账 |
| `analytics` | 独立 contract 检查加生产核心、真实临时 SQLite→Market State→Analytics→Skew HTTP 的 TEST DOUBLE 回归；固定revision、哈希、质量/历史/缺口、离线包导入 | 真实官方日参考包、页面闭环或真实时点对账 |
| `offline` | 构建、7项 CTest、Query（含生产 Analytics 核心）、Universe、部署替身、SQLite CLI、React 测试与构建；G2/G5/G6 工程基础 | 真实网络/浏览器/容器、官方参考/实盘 Analytics、三日运行 |
| `native` | 合成 C++→SQLite→真实 HTTP、独立停启、SIGKILL 失效；合成夜盘分区；G2/G5 | 真实行情与真实跨午夜 |
| `browser` | 原生闭环加 Chromium 页面/网络恢复；G2/G4 的现有页面部分 | 汇报页的用户体验或真实接收延迟 |
| `packaging` | 实际 Docker scratch COPY、必要模块/日历/SDK 字节、运行目录排除；G6 打包边界 | runtime 镜像启动、实际挂载和生命周期 |
| `docker` | 两个隔离容器 smoke，镜像构建、RW/RO 挂载、恢复与持久化；G5/G6 | 真实 CTP、Windows 浏览器或三日运行 |

用法和依赖见[Harness](../harness/README.md)。每次运行产生 PASS/FAIL/NOT_RUN 和命令日志，任一未执行不计全通过。人工门槛永远不由 `offline` 成功自动关闭。

## 现场证据要求

真实验收使用[现场记录模板](../harness/live-acceptance-template.md)，在 `artifacts/acceptance/<date>-<revision>/` 等持久目录保存数据，不依赖 `/tmp`。提交的摘要必须指出原始证据路径、日期、版本、数据源、哈希以及是否仍可复查。原始账户配置不提交；脱敏配置记录采样参数、合约范围及非敏感环境信息。

冻结验收版本后：运行对应工程套件 → 三日业务使用和夜盘观察 → 指标独立对账 → 性能/恢复演练 → 逐项填写本矩阵并链接报告。失败记录原因及复验，不用更多测试数量抵消未完成门槛。改变生产代码、参数或数据来源后，评估哪些原结论失效并重验。

备份恢复演练只能在隔离恢复目录进行，具体步骤见[运行与恢复](operations.md)。测试可用合成数据验证机制，但 G5 的真实数据恢复仍须单独取得证据。


## Skew JSON 垂直切片工程证据（2026-09-08）

实现入口：[业务 API 契约](contracts/read-path.md)、[Query 用法与审核包导入](../query/README.md)。新业务测试为 `query/tests/test_skew_api.py`；真实临时 SQLite 与 FastAPI，报价/参考均为明确 TEST DOUBLE（官方格式导入用伪造原件只检验机制，不作为 OFFICIAL 实盘证据）。覆盖：

- 最新封口、首分钟等待、午休/竞价/次日历史归属、当前报价陈旧、指定分钟历史与未封口拒绝。
- 单日237个连续分钟及失败缺口、首有效基准/变化、逐帧同 revision；请求中迟到写入不混入，显式旧 revision/bundle 回放一致。
- 原文件哈希、官方来源归档校验、前一交易日/元数据不匹配拒绝、参考字节固定、生产拒绝 SYNTHETIC、离线导入不覆盖。
- HTTP 400/404/503、无 SQL/Raw字段投影、有限 JSON 数值；冻结 oracle 的 Black 时间缩放恒等式核对，容差未改变。

`python3 harness/run.py analytics` 最终代码工程结果：`artifacts/harness/20260908T113644Z-analytics-3e874a2f/result.json`，PASS，覆盖固定独立 oracle、16项生产核心和14项切片回归。完整 Query 回归命令 `cd query && .venv/bin/python -m unittest discover -s tests -v` 同版本76项通过。`packaging` 结果：`artifacts/harness/20260908T113722Z-packaging-e1ec0ecc/result.json`，PASS，仅证明真实 Docker scratch COPY 包含必要源码且排除运行数据，不代表 runtime 镜像或服务部署。报告保存当时工作树补丁及未跟踪源码哈希；报告后的文档更新仅登记这些结果，生产代码未变。

本轮范围为工程切片，暂不执行真实业务验收。G2/G3 **未签收**：本轮没有已审核生产日包、真实完整 MO 月分钟质量证据或10个真实时点独立对账。HTTP 工程切片可用不能替代这些证据；G4汇报页与P1/P2真实性能同样未完成。本轮未启动或重启真实服务。
