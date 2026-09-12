# MVP 验收矩阵

本文件只记录当前实现、验证证据和待补缺口；产品收尾条件由 [MVP](mvp.md)定义，设计与精确行为分别以 [Design](../DESIGN.md)、[Architecture](../ARCHITECTURE.md)和 [Contracts](contracts/) 为准。本矩阵中的门槛摘要用于映射证据，不创建新的设计要求。

状态基线：工程与现场交付状态为 2026-09-10 developer runner 审计；文档 authority 拓扑迁移已于 2026-09-11 完成，见[迁移完成状态](#documentation-authority-topology)。**MVP 未完成**。工程回归由 harness 生成当次结果；历史报告只是指定时间的证据，不能证明本版本/本机当前实盘状态。下面的“待验”不是测试通过。此前的离线/原生/浏览器/打包检查和完整 Docker 网络限制见[整理验收记录](archive/reorganization-20260908.md)。

| ID | 收尾门槛 | 现有证据/实现 | 还需取得的证据 |
|---|---|---|---|
| G1 | 固定环境连续 3 个完整交易日，AU/AG 真实跨午夜至日盘/新交易日 | [CFFEX 短时实连](archive/acceptance/CFFEX_Coverage_Acceptance_CN.md)、[SHFE 短时夜盘](archive/acceptance/Market_Session_SHFE_Acceptance_CN.md)；合成夜盘脚本 | 持久保存三日检查点、run/配置身份、接收/提交推进、断线说明、真实夜盘各边界；待验 |
| G2 | 数据质量诚实，历史与当前分开 | Collector/Query/Calendar/Market State 测试；Skew JSON 当前/分钟/日序列、质量/历史/失败缺口及参考拒绝已做 TEST DOUBLE 回归；浏览器断线恢复 | 真实完整 MO 月链的分钟质量及异常证据；业务 JSON 已实现，真实业务待验 |
| G3 | 一个 MO 月 Skew 闭环，10 时点独立对账和追溯 | [七项 Analytics 契约与数值核心](../query/contracts/analytics-skew.md)、独立 oracle；Query 局部工程证据见 [Query Acceptance](../query/ACCEPTANCE.md) | 取得并审核真实官方日参考包；按固定误差做至少10个真实时点独立对账（≥6可算、≥4异常）；JSON 切片已实现，G3仍待验 |
| G4 | 30 秒理解汇报首页，3 次日常使用无需 SQL/日志 | React 汇报首页已实现月份选择、当前值/当日变化/时间/质量/原因、指定分钟回看和折叠诊断；局部 TEST DOUBLE 证据见 [Dashboard Acceptance](../dashboard/ACCEPTANCE.md) | 在已审核真实日包与完整 MO 月链上取得3次日常使用记录，实测30秒理解与无需 SQL/日志；待验 |
| G5 | 故障后恢复，保留已提交数据，备份恢复可读 | CTest、原生/容器独立停启/重启追加/心跳过期 | 本版本选择部署方式的回归；真实数据备份恢复的哈希/完整性/查询记录；现场待验 |
| G6 | 固定验收版本、可复现部署、说明完整、无阻断问题 | 原生/Docker 入口、锁文件、操作与契约已提供 | 对最终版本部署，保存构建/环境和结果，审核限制与阻断项；待验 |
| P1 | 真实一天库、完整目标链、单人核心查询 P95 ≤ 2 秒 | 既有 3 秒 SQL 预算是失败上限，不是性能证据 | 取得真实官方日包后，通过业务 API 记录≥100次业务查询耗时/错误、机器与库规模、冷热条件 |
| P2 | 活跃有效报价接收至页面显示目标 ≤ 30 秒 | 默认约15秒物化、5秒轮询、4秒前端请求超时 | 同一 observation 源/received/snapshot/显示时间配对；页面实测，待验 |

## Monitoring v1 平行扩展状态

Monitoring 的实现、工程证据与 M2–M5 缺口只见 [Monitoring Acceptance](../monitoring/ACCEPTANCE.md)；Feature provider/HTTP 证据仍见 [Query Acceptance](../query/ACCEPTANCE.md#query-feature-evidence)，实施交接见 [Monitoring execution plan](monitoring-execution-plan.md)。该平行扩展不增加或替代本文件的 G1–G6/P1/P2，工程 TEST DOUBLE 或通知闭环也不能签收主线门槛。

## 本地开发入口交付状态

2026-09-10：从 Git 和当前代码复核 `94ed099`（范围与契约准备）、`c4501e7`（可选行情账号回归）及 `fd8ba28`（启动命令分组）。根 `./dev` 已实现 `doctor [component]`、`up [component]`、参数边界及前台监督；不带组件的 `up` 联合启动三个组件，单组件启动统一为 `up collector/query/dashboard`，退役的顶层组件命令返回 2、给出迁移提示且不启动。长期要求见 [Deployment Contract](contracts/deployment.md#developer-runner-的生命周期边界)，实际命令见 [Operations](operations.md#前台开发会话)。任务 A 的真实 Collector 配置校验与 doctor TEST DOUBLE 回归覆盖账号字段缺省、空值、正常已填、分别过长、整体失败脱敏和无持久写入；任务 B 的 32 项 runner 回归覆盖新 help、参数位置/适用范围、旧入口零分派、单组件/联合分派及既有监督器边界。

2026-09-10 的 `python3 harness/run.py offline` 为 PASS（14 步均实际执行），基线为 `c4501e7` 加工作树补丁（该补丁对应 `c4501e7..fd8ba28` 的 Git binary diff）。该次运行通过 docs、harness-tests、configure/build、7 项 CTest、显式 credentials/CLI 语义、32 项 runner tests、实际 runner smoke、76 项 Query、Universe、deploy、verify、React 和 frontend-build。实际 smoke 只使用临时配置/data/flow、随机 loopback 端口和 TEST DOUBLE SDK，经过 Collector → SQLite → Uvicorn → Vite，验证共享 Raw、Dashboard 代理、下游隔离、writer/端口冲突、会话清理及重启保留追加。

这些证据不包含真实 CTP/行情、真实配置写入、现场恢复、当前版本浏览器或 Docker runtime，也不改变 native/Docker 行为。账号空值被本地接受不证明真实前置允许匿名接入；进程与 HTTP 工程闭环不证明行情推进或业务就绪。本轮不签收 G1–G6，TEST DOUBLE 和监督测试不能替代三日行情、真实恢复及最终部署验收。

## 工程 harness 与门槛映射

| Harness 检查 | 覆盖 | 不能证明 |
|---|---|---|
| `docs` | 文档链接/authority 入口、正式构建与运行依赖方向、参考原件与 SDK 哈希、构建白名单必要输入 | 业务语义正确、实现状态措辞或实盘可用 |
| `analytics-contract` | 七项冻结状态、策略/oracle哈希、固定数值样本与独立float64对照；G3设计基线 | 生产行为、真实输入可用性或实盘对账 |
| `analytics` | 独立 contract 检查加生产核心、真实临时 SQLite→Market State→Analytics→Skew HTTP 的 TEST DOUBLE 回归；固定revision、哈希、质量/历史/缺口、离线包导入 | 真实官方日参考包、页面闭环或真实时点对账 |
| `offline` | 构建、7项 CTest、developer runner 显式 CLI/凭据语义、隔离测试与实际 `./dev` TEST DOUBLE Collector→SQLite→Uvicorn→Vite 生命周期、Query（含生产 Analytics 核心）、Universe、部署替身、SQLite CLI、React 测试与构建；G2/G5/G6 工程基础 | 真实网络/浏览器/容器、官方参考/实盘 Analytics、三日运行 |
| `native` | 合成 C++→SQLite→真实 HTTP、独立停启、SIGKILL 失效；合成夜盘分区；G2/G5 | 真实行情与真实跨午夜 |
| `browser` | 原生诊断闭环加 Chromium；Skew TEST DOUBLE 覆盖当前/变化/历史/PARTIAL/STALE/UNAVAILABLE/API断线与移动布局 | 真实 Skew 业务值、30秒理解、3次日常使用或真实接收延迟 |
| `packaging` | 三个 Dockerfile-specific allowlist 的实际 scratch context、各镜像精确输入集合及必要模块/日历/SDK 字节；G6 打包边界 | runtime 镜像启动、实际挂载和生命周期 |
| `docker` | 仓库级部署边界、根 Compose 的三服务构建与隔离 smoke、RW/RO 挂载、恢复与持久化；G5/G6 | 真实 CTP、Windows 浏览器或三日运行 |

用法和依赖见 [Harness README](../harness/README.md)，PASS/FAIL/NOT_RUN、证据身份与自动结果边界见 [Harness Contract](../harness/CONTRACT.md)。人工门槛永远不由 `offline` 成功自动关闭。

## 现场证据要求

真实验收使用[现场记录模板](../harness/live-acceptance-template.md)，在 `artifacts/acceptance/<date>-<revision>/` 等持久目录保存数据，不依赖 `/tmp`。提交的摘要必须指出原始证据路径、日期、版本、数据源、哈希以及是否仍可复查。原始账户配置不提交；脱敏配置记录采样参数、合约范围及非敏感环境信息。

冻结验收版本后：运行对应工程套件 → 三日业务使用和夜盘观察 → 指标独立对账 → 性能/恢复演练 → 逐项填写本矩阵并链接报告。失败记录原因及复验，不用更多测试数量抵消未完成门槛。改变生产代码、参数或数据来源后，评估哪些原结论失效并重验。

备份恢复演练只能在隔离恢复目录进行，具体步骤见[运行与恢复](operations.md)。测试可用合成数据验证机制，但 G5 的真实数据恢复仍须单独取得证据。


Query 的数值核心、Skew JSON、reference adapter、Feature provider/HTTP 与参考路径修复工程记录已迁至 [Query Acceptance](../query/ACCEPTANCE.md)；汇报首页的 React/浏览器/打包记录已迁至 [Dashboard Acceptance](../dashboard/ACCEPTANCE.md)。根矩阵只据此映射 G2/G3/G4/P1/P2，并继续保留真实官方包、完整 MO 月链、10 时点独立对账、三次日常使用和性能证据缺口。


<a id="documentation-authority-topology"></a>

## 文档 authority 拓扑：迁移完成状态

2026-09-11 完成 repository semantic embedding 迁移（M0 freeze 与 S1–S8）：现行文档拓扑见 [Architecture](../ARCHITECTURE.md#knowledge-topology)，治理规则见[文档入口](README.md#authority-rules)，机器可读关系从根 [`.authority.json`](../.authority.json) 开始。root、collector、collector/scripts、query、query/calendars、dashboard、monitoring 与 harness 八个受管理 scope 均为 `existing`；每个 claim 只在受约束 scopes 的 smallest common scope 定义一处，旧中央副本已退役并列入负向检查。

离线检查（`harness/check_docs.py`、`harness/authority.py`）拒绝 pending scope、entrypoint/claim migration metadata、未登记的 authority-shaped 文档、重复规范段落、未登记跨 scope 依赖及已退役中央路径。迁移完成时 `python3 harness/run.py docs` 与完整 `harness/tests` 在实施工作树上实际执行通过；该结构证据不证明自然语言语义等价、业务实现或现场验收。

各阶段的一次性过程记录（M0 semantic freeze、S1 scope 登记、S2 根 authority、S3 Collector/tools、S4 Query/Market/Analytics、S5 Dashboard、S6 Monitoring、S7 Harness、S8 最终拓扑）已从本文件移除，只从 Git 追溯；本文件不再保留其逐阶段证据路径与当时工作树状态。迁移只涉及文档、authority 登记与离线检查，未修改生产代码、Skew 策略/oracle/fixtures、SDK、参考原件、Docker 输入或 experiments，也不改变本文件的 G1–G6/P1/P2 或任何模块业务状态。
