# MVP 验收矩阵

本文件只记录当前实现、验证证据和待补缺口；产品收尾条件由 [MVP](mvp.md)定义，设计与精确行为分别以 [Design](../DESIGN.md)、[Architecture](../ARCHITECTURE.md)和 [Contracts](contracts/) 为准。本矩阵中的门槛摘要用于映射证据，不创建新的设计要求。

状态基线：2026-09-10 developer runner 工程交付审计。**MVP 未完成**。工程回归由 harness 生成当次结果；历史报告只是指定时间的证据，不能证明本版本/本机当前实盘状态。下面的“待验”不是测试通过。此前的离线/原生/浏览器/打包检查和完整 Docker 网络限制见[整理验收记录](archive/reorganization-20260908.md)。

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

`python3 harness/run.py offline` 报告为 `artifacts/harness/20260910T063104Z-offline-c6268769/result.json`（PASS，14 步均实际执行）。报告基线 revision 为 `c4501e7`，记录的工作树补丁 SHA-256 `40ac99918056b21e2cc5257baf3534b1a4a2cb68aba6fafdac359af53913be83` 与 `c4501e7..fd8ba28` 的 Git binary diff 一致。该次运行通过 docs、harness-tests、configure/build、7 项 CTest、显式 credentials/CLI 语义、32 项 runner tests、实际 runner smoke、76 项 Query、Universe、deploy、verify、React 和 frontend-build。实际 smoke 只使用临时配置/data/flow、随机 loopback 端口和 TEST DOUBLE SDK，经过 Collector → SQLite → Uvicorn → Vite，验证共享 Raw、Dashboard 代理、下游隔离、writer/端口冲突、会话清理及重启保留追加。

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


<a id="semantic-freeze"></a>

## Repository semantic embedding：semantic freeze / M0

