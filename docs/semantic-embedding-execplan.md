# Repository semantic embedding：ExecPlan

日期：2026-09-10。冻结基线：`main@351003e`，`feature/realtime-monitoring-alerts` worktree 同 HEAD，freeze 开始时两个工作树均干净。Semantic freeze / M0（原计划 S0）已由 `e67a9b0` 交付；后续 session 仍必须以用户明确指定的单一阶段为边界。此 M0 与 Monitoring 业务计划的 M0 不是同一阶段。

本文只拥有执行顺序、验证、恢复、停止与计划生命周期，不拥有长期规则。治理唯一见 [docs README](README.md#authority-rules)，目标布局/归属唯一见 [Architecture mapping](../ARCHITECTURE.md#authority-mapping)，机器导航关系见 [Architecture](../ARCHITECTURE.md#authority-registration)。业务仍以各现行 Contract 为准；阶段实现与验证状态唯一登记 [Acceptance](acceptance.md#semantic-authority-s6)，不从本表推断完成程度。

<a id="resume"></a>

## 1. 新 session 恢复与 baseline reconciliation

1. 读取 [根 AGENTS](../AGENTS.md)、[文档入口](README.md)、上面的目标 mapping 和本计划；确认用户本次授权的阶段，只执行该范围。
2. 运行 `git status --short`、`git log -5 --oneline`、`git worktree list`，核对本阶段之后提交和未提交改动；不重置现场、不覆盖其他人的工作。基线不同就先重做受影响 mapping。
3. 从 `python3 harness/run.py docs` 开始，按 [Harness](../harness/README.md)选择安全检查。检查器当前固定中央路径不代表最终 topology，后续切换路径必须与检查同步。
4. 对本阶段每个规则组建立 review 对照：当前文件/标题、Git 基线、唯一目标/锚点、处理方式（移动/拆分/转引用/归证据）、理由、相关测试/证据。它是迁移清单，不抄写规则正文。可在本计划追加阶段对照，不积累多份任务 specs。
5. 复核原件和 SDK manifest、Skew 策略/fixture/生成器及 experiments 的基线哈希；不读 collector/data 或真实配置取证。对照源码和测试仅判断当前实现，不把代码自动提升为业务决定。

### 已 reconciliation 的事实与待处理问题

- `351003e` 已含 Feature service、HTTP endpoint 及测试：`8c6c900` 为 service，`351003e` 为 HTTP。Monitoring M2–M5 未实现；原 execution plan 的旧基线/提交线索不覆盖 Git 与 Acceptance。
- S2 已将 [Read Path](contracts/read-path.md) 的 Feature 可变进度改为 [Acceptance](acceptance.md) 导航；Feature 行为契约未因状态 reconciliation 改写。
- [Query Skew](../query/contracts/analytics-skew.md)与 Read Path 的分钟选择、当前可用性和当日变化已按 mapping 区分计算语义和 HTTP 投影。
- Raw/WAL/锁/心跳/部署限制散布多份 Contract，按共享不变量与局部行为切分；不能为了去重丢失例外、错误或时间条件。
- Skew §10/§11 混有历史验证、实现状态和真实接口细节；证据移出，接口细节保留为规范。
- Collector README 宣称完整配置规则在 Contract，实际缺少部分规则；Dashboard 四秒请求超时主要见 README/代码。已有文档规则归位；仅有代码证据的缺口进入所属 Acceptance，不在迁移中创造新契约。
- Query README 缺少已实现 Feature 用法；生产模块没有局部 AGENTS。后续局部迁移时补齐。
- Universe 工具跨目录导入 Calendar，native 管理三个服务。禁止把采集 runtime 的隔离误写为整个 collector 目录的零 Query 依赖。
- [实验 AGENTS](../experiments/data_coverage/AGENTS.md)、[SPEC](../experiments/data_coverage/SPEC.md)、[README](../experiments/data_coverage/README.md)存在部分证据规则重复，但只作为案例和发现保留，本次不治理实验内容。
- M0 时的 docs 检查不校验锚点、claim 唯一性、scope 或自动发现模块文档，必需路径也未列 Feature/Monitoring；S1 将这些缺口纳入登记、自测和 docs profile，但自动检查仍不证明自然语言业务等价。

不完整 Raw schema、coverage schema、配置规格不在本迁移中补造。新发现的语义冲突先记录相应 authority，不能按代码或新文档日期机械裁决。

## 2. Milestones 与单独 commits

依赖顺序 **M0/S0 → S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8**。每阶段一个可独立 review 的 commit，含对应链接、检查和状态更新。整项反向提交可回滚；不能只恢复旧定义形成双 authority。既有 Monitoring 业务 milestones 独立，不自动跟随执行。

| 阶段 / commit | 动作与完成边界 |
|---|---|
| M0/S0 `docs: freeze repository semantic authority architecture` | 固化治理、目标 topology/mapping、本 ExecPlan 和当前状态；不迁移业务文档、不建目标目录、不实现新检查器；相关文档检查后提交并停止 |
| S1 `test(docs): introduce scoped authority validation` | 实现登记、链接/锚点/claim/scope/依赖检查及负向测试，登记当前布局。未迁移项目只允许逐项具名临时例外，记录当前/目标位置及退出阶段；禁止全局关闭检查 |
| S2 `docs: establish repository scope authorities` | 根 DESIGN/ARCHITECTURE 归位，拆出 Raw 共享边界，跨 Contract 去重；修复 Feature 状态导航和 runtime/工具依赖歧义；同提交删除旧 docs/design.md、docs/architecture.md 并更新本计划等活动引用 |
| S3 `docs(collector): localize collection and tool authority` | 下放 Collector 内部契约/结构/guidance，建立 scripts 局部入口；系统部署教程归根 Operations；不移动 native/universe 代码 |
| S4 `docs(query): localize market and analytics authority` | Market State、Skew、策略、参考适配、局部证据下放；共享 HTTP/Feature 留根；补 Feature 使用入口；同步所有路径消费者与 oracle provenance |
| S5 `docs(dashboard): localize presentation authority` | 页面行为与证据归位；根 HTTP 保留协议；删除 Analytics/Read Path 的页面重复定义 |
| S6 `docs(monitoring): embed frozen monitoring authority` | 建立非空 Monitoring 文档 scope，迁入既有冻结设计和状态；不实现代码。更新原 Monitoring execution plan 链接和恢复说明，不改变业务交付边界 |
| S7 `docs(harness): localize verification semantics` | Harness CONTRACT/AGENTS 归位，README 保留用法；根 Acceptance 保留系统门槛/跨模块证据并导航局部记录；完善实验入口且实验文件不变 |
| S8 `test(docs): enforce final authority topology` | 删除全部临时迁移例外，启用最终旧路径禁令，完成逐项无丢失/无双定义 review 和 clean-clone 导航演练；删除本 ExecPlan 及活动导航，保留 Git 历史 |

每阶段按[归属 mapping](../ARCHITECTURE.md#authority-mapping)细化到段落/规则组，记录所有移出内容的去向。迁移在同一提交中移动定义、删除源处重复、更新消费者链接及检查；不能通过先复制再等待未来清理获得 locality。模块读取入口一旦落地，父入口必须指向它。

M0 的目标路径仅写为文字或代码格式；S1 创建现有 scope 的关系登记，并在父登记中声明尚无目录的 frozen-pending scope。S2–S7 才创建对应的长期内容文件，不预建空 Monitoring 文档。

### S1 reconciliation 清单

S1 以 `main@e67a9b0` 的干净工作树为实际基线。根登记逐项列出当前定义、稳定锚点、受约束 scope、唯一目标及 S2–S7 退出阶段；局部登记只连接当前入口和所依赖 claim，不复制业务正文。当前中央定义继续有效，尚未发生业务 authority 迁移。

检查器保留并区分 `collector/scripts/universe.py` 到 Query Calendar 的工具依赖、Query 镜像到 Harness golden fixture 的构建输入，以及父 scope 使用现有 child 工具/参考文件的输入；Monitoring 只作为 frozen-pending scope 登记，不创建目录或运行入口。Feature/Monitoring 当前 Contracts 已进入必需路径检查。

### S2 reconciliation 清单

S2 以 `main@6994059` 的干净工作树为实际基线。`docs/design.md` 与 `docs/architecture.md` 原子迁到根 `DESIGN.md` / `ARCHITECTURE.md` 并删除旧地址；repository claims 已退出 S2 exception。仍待 S4/S6 下放的 Query/Monitoring 局部段落只在根文件保留一份，登记中的当前路径同步为根文件，退出阶段不变。

共享 Raw 所有权、writer 协调、WAL/只读和 Collector 诊断协议从 Collector/Read Path 拆到 `docs/contracts/raw-boundary.md`；旧处改为链接，Deployment 只保留系统挂载与生命周期。Read Path 的 Feature 标题不再声称待实现，实际状态统一导航 Acceptance。Architecture 将 C++ Collector runtime 与 `collector/scripts/universe.py`、native manager 的工具职责明确区分；不移动代码或扩大合法依赖。

### S3 reconciliation 清单

S3 以 `main@c15b229` 的干净工作树为实际基线。原 `docs/contracts/collector.md` 的 callback、配置、采样、session、提交与自身停止规则迁至 `collector/CONTRACT.md`，旧文件删除并加入 retired-path 检查；共享 Raw 规则仍只由 `docs/contracts/raw-boundary.md` 拥有。Collector 的内部 C++ 文件关系单独登记到 `collector/ARCHITECTURE.md`，不把实现细节提升为新业务语义。

Market Session 中只有来源抓取、字段校验、旧代码保留、generation 发布和可选重启行为迁至 `collector/scripts/CONTRACT.md`；Calendar/Universe 版本、日期交接、coverage 与页面消费者协议继续留根。`collector/scripts/README.md` 成为工具 scope 入口，Universe 对 Query Calendar 的既有依赖继续作为 tool dependency 登记，不变成 C++ runtime 依赖。Collector README 的三服务教程迁到根 Operations，工具命令归 scripts README；`native.py`、`universe.py` 与其他生产代码均未移动或修改。

### S4 reconciliation 清单

S4 以 `main@8008722` 的干净工作树为实际基线。Query 的 guidance、Design、Architecture、组件 Contract 与 Acceptance 已建立；Market State、Skew、机器策略、ReferenceBundle adapter 及来源说明归入 Query scope。公共 HTTP/Skew wire shape、Feature envelope/Skew 映射、Raw 及 Calendar/Universe protocol 留在 repository scope；Dashboard 投影、时段与 Skew 页面 claim 继续由 S5 具名例外承接。

`analytics-skew-v1.json` 从旧中央路径按字节迁移，SHA-256 仍为 `d520d8a2831f81df1372efe280898e2e682f5e039669488417c1f4fe7ec56f14`。oracle 生成器只因策略路径变化更新，fixture 只更新对应 `generator_sha256`；新增去除该 provenance 字段后的固定基线哈希检查，拒绝 vectors/chains/expected 或其他 fixture 字段漂移。所有 S4 例外已退出，旧中央 Query authority 路径进入退役检查。

### S5 reconciliation 清单

S5 以 `main@414e043` 的干净工作树为实际基线。Dashboard 的 guidance、页面 Contract、局部 Acceptance 与登记已建立；Read Path 的 React 布局/轮询/失败清值、Market Session 的页面时段表，以及原 Skew Contract 的两位显示精度归入 Dashboard scope。公共 HTTP/wire shape、Calendar/Universe 交接与 Feature 语义继续留在 repository scope，Market State、Skew/Analytics、solver 和 reference semantics 继续属于 Query。

三个 S5 migration exceptions 已退出，旧中央位置改为链接而不保留页面定义。历史汇报首页证据原样迁入 Dashboard Acceptance，根 Acceptance 只映射 G4/P2 和本阶段迁移证据。生产 React、样式、测试、Analytics 策略、golden、原件、SDK 与 experiments 均未修改；React 中没有既有规范来源的控件/文案细节只登记为 evidence/gap，不提升为 Contract。

### S6 reconciliation 清单

S6 以 `main@8a1550a` 的干净工作树为实际基线。Monitoring 的 guidance、README、Design、Architecture、Contract、Acceptance 与登记已建立；Rule/Evaluation、crossing、UNKNOWN、配置、application state、Opportunity Event、事务、恢复和 delivery/retry 语义归入 Monitoring。共享 Feature protocol、Raw/Market Facts ownership、Monitoring↔Query access、system lifecycle 与永久不自动交易边界继续位于 repository scope并由 Monitoring 引用。

四个 S6 migration exceptions 已退出，旧中央 Monitoring Contract 路径进入退役检查；根 Design/Architecture/Deployment 仅保留跨模块 rationale、目标流、所有权和部署隔离。Monitoring 业务 execution plan 继续独立存续并切换 authority/recovery 导航；本阶段不实现代码、不提供虚构命令、不创建子模块，也不执行其 M2–M5。

## 3. Harness 工作规格

按 [机器导航职责](../ARCHITECTURE.md#authority-registration)实现同版本 `.authority.json`。claim 粒度是独立接口/规则组，登记只承载路径和关系，不能存业务正文。S1 建检查与迁移前登记，S8 拒绝最终旧位置；中间例外必须可枚举且逐项退出。

| 检查 | 拒绝场景 / 正向场景 |
|---|---|
| 本地链接与锚点 | inline/reference-style 链接、显式锚点、目录入口失效；保留有效父子/跨协议导航。外部网络可用性不属于离线检查 |
| 导航可达 | authority 孤立、漏 child、错 parent、层级环、未来路径假链接；允许父级直链必要深层 authority |
| 唯一 authority | claim 多定义/无定义、引用不存在声明、计划/证据充当规范；引用不是复制定义 |
| Scope | 定义不在 constrained scopes 的共同祖先，子级定义父/兄弟规则；不能只按读者集合提升所有局部算法 |
| 文档重复 | 相同规范性段落多处定义；排除示例、明确引用、历史/外部材料。语义相似但改写的重复必须人工 review |
| 代码依赖 | 新增未登记跨一级模块 import/include/构建输入，Monitoring 导入 Query 私有模块，正式 runtime 依赖实验区；保留 universe.py → market_calendar.py 精确工具依赖 |
| 旧中央残留 | 已迁移文件、复制副本、活动链接/路径常量重现；继续禁止 docs/tasks；允许未迁移项目的具名短期例外 |
| 来源/数值保护 | SDK/原件/策略哈希漂移、golden 数值变化、非法 provenance 更新；不能放宽既有校验 |
| 检查器自测 | 每类失败使用临时 TEST DOUBLE 仓库；覆盖合法引用、继承、工具/测试/实验差异和跨平台路径边界 |

区分生产、工具、测试、实验依赖，不能用全目录循环检测代替语义。保持 Docker 输入/SDK/原件既有保护，不为文档扩大镜像白名单。实验内部不接受生产 authority lint；父入口链接仍须有效。历史正文不要求改为当前词汇，历史链接检查与旧 authority 禁令分开。

S1 起 docs profile 包含文档检查器负向自测，仍仅标准库、离线、无真实服务副作用。S8 再移除全部临时例外并启用最终旧路径禁令。

自动检查不能证明所有自然语言业务等价。claim/相同段落检查以外，必须人工核对逐项 mapping；不得以 embedding 相似度阈值作为正确性判据。本计划不交付向量库或索引服务。

## 4. 验证与特殊迁移风险

### 每个阶段

- 运行 `python3 harness/run.py docs`、相关 Harness 自测、`git diff --check`；结果必须检查实际执行数量/退出码，不把跳过或缺依赖写 PASS。
- 人工检查新增/修改链接与锚点，逐规则对照数值、否定条件、边界、时间、错误、版本和证据身份不变。
- 审查 diff：无生产行为变化、无 package 重构、无 experiments/原件/SDK 修改；业务 Contract 只在对应迁移阶段组织，不改业务含义。
- 当前结果登记 Acceptance 并定位版本/报告；历史结果原样保留版本，不因迁移重新宣称当前业务通过。
- Markdown 整理不运行真实 up/update/stop，不读真实配置/Raw、不发 webhook，不做现场恢复。纯文档无需全量 native/browser/Docker。

### S4：Skew 策略和 oracle

- 策略按字节移动，保持 `policy_sha256`。策略现有 SHA-256：`d520d8a2831f81df1372efe280898e2e682f5e039669488417c1f4fe7ec56f14`。
- 路径消费者包括 `harness/check_analytics_contract.py`、`harness/analytics_oracle.py`、其测试、README/AGENTS、生产源码中的 Contract 链接；全仓搜索补齐，不只修改文档链接。
- 修改 oracle 的策略路径将改变生成器哈希，现有 `generator_sha256` 为 `bacac840f959d545abcb14cd4ba25d9962fe426f45b0f4b7cf1319829edf77fc`。只允许路径变化对应的 provenance 字段更新；所有 vectors/chains/expected 值保持不变，禁止覆盖重生成 golden。
- 使用固定 QuantLib 1.40 / mpmath 1.3.0 环境运行 oracle 比较，运行 `python3 harness/run.py analytics`（含 analytics-contract）。新增基线对照验证 fixture 除生成器 provenance 外未变；不得改数学、参考准入或容差。
- 缺依赖明确 NOT_RUN，S4 不签收；普通依赖恢复不触发数值重设计，不因此自动安装/升级生产依赖。

### S8：无上下文导航演练

在干净 checkout（不带本次聊天、artifacts 或未跟踪辅助文件）只依据仓库入口执行只读定位：

1. Query Skew：找到局部契约/策略，以及按需依赖的 Market State、Raw、HTTP 协议。
2. Dashboard 清值：找到页面契约和共享 HTTP；无需读取 solver。
3. Universe：找到 scripts 工具契约与根 Calendar/Universe；明确与 C++ runtime 的不同依赖。
4. Experiment：进入已有 AGENTS/SPEC → 数据类型 → 来源；不要求加载全部生产 Contracts，也不因 NO_SAMPLE 发网络请求。

完成条件：所有现行规则唯一、可达且在正确 scope；无旧中央局部定义；根只保留 repository 语义/真实跨模块约束；业务/证据含义不变；所有迁移例外消失。治理、mapping、状态、必要检查在删除本计划后仍独立可读。

## 5. 冻结项、裁量与停止条件

### 迁移前已冻结，实施者不得另选

- [治理职责](README.md#authority-rules)、[目标 topology/mapping](../ARCHITECTURE.md#knowledge-topology)、共享协议归属及代码位置不变。
- Raw、Calendar、Market State、Skew、Feature、Monitoring 既有含义/版本；MVP 与真实证据缺口不提升。
- 原件/SDK/策略/golden/实验保护；合法工具依赖及 native 系统职责；无生产新指标、部署能力或业务实现。
- Monitoring 后续可建立有实际冻结内容的文档 scope，不能预建空模块；实验内容/命名保持字节不变。
- 活动迁移计划最终删除；Monitoring 原计划有独立生命周期。

### 实施者可以决定

不改变 scope 的段落顺序、精简措辞、链接文案；claim/锚点拼写；检查器函数、错误信息、临时测试 fixture 组织；review 清单排版与 Git rename 展示；已有非规范示例去重。不授权补全未确认业务规则或改变归属决策。

### 停止受影响迁移并重新设计

1. 规则没有唯一 owner，必须复制到两个局部文档才能继续。
2. Locality 必须靠移动代码、虚构子模块或拆 Query 包满足。
3. 正常局部任务仍需读取大部分中央/兄弟文档，只有路径发生改变。
4. Producer/consumer 对同一时间、身份、错误或生命周期形成独立定义。
5. 现有 Contract 冲突，需要选择新业务语义才能继续；不能按代码或日期裁决。
6. 检查器必须靠宽泛例外接受现状，或把所有跨模块链接都判为非法。
7. 数值、golden、原件、SDK、实验出现本计划之外的改动。
8. 并行提交改变接口、owner 或模块结构，使 mapping 不再覆盖实际状态。
9. 长期设计必须依赖 milestone、commit 步骤或未实现命令才能被理解。

普通断链、漏登记、缺依赖、测试失败按范围修复或如实阻断，不自动触发业务重设计。不清现场、不跳过失败来签收。

## 6. 计划生命周期

本文保持活动状态供未来被明确授权的 migration session 使用；每个 session 在完成用户指定的单一阶段后停止。后续每阶段在 Acceptance 登记证据，并更新本文中的路径和必要 reconciliation，不创建多份竞争计划。

S8 完成后删除本文和所有活动导航，Architecture mapping 转为现行归属导航，规则留 docs README，状态/证据留 Acceptance。历史步骤和提交从 Git 追溯，不移动到 docs/tasks，不将本计划全文复制为长期 Contract/Design。删除前检查没有任何长期规则只存在于本文。

Monitoring execution plan 不因 S8 自动结束或删除；只有其业务交付满足自身条件时结束。迁移不执行 Monitoring M2–M5。
