# MVP 验收矩阵

本文件只记录当前实现、验证证据和待补缺口；产品收尾条件由 [MVP](mvp.md)定义，设计与精确行为分别以 [Design](../DESIGN.md)、[Architecture](../ARCHITECTURE.md)和 [Contracts](contracts/) 为准。本矩阵中的门槛摘要用于映射证据，不创建新的设计要求。

状态基线：2026-09-10 developer runner 工程交付审计。**MVP 未完成**。工程回归由 harness 生成当次结果；历史报告只是指定时间的证据，不能证明本版本/本机当前实盘状态。下面的“待验”不是测试通过。此前的离线/原生/浏览器/打包检查和完整 Docker 网络限制见[整理验收记录](archive/reorganization-20260908.md)。

| ID | 收尾门槛 | 现有证据/实现 | 还需取得的证据 |
|---|---|---|---|
| G1 | 固定环境连续 3 个完整交易日，AU/AG 真实跨午夜至日盘/新交易日 | [CFFEX 短时实连](archive/acceptance/CFFEX_Coverage_Acceptance_CN.md)、[SHFE 短时夜盘](archive/acceptance/Market_Session_SHFE_Acceptance_CN.md)；合成夜盘脚本 | 持久保存三日检查点、run/配置身份、接收/提交推进、断线说明、真实夜盘各边界；待验 |
| G2 | 数据质量诚实，历史与当前分开 | Collector/Query/Calendar/Market State 测试；Skew JSON 当前/分钟/日序列、质量/历史/失败缺口及参考拒绝已做 TEST DOUBLE 回归；浏览器断线恢复 | 真实完整 MO 月链的分钟质量及异常证据；业务 JSON 已实现，真实业务待验 |
| G3 | 一个 MO 月 Skew 闭环，10 时点独立对账和追溯 | [七项 Analytics 契约与数值核心](contracts/analytics-skew.md)、独立 oracle；审核包离线导入、当前/日序列/历史 JSON、输入哈希与固定 revision 回放已实现并做合成回归 | 取得并审核真实官方日参考包；按固定误差做至少10个真实时点独立对账（≥6可算、≥4异常）；JSON 切片已实现，G3仍待验 |
| G4 | 30 秒理解汇报首页，3 次日常使用无需 SQL/日志 | React 汇报首页已实现月份选择、当前值/当日变化/时间/质量/原因、指定分钟回看和折叠诊断；组件回归为 TEST DOUBLE | 在已审核真实日包与完整 MO 月链上取得3次日常使用记录，实测30秒理解与无需 SQL/日志；待验 |
| G5 | 故障后恢复，保留已提交数据，备份恢复可读 | CTest、原生/容器独立停启/重启追加/心跳过期 | 本版本选择部署方式的回归；真实数据备份恢复的哈希/完整性/查询记录；现场待验 |
| G6 | 固定验收版本、可复现部署、说明完整、无阻断问题 | 原生/Docker 入口、锁文件、操作与契约已提供 | 对最终版本部署，保存构建/环境和结果，审核限制与阻断项；待验 |
| P1 | 真实一天库、完整目标链、单人核心查询 P95 ≤ 2 秒 | 既有 3 秒 SQL 预算是失败上限，不是性能证据 | 取得真实官方日包后，通过业务 API 记录≥100次业务查询耗时/错误、机器与库规模、冷热条件 |
| P2 | 活跃有效报价接收至页面显示目标 ≤ 30 秒 | 默认约15秒物化、5秒轮询、4秒前端请求超时 | 同一 observation 源/received/snapshot/显示时间配对；页面实测，待验 |

## Monitoring v1 平行扩展状态

2026-09-10，分支 `feature/realtime-monitoring-alerts` 已在 M0 文档冻结之上完成 M1 Feature service / HTTP 工程切片；M2–M5 仍未实现。交接见 [Monitoring execution plan](monitoring-execution-plan.md)。精确要求归 [Feature](contracts/features.md)和 [Monitoring](contracts/monitoring.md) Contracts，目标结构与当前部署的区别见 [Architecture](../ARCHITECTURE.md)。