2026-09-10，实施前复核 `main@351003e` 与同 HEAD 的 monitoring worktree，工作树干净。本阶段只冻结[治理规则](README.md#authority-rules)、[目标 topology / mapping](../ARCHITECTURE.md#knowledge-topology)和[迁移 ExecPlan](semantic-embedding-execplan.md)；对应原迁移计划 S0，与 Monitoring 业务 M0 不同。

现有中央业务 Contracts 仍为当前定义，目标模块文档尚未迁移。S1–S8（scope 检查器、根/模块迁移、最终强制治理）均未执行；生产代码、业务 Contract、策略、oracle、实验、SDK 和原件保持不变。新 checks 尚未实现，不把 docs PASS 作为 scope/唯一性自动验证或 MVP 通过。

文档检查 `python3 harness/run.py docs` 为 PASS，报告 `artifacts/harness/20260910T154722Z-docs-5407522d/result.json`，记录 `351003e` 加 freeze 工作树；报告后的修改仅收紧导航/排版与登记证据。`python3 -m unittest discover -s harness/tests -p test_docs.py -v` 实际执行 3 项，全部通过；`git diff --check` 通过。对本次七个 Markdown 文件逐一离线检查本地链接及显式/标题锚点，并人工核对治理只在 docs README 定义、归属只在 Architecture 定义、执行步骤只在 ExecPlan，目标路径不冒充现存 authority。提交前再次执行 docs/diff 检查。

范围审查只包含这七份文档；与 `351003e` 比较业务 Contracts、生产代码、oracle/fixtures、实验和参考原件无 diff。未运行 analytics/offline/native/browser/packaging/docker，不改变上文 G1–G6/P1/P2、Feature 或 Monitoring 的业务证据状态。M0 交付在本节所属独立 commit 中结束，S1–S8 留待新 session 明确授权。

<a id="semantic-authority-m1"></a>

## Repository semantic embedding：scoped authority validation / M1（S1）

2026-09-11，从 `main@e67a9b0` 的干净工作树恢复并核对另一 worktree 仍为 `feature/realtime-monitoring-alerts@351003e`。本阶段只实现 S1：为现有 repository、Collector、Collector tools、Query、Calendar reference、Dashboard 与 Harness scope 建立 version 1 关系登记；尚无目录的 Monitoring 仅在父登记标为 `frozen_pending`。现行中央业务定义未迁移，所有局部目标均以具名 exception 记录当前路径、目标路径、目标 scope 和 S2–S7 退出阶段。

离线检查现验证登记版本、scope 树与 smallest-common-scope、入口可达、文档角色、显式锚点、claim 唯一定义/引用、证据与计划不得定义 authority、精确重复规范段落、具名迁移例外，以及 Python/include/build 输入的跨 scope 依赖；保留现有原件/SDK 哈希、正式 runtime 不依赖 experiments 和 Docker 白名单检查。15 项临时 TEST DOUBLE 仓库自测覆盖正向继承、跨平台路径及上述主要负向边界，并已加入 `docs` profile。

本阶段只修改机器导航、离线 Harness、导航/状态说明并为现行定义增加不改变正文的显式锚点。未移动或改写 Contract 规则，未修改生产代码、Skew 策略、golden/oracle、参考原件、SDK 或 experiments；M2/S2 及后续迁移未执行。自动 PASS 只证明登记与确定性结构约束，不证明自然语言语义等价、业务实现或现场验收。

`python3 harness/run.py docs` 为 PASS，报告 `artifacts/harness/20260910T161215Z-docs-cbb04f60/result.json` 记录 `e67a9b0` 加 S1 工作树，两个步骤均实际执行；报告后的修改仅登记本证据。完整 `harness/tests` 共 29 项及 `git diff --check` 在提交前另行通过。

<a id="semantic-authority-s2"></a>

## Repository semantic embedding：repository scope authorities / S2

2026-09-11，从干净的 `main@6994059` 恢复并核对 S1 登记、检查器和 15 项专项测试均已提交。本阶段将 repository-level Design/Architecture 从 `docs/` 原子迁至根 `DESIGN.md` / `ARCHITECTURE.md`，并删除旧地址；共享 Raw 所有权、writer 协调、WAL/只读和 Collector 诊断协议迁至 `docs/contracts/raw-boundary.md`。Collector、Read Path 与 Deployment 的原重复定义已改为指向共享 Contract，根与模块入口同步切换。

尚待 S4/S6 下放的 Query/Monitoring 局部 Design/Architecture 段落仍只存在于根文件，并在登记中以具名 exception 保留原退出阶段；没有创建未来局部副本。Feature endpoint 的行为定义未改，Read Path 只移除可变的“待实现”判断并导航本 Acceptance。Architecture 现明确 C++ Collector runtime 不依赖 Query，而 Universe/native 属于工具或 repository integration 职责；允许的实际依赖仍由登记约束。

本阶段未修改生产代码、业务数值、Skew 策略、golden/oracle、参考原件、SDK 或 experiments，也未执行 S3。结构检查只证明迁移路径、链接/锚点、claim/scope、依赖和受保护输入，不提升任何业务或现场验收状态。

`python3 harness/run.py docs` 为 PASS，报告 `artifacts/harness/20260911T003901Z-docs-006eb907/result.json` 记录 `6994059` 加 S2 工作树，docs 与 authority 自测两个步骤均实际执行。完整 `harness/tests` 共 30 项通过，`git diff --check` 通过；报告后的修改仅登记本证据。提交前再次直接执行结构检查与 diff 检查。

<a id="semantic-authority-s3"></a>

## Repository semantic embedding：Collector / tools authority / S3

2026-09-11，从干净的 `main@c15b229` 恢复并核对 S1/S2 的登记、迁移和提交。本阶段建立 Collector 的 AGENTS/README/ARCHITECTURE/CONTRACT 导航，以及 `collector/scripts/` 的 AGENTS/README/CONTRACT 工具入口；Collector runtime、Collector 自身 lifecycle 和 Universe tool claims 已退出三个 S3 migration exceptions，旧中央 Collector Contract 被删除并列入退役路径检查。

Collector callback、配置、采样、session、提交与正常停止语义只迁址、不重新设计；共享 Raw owner/锁/WAL/诊断继续留根。Universe 的来源抓取、校验、保留和发布行为下沉到工具 scope，Calendar/Universe 跨模块交接继续留根；C++ runtime 不依赖 Query，只有既有 `universe.py` → `query/market_calendar.py` 工具边。三服务 native/Docker 教程归根 Operations，repository deployment lifecycle 未下沉。

本阶段只修改文档、authority registration 和相应 Harness 文档路径检查；没有移动或修改 `native.py`、`universe.py` 或其他生产代码，没有读取配置/Raw、运行真实服务或执行 S4。结构检查证明路径、锚点、claim/scope、依赖和受保护输入，不提升业务或现场验收状态。

<a id="semantic-authority-s4"></a>

## Repository semantic embedding：Query / Market / Analytics authority / S4

2026-09-11，从干净的 `main@8008722` 恢复并核对 S1–S3 提交与登记。本阶段只执行 S4：Query guidance、Design、Architecture、组件 Contract、领域 Contracts 与局部 Acceptance 已落位；Market State、Skew、机器策略、ReferenceBundle adapter 和来源说明迁入 Query。共享 HTTP、Feature、Raw、Calendar/Universe protocol 继续位于 repository scope，Dashboard 专属规则及 S5 例外未执行。

冻结策略按字节迁移，SHA-256 保持 `d520d8a2831f81df1372efe280898e2e682f5e039669488417c1f4fe7ec56f14`。oracle 只更新策略路径，fixture 只更新相应 `generator_sha256` provenance；新增忽略该 provenance 后的整份固定基线检查，未重新生成 expected，也未修改 vectors、chains、数学、参数或容差。旧中央 Query authority 路径已纳入退役检查，S4 migration exceptions 已退出。

`python3 harness/run.py analytics` 为 PASS，报告 `artifacts/harness/20260911T031153Z-analytics-a75593bc/result.json`，其中 docs、32 项 harness tests、analytics-contract 与 production Analytics 均实际执行通过。固定环境 `artifacts/analytics-oracle-env` 使用 QuantLib 1.40 / mpmath 1.3.0 独立比较 12 个价格向量、2 条 tick-rounded chains 和插值例，退出码 0。最终 docs profile 为 PASS，报告 `artifacts/harness/20260911T031326Z-docs-3415e4cb/result.json`，docs 与 authority 自测均实际执行。迁移不读取真实配置/Raw、不运行服务、不改变生产行为，也不执行 S5；这些工程结果不提升 G1–G6/P1/P2。

`python3 harness/run.py docs` 为 PASS，报告 `artifacts/harness/20260911T010603Z-docs-d7abef93/result.json` 记录 `c15b229` 加 S3 工作树，docs 与 authority 自测两个步骤均实际执行；完整 `harness/tests` 共 31 项通过，`git diff --check` 通过。报告后的修改仅登记本证据；提交前再次执行结构与 diff 检查。

<a id="semantic-authority-s5"></a>

## Repository semantic embedding：Dashboard authority / S5

2026-09-11，从干净的 `main@414e043` 恢复并核对 S1–S4 提交与登记。本阶段只执行 S5：Dashboard guidance、页面 Contract、局部 Acceptance 与 authority registration 已落位；页面布局、5 秒轮询、4 秒请求超时、失败清值、两位显示精度、当前/历史交互和独立市场时段表归入 Dashboard。公共 HTTP/wire shape、Feature 与 Calendar/Universe 协议继续位于 repository scope，Market State、Skew/Analytics、solver 和 reference semantics 继续属于 Query。

Read Path、Market Session 与 Query Skew 中的页面重复定义已改为链接，三个 S5 migration exceptions 已退出；历史汇报首页证据原样迁入 [Dashboard Acceptance](../dashboard/ACCEPTANCE.md#dashboard-presentation-evidence)，根只保留 G4/P2 与本阶段迁移映射。仅由 React 代码体现而无既有规范来源的控件、文案和表列细节仍作为局部 evidence/gap，没有提升为业务 Contract。

本阶段没有修改生产 React、样式、测试或 Query 生产行为，也没有改动 Skew 策略、golden/oracle、原件、SDK 或 experiments；没有读取真实配置/Raw、运行服务或执行 S6。`python3 harness/run.py docs` 为 PASS，报告 `artifacts/harness/20260911T032509Z-docs-f11ea30c/result.json`，docs 与 authority 自测均实际执行；完整 `harness/tests` 32 项通过。Dashboard 的 7 项组件测试与生产构建通过，局部边界见 [Dashboard Acceptance](../dashboard/ACCEPTANCE.md)。报告后的修改只登记这些证据；结构与前端工程结果不提升 G1–G6/P1/P2。

<a id="semantic-authority-s6"></a>

## Repository semantic embedding：Monitoring frozen authority / S6

2026-09-11，从干净的 `main@8a1550a` 恢复并核对 S1–S5 提交与登记。本阶段只执行 S6：建立非空 [Monitoring scope](../monitoring/README.md)，将内部 Design、Architecture、Rule/Evaluation/crossing/UNKNOWN、配置、application state、Opportunity Event、原子事务、恢复和 delivery/retry authority 迁入本级文档；四个 S6 migration exceptions 已退出，旧中央 Monitoring Contract 已退役。

共享 Feature protocol、Raw/Market Facts ownership、Monitoring↔Query access、system lifecycle 和永久不自动交易边界继续位于 repository scope。根 Design/Architecture/Deployment 只保留共同边界并导航局部 authority；Monitoring execution plan 仅更新恢复与 authority 链接，仍独立存续，M2–M5 没有执行。

本阶段没有实现 Monitoring 代码、可执行入口、配置样例或 application SQLite，没有创建未来子模块或虚构启动命令；生产代码、Skew 策略、golden/oracle、原件、SDK 和 experiments 均未修改。局部实现状态和历史证据见 [Monitoring Acceptance](../monitoring/ACCEPTANCE.md)；结构检查不提升其业务交付状态，也不改变根 G1–G6/P1/P2。

`python3 harness/run.py docs` 为 PASS，报告 `artifacts/harness/20260911T054957Z-docs-90006cb0/result.json`；完整 `harness/tests` 33 项通过，`git diff --check` 通过。报告后的修改只登记本次证据；提交前再次执行结构与链接检查。

<a id="semantic-authority-s7"></a>

## Repository semantic embedding：Harness verification authority / S7

2026-09-11，从干净的 `main@94e8325` 恢复并核对 M0/S1–S6 的连续提交、登记和局部 Acceptance。本阶段只执行 S7：建立 [Harness AGENTS](../harness/AGENTS.md) 与 [Harness Contract](../harness/CONTRACT.md)，将 PASS/FAIL/NOT_RUN、dependency/skip、TEST DOUBLE、证据身份、result/reproducibility 及现场边界从 README 迁入唯一 Contract；[Harness README](../harness/README.md)保留实际 profiles、依赖、命令和测试导航。

`harness.evidence-contract` 已切换到本地 Contract，唯一的 S7 migration exception 已退出；S2–S7 不再有剩余迁移例外。根 Acceptance 仍只拥有 G1–G6/P1/P2、developer runner 与跨模块 Harness 映射，并导航 [Query](../query/ACCEPTANCE.md)、[Dashboard](../dashboard/ACCEPTANCE.md)和 [Monitoring](../monitoring/ACCEPTANCE.md)局部证据，没有复制其当前状态。根级入口补齐 [CTP experiment](../experiments/ctp/README.md)与 [Data Coverage experiment](../experiments/data_coverage/README.md)导航，实验内部文件和规则未修改。

本阶段只修改文档、authority registration 和文档必需路径检查；未修改 Harness runner 行为、生产代码、Skew 策略、oracle、fixtures/golden、SDK/originals、Docker 输入或 experiments，也未执行 S8。自动结构检查不提升 G1–G6/P1/P2 或任何模块业务状态。

迁移前 `python3 harness/run.py docs` 为 PASS（`artifacts/harness/20260911T055251Z-docs-fb5f4375/result.json`）。迁移后完整 `harness/tests` 33 项全部通过；最终 docs profile 为 PASS（`artifacts/harness/20260911T055748Z-docs-1ebc8e2e/result.json`），docs 与 authority 自测两个 step 均实际执行。`git diff --check` 通过，且相对 HEAD 的受保护路径检查确认 experiments、oracle、fixtures/golden、Skew 机器策略、SDK/originals 均无 diff。报告后的修改只登记本段证据；提交前再次执行直接结构、链接与 diff 检查。
