<a id="repository-documentation-governance"></a>

# 长期文档入口

本文件是 repository documentation governance 的唯一规则来源；[Architecture](../ARCHITECTURE.md#knowledge-topology)拥有目标布局和 authority mapping，[ExecPlan](semantic-embedding-execplan.md)只安排迁移执行与完成条件。当前业务定义由根与下方链接的现行 Contracts 分别拥有，冻结目标不表示剩余迁移已经完成。

<a id="authority-rules"></a>

## Authority scope 与文档职责

**Authority should live at the smallest common scope it constrains.**

Parent scope 只负责自身 scope 的语义、跨直接子级的 invariant，以及对下级 authority 的导航。Child scope 继承并链接 parent authority，不重复定义，也不得覆盖合法的父级不变量。这一规则逐层适用；跨模块 invariant 位于所有受约束模块的 smallest common ancestor。

一个 semantic fact 只能有一个 authoritative location。先判断规则约束哪些责任主体，再选择 scope；不按读者数量、目录名或语言分类。公开能力有消费者，不代表 provider 全部内部设计都提升到根；共同约束 producer/consumer 的协议属于共同祖先，provider 内部计算仍归 provider。目录中的工具与 runtime 可以承担不同责任，不以物理位置推断整目录依赖禁令。

文档与代码 co-located，但职责保持纯净：代码只保留必要接口说明和 authority 链接，不嵌入长期设计文章。Topology 跟随真实 ownership / semantic boundary；不为放文档拆代码目录，不创建空模块或对称文档。扁平模块可在本级用领域 Contract 分卷，不因此虚构子模块。

| 文档类型 | 在所属 scope 唯一负责 | 何时不需要 |
|---|---|---|
| AGENTS.md | Agent 工作路径、修改纪律、局部验证要求、必读 authority 导航；不复述业务规则 | 祖先指导已充分且无局部工作差异 |
| README.md | 本级入口、子级导航、实际 build/run/usage/examples/troubleshooting；不定义第二套设计或契约 | 非独立使用单元且父级可直接导航 |
| DESIGN.md | 本级长期取舍及 rationale | 无需独立维护局部理由 |
| ARCHITECTURE.md | 本级组件关系、数据流、所有权、依赖；对子级结构只导航 | 简单单元无需独立结构分解 |
| CONTRACT.md / 领域 Contract | 本级精确行为、接口、不变量、失败与兼容规则 | 只有继承的约束，没有本级独立契约；内容少时不分卷 |
| MVP | Repository 产品目标、范围和系统完成边界 | 不为每个代码目录复制产品文档 |
| ACCEPTANCE.md | 本级当前实现、证据、版本与缺口；根保留系统门槛和跨模块证据导航 | 无独立交付状态需要维护 |
| Operations / README 用法 | 实际运行、维护、恢复与操作步骤 | 局部用法足以放 README 时不另建 Operations |

冲突按事实职责裁决，不按文档日期或文件名覆盖顺序：Contract 决定行为，Design 解释理由，Architecture 描述结构，MVP 决定产品边界，Acceptance 陈述证据。代码是实现证据，不静默改写契约；无法在既有 authority 下裁决时停止受影响工作并报告冲突。

[外部参考](references/README.md)保存来源、版本与原件，不自动成为项目决定；[历史归档](archive/README.md)保存过去观察，不证明当前状态。Harness 是验证与证据入口，不定义产品行为。示例与摘要不得夹带没有规范来源的新默认值、优先级或失败要求。

<a id="progressive-disclosure"></a>

## 导航与渐进式阅读

1. 从任意目录工作，先读根及沿途适用 AGENTS；读取最近 scope README，按任务选择 Contract、Architecture、Design、Acceptance 或操作说明。
2. 父入口直接链接已登记子 scope 的入口；子入口链接父入口及必需上级协议。进入子 scope 后只加载该路径上的 guidance，不默认加载兄弟模块。
3. 跨 scope 引用标明共享协议、依赖的公开能力、证据或参考；不得依赖兄弟私有设计取得隐含约束。父级可直链深层 authority，但不能代替其定义。
4. 验证时只读取局部要求和 [Harness](../harness/README.md)相应 profile。新人了解产品时从 [MVP](mvp.md)、[Design](../DESIGN.md)、[Architecture](../ARCHITECTURE.md)进入，不把全仓 Contracts 作为局部任务前置。

根 Design/Architecture 与共享 Raw boundary 已迁移；其余尚未迁移项继续使用下面的现行地址，并按 [mapping](../ARCHITECTURE.md#authority-mapping)逐项切换。未来路径以代码格式表示，不链接不存在文件、不预建占位文档。每项迁移必须同时移动定义、删除重复并更新导航，旧位置不能成为第二 authority。

仓库级状态与操作：[Acceptance](acceptance.md) · [Operations](operations.md)。

机器可读的 scope、claim、导航、迁移例外与依赖关系从根 [`.authority.json`](../.authority.json) 开始；JSON 只登记关系，业务正文仍由下列文档负责。

精确契约入口：

- [Raw Market Facts 共享边界](contracts/raw-boundary.md)
- [Collector](contracts/collector.md)
- [Read Path](contracts/read-path.md)
- [Market State](contracts/market-state.md)
- [Calendar / Universe](contracts/market-session.md)
- [Deployment](contracts/deployment.md)
- [Analytics / Skew v1](contracts/analytics-skew.md)及其[机器策略](contracts/analytics-skew-v1.json)
- [Feature 查询 v1](contracts/features.md)（已冻结；实现与验证状态见 [Acceptance](acceptance.md)）
- [Monitoring / Opportunity / Notification v1](contracts/monitoring.md)（已冻结，待实现）

可执行模块手册：[Collector](../collector/README.md)、[Query](../query/README.md)、[Dashboard](../dashboard/README.md)。验证入口和证据语义见 [Harness](../harness/README.md)。

## 维护约定

一次性 execution plan 不是长期 system of record；任务完成后应将稳定规则归入对应 authority、在 Acceptance 登记实际证据，并移除活动计划及导航，必要历史从 Git 追溯。不恢复 `docs/tasks/` 或积累逐任务过程 specs。

[Monitoring v1 execution plan](monitoring-execution-plan.md)同样只承载有完成边界的实施交接。当前交付进度从 [Acceptance](acceptance.md)核对，不根据计划中的历史 M0 叙述推断；产品、领域行为及状态分别以 MVP、Feature/Monitoring Contracts 和 Acceptance 为准，完成后移除活动导航。

修改信息时只更新其 authority，并检查引用它的入口是否仍准确。文档状态用词中，“已实现”必须有代码证据，“已验证”必须说明版本、环境、数据来源与证据；“待实现/待验”不得省略。当前结论统一登记到 Acceptance，不回填为设计定义。旧过程 specs 不再维护，可从 Git 历史追溯。

[Repository semantic embedding ExecPlan](semantic-embedding-execplan.md)负责本次迁移交接，阶段状态见 [Acceptance](acceptance.md#semantic-authority-s2)。它与 Monitoring 业务实施计划相互独立；已完成阶段不授权继续执行后续迁移或 Monitoring 实现。
