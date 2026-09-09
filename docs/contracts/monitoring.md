# Monitoring / Opportunity / Notification 契约 v1

状态：**FROZEN / 待实现**，2026-09-09。本契约冻结用户机会检测、状态推进、事件与投递失败语义；当前证据只登记在 [Acceptance](../acceptance.md)。产品与永久不交易边界见 [MVP](../mvp.md)，模块和数据所有权见 [Architecture](../architecture.md)，行情输入只经 [Feature Contract](features.md)。

## 1. Rule 与 Evaluation

| 模型 | 必需语义 |
|---|---|
| Rule | 稳定 `rule_id`、正整数 `revision`、`enabled`、一个 Feature 请求定义（ID/scope/parameters）、一个 comparator、有限 threshold、unit、一个 target ID |
| Evaluation | 规则 ID/revision、评估时刻、Feature 身份及证据、`MATCH / NOT_MATCH / UNKNOWN`、原因 |
| Evaluation State | 最近有效判断及其证据、最近接受的 sample_key/effective_at、最近评估诊断、未闭合缺口、递增 transition 序号 |
| Opportunity Event | 不可变 event_id、规则快照及版本、transition 序号、前后有效 Evaluation 证据、触发值/单位/阈值/原因、缺口、提交时间 |
| Notification Delivery | event_id、target ID、投递状态、尝试次数及每次尝试的时间/结果/脱敏错误；与 Event 独立 |

v1 Rule 只支持一个标量与常量阈值的 `< / <= / > / >=` 比较。阈值必须有限且不是布尔值，unit 必须与 Feature 单位完全一致；不隐式换算、不用显示舍入或额外容差判断。请求时刻由 runtime 每轮注入，不属于静态 Rule。

Rule Engine 只消费通用 Feature envelope，不能读 Raw、调用金融公式或依赖 Skew/MO/IM 字段。Feature ID、scope/parameters 必须与本次请求一致。schema/身份/单位/时间或值不合法的响应为 UNKNOWN，不能做比较。

只有 `status=OK`、有限 value、`historical=false`、`current_usable=true` 且采样身份/时间成立的响应可得到 MATCH 或 NOT_MATCH。输入是否当前可用由 provider 按指标契约决定；Monitoring 不以 healthz、HTTP 200、非 null 或通用 Market State usable 替代它。请求失败、超时、休市、历史、陈旧、不可算及不可解释响应均为 UNKNOWN，并记录原因。

## 2. 基线、crossing 与采样去重

纯状态推进必须显式输入 prior state、Rule、Evaluation 和当前时间；不隐含读取网络、数据库或时钟。

| 最近有效状态 | 新有效判断 | 新状态 | Opportunity Event |
|---|---|---|---|
| 无 | NOT_MATCH 或 MATCH | 只建立首次基线 | 无 |
| NOT_MATCH | NOT_MATCH | 更新有效证据 | 无 |
| NOT_MATCH | MATCH | 推进状态和 transition 序号 | 一次 |
| MATCH | MATCH | 更新有效证据 | 无 |
| MATCH | NOT_MATCH | 推进状态和 transition 序号，允许后续重入 | 无 |

transition 序号从 0 开始，只在两种有效判断之间切换时递增；初始基线、UNKNOWN、重复满足不递增。每个规则版本独立编号。

UNKNOWN 更新诊断及缺口，不替换最近有效状态/证据和采样位置。恢复后的有效 Evaluation 关闭缺口：`NOT_MATCH → UNKNOWN → MATCH` 生成带缺口说明的 Event；`MATCH → UNKNOWN → MATCH` 不重复生成。缺口保存起止观测时间和原因，不声称完整记录全部失败请求。进程重启亦记录从上次持久评估到恢复评估的未观测间隔。

crossing 只表示两次有效观测之间发现条件由不满足变为满足。Event 必须保留两端时间和值，不能把检测时间说成市场精确穿越时间，也不能声称捕获了间隔内所有 crossing。

同一规则版本每个逻辑采样位置最多接受一次有效判断：