| 交付层次 | 当前状态/证据 | 缺口 |
|---|---|---|
| M0 设计冻结 | 产品平行边界、领域模型、依赖/ownership、状态机、事务和投递恢复已落位 authority；milestone 拆为独立 commits | 文档证据仅证明设计和结构检查，不证明业务运行 |
| M1 Feature service / HTTP | 已实现通用 v1 envelope、显式注册表、复用 SkewService 的 `mo-skew-25d-v1` provider 及只读 `POST /api/features/evaluate`；新旧接口相同 TEST DOUBLE 输入的数值、时间、状态、质量、scope 与完整 evidence 对等；严格参数/失败和只读边界已有工程回归 | Docker 输入白名单已同步并通过结构检查；本机 Docker 命令不可用，实际 packaging context 导出未执行成功；真实 MO/官方参考仍沿用 G2/G3 缺口 |
| M2 Rule Engine | 待实现 | 纯规则、crossing、UNKNOWN、去重及 representative TEST DOUBLE 回归未执行 |
| M3 持久事件 / runtime | 待实现 | application SQLite、原子提交、独立进程和恢复验证未执行 |
| M4 webhook delivery | 待实现 | 独立投递、尝试记录、有限重试和不确定性恢复验证未执行 |
| M5 工程交付 | 待实现 | 隔离端到端与故障回归、实际运行手册待交付 |
| 真实运行 / 通知 | 未验 | 无本扩展真实 Skew 运行、实际 webhook 接收或用户收到通知的证据；既有官方参考与真实指标缺口仍保留 |

M0 文档基线检查：`artifacts/harness/20260909T152645Z-docs-a8bc6e08/result.json`（PASS）；领域文档检查：`artifacts/harness/20260909T153512Z-docs-0b2c4144/result.json`（PASS）。报告保留当时 HEAD/dirty patch、平台与日志哈希，只检查文档链接/authority 入口、既有依赖与构建边界，不验证新状态机或未来接口。

完整交接文档检查：`artifacts/harness/20260909T154127Z-docs-30337ce2/result.json`（PASS），`git diff --check` 通过；人工核对仅有 Markdown 变更，业务实现、Skew 机器策略及 oracle 未变。报告后的改动仅补充此证据登记，并澄清响应 scope 的实际交易日与缺口关闭的去重边界；最终内容以 M0 两个 Git commits 为准。

本次没有执行 analytics/offline/native/browser/packaging/docker，没有启动/停止真实服务、读取实盘数据或发送 webhook。basis、return、ATM IV 只有扩展性测试规划，未实现生产指标，也尚未执行这些 TEST DOUBLE 测试。原 G1–G6/P1/P2 均不因 M0 文档冻结签收。

M1 由两个独立提交交付：`feat(query): add shared feature projection`（`8c6c900`）和 `feat(query): expose read-only feature evaluation`。第一提交的 6 项 service/provider 测试使用真实临时 SQLite、Market State、生产 Analytics 与明确的 SYNTHETIC / TEST DOUBLE 参考包，验证 envelope 有限标量约束、注册表、严格 scope/参数/时间、Skew 公共结果逐字段投影、同一采样位置跨 Raw revision/请求时钟的稳定 sample key，以及未知位置不伪造 sample key。第二提交的 7 项 HTTP 测试在同类隔离输入上验证只读 POST、新旧接口对等、PARTIAL/历史/陈旧/不可用、未知/重复/非有限 JSON 与字段/版本/Feature/scope/参数拒绝、生产拒绝 SYNTHETIC、Raw 404/503 原样传播和未预期 provider 异常为 HTTP 失败；测试前后 Raw SQLite 字节一致。

本次完整 Query 回归 89 项通过；`python3 harness/run.py analytics` 为 PASS，报告 `artifacts/harness/20260910T151944Z-analytics-beea795b/result.json`，包含既有 frozen contract/oracle 与生产 Skew 回归，未修改模型、参数、质量门槛或数值容差。构建输入已同步至 Query Dockerfile、deny-by-default allowlist 与 harness 精确输入清单；docs 结构检查为 PASS，报告 `artifacts/harness/20260910T152100Z-docs-b207185b/result.json`，验证必要文件均被声明。`python3 harness/run.py packaging` 报告 `artifacts/harness/20260910T151708Z-packaging-e477e8ee/result.json` 为 FAIL：docs 与 harness tests 通过，但当前 WSL 未启用 Docker Desktop integration，`docker version` 失败，实际 context 导出因此 NOT_RUN；不能把结构检查写成 packaging PASS。

M1 没有实现或测试 Rule Engine、application SQLite、Monitoring runtime、webhook 或 basis/return/ATM IV，也没有启动/停止真实服务、读取实盘或发送通知。工程 TEST DOUBLE 通过不签收真实 Feature/通知证据，不改变 G1–G6/P1/P2 及 M2–M5 缺口。

## 本地开发入口交付状态

