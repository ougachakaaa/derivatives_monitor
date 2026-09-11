# 实时监控 v1：Execution plan

日期：2026-09-09。运行代码基线 `23672a5`，分支 `feature/realtime-monitoring-alerts`；领域冻结首个提交为 `5711078`。本文是有完成边界的实施交接，不是长期 system of record；当前交付/证据状态唯一登记在 [Acceptance](acceptance.md)。

本次只交付 **M0 文档冻结**，不开始 M1–M5 业务实现。后续每个 milestone 可分别交给 Sol 的 Goal 模式，实施者无需读取原对话。每个 session 以用户指定 Goal 为工作边界，不因本文件列出全部任务就一次执行全部里程碑。

## 1. 阅读入口与 reconciliation

先读 [AGENTS.md](../AGENTS.md)与[文档入口](README.md)，检查分支、Git 历史、工作树和 Acceptance，运行 `python3 harness/run.py docs`。后续分支可能继续演进，不能用本基线覆盖新的实现或现场证据。

| Authority / 实现 | 对本任务的约束或已确认事实 |
|---|---|
| [MVP](mvp.md) / [Design](../DESIGN.md) / [Architecture](../ARCHITECTURE.md) | Monitoring 是平行扩展；主线 Skew 收尾不变；冻结目标结构与当前三组件部署分开 |
| [Feature Contract](contracts/features.md) | 公共语义、单 Feature 查询、Skew 投影、采样身份、共享/窗口边界 |
| [Monitoring Contract](contracts/monitoring.md) | Rule/Evaluation、crossing、事务、恢复和投递语义；实施不得另选状态机 |
| [Market State](../query/contracts/market-state.md) / [Market Session](contracts/market-session.md) | 时间、session、revision、质量及显式 Universe 不变量 |
| [Skew Contract](../query/contracts/analytics-skew.md)及[机器策略](../query/contracts/analytics-skew-v1.json) | 金融模型、单位、参考准入、质量和 oracle 容差全部保持 |
| [Read Path](contracts/read-path.md) / [Deployment](contracts/deployment.md) | HTTP 只读、错误和进程/存储边界；不接管现有部署 |
| [Market State 实现](../query/market_state.py) | 已有显式读取接口，Monitoring 无需重建第二条 Raw 读取路径 |
| [Skew service](../query/skew_service.py) / [数值核心](../query/analytics.py) | 已有业务时间选择与完整公共结果；只增加 Feature 投影，不复制金融实现 |
| [Query app](../query/app.py) / [项目配置](../query/pyproject.toml) | 既有 FastAPI、扁平导入、非 package 模式；新增 HTTP 避免跨项目导入改造 |
| [Harness](../harness/README.md) | 测试范围、TEST DOUBLE、PASS/FAIL/NOT_RUN 和现场保护；工程测试不证明实盘 |

现有生产指标只有 MO 25Δ Skew。IM basis 的现货来源、5 分钟 return 窗口及 ATM IV 定义不在本次生产范围；测试只验证这些 Feature 输出可进入同一规则引擎。Skew 的平价远期和翼 IV 不能冒充这些缺失能力。

Skew Contract 原有页面/HTTP“待完成”文字落后于 Acceptance 和代码；M0 将可变进度改为引用 Acceptance，保留数值、参考、失败与独立验证要求。原 MVP 的自动告警排除项改为单月观察闭环的边界，并登记平行扩展，不改主线 G1–G6/P1/P2。

## 2. Milestone 与独立 commits

依赖顺序 **M0 → M1 → M2 → M3 → M4 → M5**。每个 commit 连同必要定向测试独立 review；表内 ①/② 为不同 commits。必要文档同步随相关实现，不积累第二套过程 specs。