- 先检查通用有效性；UNKNOWN 不消耗采样位置，因此同一位置恢复可用后可首次进入判断。
- 有效响应的 sample_key 与已接受键相同，或 effective_at 不晚于已接受位置时，不再推进有效状态，不用修订结果覆盖先前证据；记录重复/旧响应诊断即可。
- 后续位置即使数值未变，也更新最近有效证据；持续 MATCH 仍不产生 Event。
- Skew 的分钟/revision 含义由 [Feature Contract](features.md)决定；引擎不解析分钟或 raw_revision。

规则状态跨正常重启、午休和交易日延续，不按自然日清零。停机期间不枚举历史补发机会，恢复只请求当前输入；可能漏掉未被轮询观察的短暂机会。已经提交但未投递的 Event 恢复投递，不属于历史机会补算。

同分钟 Raw/参考修订可能改变可重建指标，却不改写系统当时接受的判断或已提交事件。这是运行时机会记录，不是随修订重新生成的回测事件流。

## 3. 配置与 application state

用户维护本地版本化 JSON，启动时完整校验并保存已应用 Rule 版本；v1 无热更新、管理 API 或 UI。重复 rule_id、未知比较器、非法 threshold/unit、缺 target 等配置错误阻止启动，不部分应用配置。

规则定义（包括 scope、阈值、enabled、target ID）变化必须提高 revision；相同 revision 不同内容或回退旧 revision 均拒绝。同一未变化的有效版本重启恢复状态；新版本重新建立基线。停用再启用必须新版本；从配置删除规则视为停用，重新加入不得借旧 revision 恢复基线。保留旧规则、状态和事件用于审计，不覆盖历史。

通知 target 是独立本地配置，Rule 仅引用 ID。含秘密的 URL/token/header 值仅通过环境变量引用，不能进入 Rule/Event/日志/Git。target ID 表达稳定接收目标；更换接收目标使用新 ID，旧待投递项不得静默改投新目标。旧事件可在规则停用或换版本后继续投递；缺少其 target 配置时保留 pending 并报告阻断，不删除、不改目标、不计为网络尝试。

Monitoring 在专属目录维护一份 application SQLite，保存 Rule 版本、Evaluation State、不可变 Event、Delivery 和 Attempts。不放入 Collector 数据目录、不写 Raw、不复制连续行情；事件中的 Feature 证据快照用于解释当时的应用事实，不是新的行情 authority。

只持久化最近评估诊断、有效状态/证据、缺口与 Event 必需的前后证据，不要求完整轮询日志库。Event 保存 Feature 的完整 evidence，不仅保存可能失效的临时 URL 或单个哈希。日后复算可以核对事件输入，但不能修改已有 Event。

同一 application store 只有一个 Monitoring runtime writer，采用单实例锁、短事务和 schema version；第二实例拒绝启动，不接管第一实例。未知 schema、损坏、锁或写入失败必须明确失败，不清库、不自动重置、不降级为仅内存通知。无需引入分布式锁或独立数据库服务。

## 4. 原子提交与故障隔离

一次状态推进在同一 SQLite 事务中保存新 Evaluation State；若发生 crossing，同事务插入 Event 及初始 PENDING Delivery。以 `(rule_id, revision, transition_sequence)` 唯一约束防止重复创建 Event，event_id 创建后稳定且全局唯一。发送只读取已提交 Event。

事务提交前失败或进程崩溃，状态/事件/初始投递项全部不成立；提交后崩溃则全部可恢复。提交是否成功不确定时从库恢复，不用内存假设补发或重复插入。应用库不可写时停止状态推进并报告失败，不通过通知补偿未提交事件。

单规则无效输入、provider 失败只影响相关规则，其他规则继续评估。Query 不可用可导致全部规则 UNKNOWN，但不能调用管理器重启 Query 或 Collector。应用库的共同故障属于 Monitoring 故障域，不影响 Collector 的数据写入路径。

## 5. Runtime 与时间

首版独立前台进程内设评估循环与一个投递循环；二者独立调度，通知网络等待不能阻塞规则评估。共享 SQLite 仅通过短事务协调，任何网络请求期间均不持有数据库事务。部署和本地进程范围见 [Deployment Contract](deployment.md)。