2026-09-10：从 Git 和当前代码复核 `94ed099`（范围与契约准备）、`c4501e7`（可选行情账号回归）及 `fd8ba28`（启动命令分组）。根 `./dev` 已实现 `doctor [component]`、`up [component]`、参数边界及前台监督；不带组件的 `up` 联合启动三个组件，单组件启动统一为 `up collector/query/dashboard`，退役的顶层组件命令返回 2、给出迁移提示且不启动。长期要求见 [Deployment Contract](contracts/deployment.md#developer-runner-的生命周期边界)，实际命令见 [Operations](operations.md#前台开发会话)。任务 A 的真实 Collector 配置校验与 doctor TEST DOUBLE 回归覆盖账号字段缺省、空值、正常已填、分别过长、整体失败脱敏和无持久写入；任务 B 的 32 项 runner 回归覆盖新 help、参数位置/适用范围、旧入口零分派、单组件/联合分派及既有监督器边界。

`python3 harness/run.py offline` 报告为 `artifacts/harness/20260910T063104Z-offline-c6268769/result.json`（PASS，14 步均实际执行）。报告基线 revision 为 `c4501e7`，记录的工作树补丁 SHA-256 `40ac99918056b21e2cc5257baf3534b1a4a2cb68aba6fafdac359af53913be83` 与 `c4501e7..fd8ba28` 的 Git binary diff 一致。该次运行通过 docs、harness-tests、configure/build、7 项 CTest、显式 credentials/CLI 语义、32 项 runner tests、实际 runner smoke、76 项 Query、Universe、deploy、verify、React 和 frontend-build。实际 smoke 只使用临时配置/data/flow、随机 loopback 端口和 TEST DOUBLE SDK，经过 Collector → SQLite → Uvicorn → Vite，验证共享 Raw、Dashboard 代理、下游隔离、writer/端口冲突、会话清理及重启保留追加。

这些证据不包含真实 CTP/行情、真实配置写入、现场恢复、当前版本浏览器或 Docker runtime，也不改变 native/Docker 行为。账号空值被本地接受不证明真实前置允许匿名接入；进程与 HTTP 工程闭环不证明行情推进或业务就绪。本轮不签收 G1–G6，TEST DOUBLE 和监督测试不能替代三日行情、真实恢复及最终部署验收。

## Query 参考目录路径一致性修复（2026-09-10）

提交 `9cc5870` 将单 Query 和联合启动共用的参考目录环境准备逻辑对齐 [Deployment Contract](contracts/deployment.md)：已设置的 `MARKET_CALENDAR_DIR`、`SKEW_REFERENCE_DIR` 基于调用目录转为绝对路径，缺省保持缺省，空字符串映射到调用目录；不展开占位符、不解引用符号链接、不创建目录，也不改父进程及其他组件环境。此记录不替换上文历史 offline 报告的版本归属。

该修复工作树（随后提交为 `9cc5870`）执行 `python3 -m unittest discover -s tests -p 'test_dev*.py' -v`，34 项通过。新增 TEST DOUBLE 回归覆盖单组件/联合启动的相对、绝对、空、缺省、空格/`..`、符号链接、未展开字符、无持久写入及环境隔离；标准库子进程使用实际构造的 Query cwd/env 验证参考路径仍指向临时调用目录。`python3 harness/check_dev_semantics.py --scope all` 的 credentials 和 CLI 均 PASS；`python3 harness/run.py docs` 为 PASS，报告 `artifacts/harness/20260910T081747Z-docs-41e87148/result.json` 保存提交前修复工作树信息；`git diff --check` 通过。

本次未重跑完整 offline、浏览器或 Docker runtime，未启动真实行情、读取真实配置或加载业务参考包。以上仅证明路径与文档一致，不签收真实行情或 MVP 门槛。

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

本轮范围为工程切片，暂不执行真实业务验收。G2/G3 **未签收**：本轮没有已审核生产日包、真实完整 MO 月分钟质量证据或10个真实时点独立对账。HTTP 工程切片可用不能替代这些证据；G4 的汇报页代码已实现，但真实三次日常使用未取证，因此 G4 仍未签收；P1/P2 也尚无真实性能证据。本轮未启动或重启真实服务。

## 汇报首页工程证据（2026-09-09）

React 组件 7 项通过，覆盖当前 Skew、当日变化、完整性与 TEST DOUBLE 标记、PARTIAL、STALE、UNAVAILABLE、指定分钟回看、Skew API 断线清值/恢复以及诊断独立失效；`npm run build` 通过。`browser` 结果为 `artifacts/harness/20260909T005859Z-browser-2446e812/result.json`（PASS），在实际 Chromium 中覆盖同样的 Skew TEST DOUBLE 状态、移动端无整页溢出，并保留真实临时 C++ → SQLite → FastAPI 诊断路径。`packaging` 结果为 `artifacts/harness/20260909T005808Z-packaging-957813a7/result.json`（PASS），证明 Dashboard 生产构建输入仍符合镜像 allowlist。

这些数值和参考均为 TEST DOUBLE，没有已审核的真实官方日包、真实完整 MO 月链或人工日常使用记录。因此本节只表明汇报页工程行为可回归，**不签收 G4**。


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