| Milestone / Goal | Commit ① | Commit ② | 最终验收状态 |
|---|---|---|---|
| **M0：冻结核心边界** | `docs: freeze feature and monitoring v1 boundaries`：MVP、Design、Architecture、Feature/Monitoring Contracts；已提交 `5711078` | `docs: publish monitoring implementation handoff`：Read Path/Deployment 链接协调、Skew 进度归位、Acceptance、入口及本文 | 仅 Markdown 改动，契约无矛盾；docs 与 diff 检查通过；M1–M5 明确待实现 |
| **M1：暴露共享 Feature** | `feat(query): add shared feature projection`：通用 envelope、注册表、复用 SkewService 的 provider；对等测试 | `feat(query): expose read-only feature evaluation`：HTTP endpoint、结构/失败回归、Query 构建输入同步 | 新旧接口相同输入数值/时间/质量/身份一致；不需 Monitoring 或新行情写入；旧 API 兼容 |
| **M2：建立纯规则核心** | `feat(monitoring): define versioned threshold rules`：配置结构校验、版本身份、单位和纯比较器 | `feat(monitoring): implement observation crossing state`：基线、UNKNOWN、采样去重、缺口和状态推进；四类 TEST DOUBLE | 核心无网络、金融公式或 SQLite；转换完全符合 Contract，换 Feature 不改规则代码 |
| **M3：提交可恢复机会事实** | `feat(monitoring): persist atomic opportunity transitions`：单实例 application SQLite、版本校验、原子状态/Event/初始 pending delivery；崩溃测试 | `feat(monitoring): poll query in a standalone runtime`：HTTP consumer、调度、独立前台 CLI、重启恢复 | 临时库和真实 Query HTTP 的 Skew 工程切片生成事件；重启无重复事件、失败无半推进；尚不发送 webhook |
| **M4：交付内部 webhook adapter** | `feat(monitoring): persist delivery attempts and recovery`：完善 delivery/attempt 状态、额度/退避、未知结果恢复；兼容 M3 已保存事件 | `feat(monitoring): deliver committed events by webhook`：独立投递循环、HTTP adapter、超时/重试/脱敏 | 只投递已提交事件；通知阻塞/失败不改机会判断；稳定 Event ID 有限重试，送达不确定性可查 |
| **M5：完成工程交付** | `test(monitoring): verify isolated end-to-end recovery`：隔离端到端/故障测试接入现有 offline Harness，扩展必要入口依赖检查 | `docs: publish monitoring usage and evidence`：真实可执行手册、Acceptance 证据与限制、结束本计划活动导航 | 新人按手册可配置/运行/恢复；证据可定位；未验实盘/通知单列，不能关闭主线 MVP |

M3 的初始 delivery 记录是保证事件与待发送事实原子成立所需；M4 补齐实际尝试与发送，不重建事件或更换 event_id。M1 新增 Query 生产文件时同步实际 Docker COPY/白名单与 harness 输入清单，保持现有三个镜像的隔离，不把 Monitoring 塞入 Query 镜像。

实施按职责作最少文件拆分：Query 薄 Feature service；Monitoring 纯核心、application store、runtime/HTTP 和通知 adapter。不要为了目录对称或未来插件创建空模块。运行常量与接口服从 Contracts；具体 SQL 表布局、内部函数命名不成为另一份业务规范。

## 3. 验证安排

| 阶段 | 必须取得的验证 |
|---|---|
| M0 | `python3 harness/run.py docs`、`git diff --check`；人工核对 authority、当前/待实现用词、与原计划一致；diff 仅涉及文档 |
| M1 | 定向 Feature/service/HTTP 回归、完整 Query 回归及 `python3 harness/run.py analytics`（含 analytics-contract）；新增镜像输入时 `packaging` |
| M2 | 不需要运行 Query/Collector 的纯核心 TEST DOUBLE 测试；配置/比较与全部转换表场景 |
| M3 | 临时真实 SQLite、固定时钟、随机 loopback 端口的 Query HTTP；单实例锁、事务故障注入、实际进程重启及规则版本恢复 |
| M4 | 本地 webhook TEST DOUBLE 接收端，记录实际请求；超时/非 2xx/崩溃恢复和评估独立推进 |
| M5 | `python3 harness/run.py offline`，加入新定向回归及隔离实际进程闭环；docs/diff；若修改构建输入补 packaging |