- 默认每 5 秒轮询。同轮相同 Feature 请求复用一次结果（包括失败），不跨轮缓存；每轮显式固定 requested_at。
- 同一规则串行评估；周期超时不积累待补跑任务，不并发追赶历史周期。实际周期可长于间隔，需可见地报告延迟。
- Query 与 webhook 请求均有界，默认超时 5 秒。失败请求不复用旧结果；评估与发送时间分别记录。
- 时间字段带时区；采样顺序使用 Feature effective_at，不能以源 UpdateTime、自然日或本地字符串猜测。调度等待使用单调时钟，不因墙钟调整补跑机会。
- 轮询不是 tick 订阅，既有采样/封口/新鲜度要求可能使某些周期或分钟无有效样本；不为提高通知率修改 Analytics Contract。

正常停止结束本进程循环并关闭自有资源，不清理库或调用其他组件的服务管理器。崩溃恢复依据持久状态，不依赖上次终端日志。

## 6. Notification adapter 与 delivery state

Notification 只消费已成立 Event 和 target 配置，不重新请求 Feature、不判断 Rule、不改变 Event。v1 一个 Event 对应一个 target；逻辑唯一键 `(event_id, target_id)`。通知渠道的增加只新增 adapter，复用事件与 delivery 生命周期。

webhook 用 HTTP POST 发送 JSON：`schema_version=1`、`event_id`、`event`（规则快照、前后 Evaluation、时间/值/原因/缺口及追溯证据）、`delivery`（target ID、attempt number、attempted_at）。重试的 event 内容和 event_id 相同，delivery 尝试信息变化。不发送凭据字段，HTTP 2xx 仅表示接收端接受，不能称为人已阅读或采取行动。

| Delivery 状态 | 语义 |
|---|---|
| PENDING | 已有已提交 Event，等待首次发送或重试到期 |
| SENDING | 已持久登记本次尝试，网络结果尚未完成登记 |
| SUCCEEDED | 一次尝试收到 HTTP 2xx 并成功记录 |
| FAILED | 尝试次数已耗尽；保留失败或送达不确定性 |

首次立即尝试，最多 3 次；第 1 次失败后等待 5 秒，第 2 次失败后等待 30 秒再尝试。所有非 2xx、连接失败和超时都按有限重试规则处理，不另加无限后台重试；不跟随重定向把事件发送到另一个目标。每次网络发送前先提交 Attempt 记录并计入次数，完成后提交结果和下一次 due time。

Attempt 记录开始/结束时间、HTTP 状态（若有）、结果 `ACCEPTED / FAILED / UNKNOWN` 和脱敏错误。超时、连接结果不确定或重启发现 SENDING 时，保留 UNKNOWN；重启不得假定失败未送达。未完成尝试已消耗一次额度；按对应退避安排剩余尝试，额度耗尽进入 FAILED 并保留 UNKNOWN 证据。FAILED 只表示本地停止尝试，不保证接收端未收到。

接收端可能已接受而发送端在登记成功前崩溃，因此允许重复投递，接收端可按 event_id 去重；不承诺 exactly-once 或保证至少成功送达一次。网络结果记录失败时不修改 Event，不无记录地再发送；恢复按已持久尝试处理。

重启继续已提交 pending 投递，保留原事件时间并另给实际尝试时间，明确迟到；v1 不新增过期抑制、人工重发或撤回机制。成功/失败都不能反向改变 Rule evaluation state。

## 7. 扩展与验收边界

去重来自采样位置、状态机和事务唯一性，不借 cooldown 替代。未来持续满足、cooldown、hysteresis 属于版本化触发策略与 Evaluation State；市场 rolling window 属于 Feature。v1 不预建未使用的字段、表、策略框架或复合规则表达式。

必须覆盖首次基线、四种比较的等号边界、单位/非有限值拒绝、持续满足/重入、UNKNOWN 前后两种 crossing、同分钟修订/旧响应、重启/规则修订/停用、原子提交前后崩溃、双实例及库失败。通知验证成功、非 2xx、超时、接收后崩溃、次数耗尽和重启续投；证明发送等待不阻塞判断，下游退出不影响隔离 Collector 继续提交。

basis、5 分钟 return、ATM IV 和 Skew representative cases 使用同一纯引擎；前三者只用标明 TEST DOUBLE 的 Feature 输出验证接口，不把它们登记为生产指标。真实 Skew 的输入与官方参考验证仍沿用 [Analytics Contract](analytics-skew.md)。工程、现场和未执行证据分开登记 [Acceptance](../acceptance.md)，不得用通知闭环替代主线 MVP 验收。