每个测试明确数据来源，不读取真实 INI/Raw/参考包、不连接真实 CTP、不发送真实 webhook；需要真实 SQLite/HTTP 不等于需要真实行情。使用临时目录、随机端口及 TEST DOUBLE SDK/报价/参考包；生产无测试绕过开关。

关键场景必须覆盖：

- 比较与状态：四个运算符的等号边界、单位不匹配、非有限数值、首次 MATCH、持续 MATCH、解除重入；UNKNOWN 两端两种 crossing 和缺口解释。
- 采样与质量：同位置 revision 修订、旧响应、UNKNOWN 后同位置首次有效；历史/休市、未封口、缺参考、PARTIAL 但合格 Skew、当前陈旧、404/503；不放宽 Skew 既有质量和 oracle 容差。
- 持久化：状态/Event/pending delivery 提交前后崩溃、重启、双实例、Rule revision/停用/重新启用、应用库失败；证明无半推进和重复 Event。
- 投递：2xx、非 2xx、超时、接收后未登记成功即崩溃、次数耗尽、重启续投和未知结果；同 Event ID 可重复投递，但不新增机会事实。
- 隔离：通知网络阻塞时评估继续；Query/Monitoring 停止时隔离 Collector 继续 Raw 提交；停止只收尾测试自有进程，原采集事实保留。

M5 完整闭环使用 TEST DOUBLE 行情源 → 隔离 Collector/Raw → 真实 Query/Feature HTTP → Monitoring application SQLite → 本地 webhook 接收端；构造不同逻辑采样位置的 NOT_MATCH/MATCH 验证一次事件，重复满足不产生新事件。保持已有冻结数值样本，不由生产代码生成 expected。

Harness 父进程超时/中断必须清理本测试创建的子进程，不能遗留脱管进程或误伤其他运行实例。不调用真实 native/systemd/Docker 管理器证明隔离。M0 不执行 analytics/offline/native/browser/packaging/docker；这些没有因文档检查通过而被验证。

结果按 Harness 记录 HEAD、dirty patch、环境、数据来源及日志哈希，未执行/缺依赖/跳过不能写 PASS。本地 webhook 成功不证明用户收到真实消息，Skew 合成回归不证明官方参考与真实输入已可用；对应缺口唯一登记 Acceptance。

## 4. 交付与计划生命周期

每个 Goal 完成时报告 commits、所执行测试及剩余证据，不自动关闭其他 milestone。后续状态从 Git/Acceptance 核对，不根据本表猜测已经实现。M0 两个 commits 完成后即停止本次工作。

M3 起在拟新增 `monitoring/README.md` 维护已经可用的配置/启动/停止与检查方式；M4 后补 target 环境引用和失败排障；M5 在 Operations 链接实际运行/恢复说明。README 不复制领域状态机。不要在 CLI 尚未实现时将建议命令写成当前操作能力。

M5 完成后本文标记完成并移除 docs/README 活动导航；长期接口和不变量留在对应 Contracts，当前证据留在 Acceptance，历史从 Git 追溯。不得新增 `docs/tasks/` 或按 commit 积累过程 specs。

## 5. 停止与重新设计条件

以下情况只停止受影响部分，保留工作和证据，说明冲突 authority 并回到设计，不能静默扩大范围：

1. 需要新增现货源、生产 basis/return/ATM IV、替代模型或放宽 Skew 同步/新鲜度/数值容差。
2. 需要 Monitoring 读写 Raw、Query 反向依赖 Monitoring、Dashboard 判断规则、Notification 复判或交易执行。
3. 需要拆顶层 Analytics 包、消息队列、独立通知服务或更复杂触发策略来完成本版。
4. 需要接管现有部署、修改 Compose/systemd/developer runner、清理真实配置/数据/flow/日志或对真实服务取证。
5. 新代码基线与已冻结时间、状态、身份或事务要求不一致，不能通过范围内 additive 修改兼容。

普通缺依赖、测试失败、端口占用或未取得现场证据不自动成为设计变更；安全修复范围内实现，或如实报告 NOT_RUN。不得靠更换 oracle、删除失败样本或把 TEST DOUBLE 称为生产支持来通过验收。
