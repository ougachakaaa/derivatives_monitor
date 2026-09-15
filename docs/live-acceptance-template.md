# MVP 现场验收记录模板

复制到新的持久证据目录，填写完成后提交脱敏摘要并从[验收矩阵](acceptance.md)链接。初始状态全部 NOT_RUN；没有原始证据、只有截图或只有“登录成功”都不能直接记为通过。

## 环境与来源

- 验收日期/时区/执行人：待填
- Git commit、dirty 补丁身份、镜像/构建身份：待填
- 机器/OS/CPU/内存/磁盘、原生或 Docker、依赖版本：待填
- 数据目录与证据归档目录（不得只用 /tmp）：待填
- 非敏感配置：固定 15 秒 Bar/1 秒 grace、产品/月/精确清单、Universe generation 和哈希、Calendar 版本：待填
- 数据来源：REAL_CTP 或 TEST_DOUBLE（分别记录，不混用）；SDK 版本/run ID：待填
- 脱敏说明及原件访问位置：待填；不记录密码

## G1/G2：连续运行与夜盘

记录三个完整交易日的起止、服务重启/断线原因、行情空洞解释。AU/AG 至少覆盖 21:00、23:59、00:00、02:30、次日日盘及下一真实 TradingDay；每个时点保存以下记录。交易时段以当次审核日历为准。

| 检查时刻 | TradingDay / bucket / last event | receive / committed time | 日文件 schema / Bar identity / run | 订阅/callback/Bar/partial/late 计数 | 质量/缺口与原因 | 原件路径/SHA-256 |
|---|---|---|---|---|---|---|
| 待填 | | | | | | |

结论：NOT_RUN。不可用合约与数据缺失的业务影响：待填。

## Collector 第一阶段可靠性验收

本节按 [Collector 第一阶段完成条件](mvp.md#collector-第一阶段完成条件)单独判定；可引用上节连续运行证据，不能代替后续整体 MVP 门槛。真实环境与 TEST DOUBLE 分开记录，能力未实现或未执行时保留 NOT_RUN。

### 部署前提与连续运行证据

- 固定机器、部署方式、版本及连续三个完整交易日起止；日盘、夜盘、跨午夜、TradingDay rollover 对应证据：待填
- 系统时间同步服务、同步状态/偏移及检查时刻：待填
- Market DB、Runtime DB、必要 flow 的持久目录/挂载；运行 UID/GID 与可写检查：待填
- 起止及期间磁盘余量、inode、各日库/运行库及 sidecar 大小与增长：待填
- Docker 或原生日志的有效轮转/容量/保留参数及实际占用：待填
- Supervisor 的 stale 阈值、检查周期/超时、启动及终止宽限、强制终止、重启等待/退避/限制、故障至新进程启动总上界：待填

### 故障与恢复

| 场景 | 必须核对的事实 | 故障/检测/终止/新进程/恢复采集时刻及耗时 | Runtime/Market 原件路径与身份 | 结论 |
|---|---|---|---|---|
| 连续运行含静默窗口 | Runtime 观察连续；无 Tick 窗口有记录，接收/提交计数与数据库事实可对照 | 待填 | 待填 | NOT_RUN |
| 真实或受控断网及网络恢复 | 断线期间主循环观察持续，连接/登录事实正确；同 run reconnect/login/resubscribe 后 Bar 继续产生 | 待填 | 待填 | NOT_RUN |
| Collector 强制终止 | Supervisor 实际重启，持久新 run，重新连接并恢复采集 | 待填 | 待填 | NOT_RUN |
| 主循环 stall | Heartbeat 停止，stale 后实际终止/重启，新 run 恢复采集；只有 unhealthy 不算通过 | 待填 | 待填 | NOT_RUN |
| 异常退出后持久性安全 | 完整性检查；故障前已提交 Bar 集合逐行不变、canonical identity 不重复、同日可跨 run 追加、日身份不混写 | 待填 | 待填 | NOT_RUN |

每次演练保存故障前后 run、Runtime interval 范围及最低事实（按 [History Contract](contracts/collector-health.md#runtime-snapshots)）、Market canonical identity/提交时间、重启次数和相关日志。明确注入方式与外部观察时间，比较约定恢复上界与实测；恢复采集须有新增成功 Market commit 证据。

对已提交 Bar 使用故障前固定行集合或 revision 的只读导出及哈希对账，不能因恢复后新增行导致整库哈希变化就认定历史被修改。区分未提交内存损失、断网真实缺口与已提交事实损坏；按 [History 解释边界](contracts/collector-health.md#历史解释边界)保留未知，不用当前健康追认缺失窗口。另记 Runtime/Market 备份副本、schema、完整性结果和 run 关联检查。

### 阶段结论

环境、连续运行、CTP 恢复、进程恢复、heartbeat 恢复、持久性安全逐项：NOT_RUN。仅凭持久化事实和日志能否回答 [阶段问题](mvp.md#collector-第一阶段完成条件)：待填；未知及其证据限制：待填。Collector 第一阶段总判定：NOT_RUN；未完成项不能由整体其他模块或 TEST DOUBLE 的通过抵消。

## G3：指标对账

按[冻结的 mo-skew-25d-v1](../analytics/contracts/analytics-skew.md)记录契约/算法版本、ReferenceBundle及输入身份。至少10个不同真实时点（≥6可计算、≥4异常；定点扰动需另标SYNTHETIC_MUTATION），按契约固定IV/delta/F/Skew容差及选点规则对账；不能用同一实现计算两次冒充独立验证，不得在看到误差后放宽阈值。

| 时点/scope | revision/Universe/Calendar/输入 ID | 参数与版本 | 系统值或失败原因 | 独立值/预期失败 | 差异/阈值/结论 | 证据 |
|---|---|---|---|---|---|---|
| 待填（至少10行） | | | | | | |

结论：NOT_RUN。相同固定输入重放输出是否一致：待填。

## G4：三次日常观察

| 日期/观察任务 | 理解对象/指标/变化/时间/可信度所用秒数 | 是否借助 SQL/日志 | 当前/分钟回看是否可用 | 问题/截图证据 |
|---|---|---|---|---|
| 第1次 | | | | |
| 第2次 | | | | |
| 第3次 | | | | |

结论：NOT_RUN。

## G5/G6：恢复与交付

| 演练 | 前后 run/行数/最大 id/哈希 | 预期与实际恢复 | 证据/耗时 | 结论 |
|---|---|---|---|---|
| CTP 断线重连 | | | | NOT_RUN |
| Collector 异常退出后重启 | | | | NOT_RUN |
| Query 停止而采集继续/重启恢复 | | | | NOT_RUN |
| 正常停机备份→隔离恢复→历史 Query/指标重放 | | | | NOT_RUN |
| 声明部署方式的最终版本部署 | | | | NOT_RUN |

[备份恢复规程](operations.md)；不覆盖生产目录，不删除 WAL。记录工程 verification 报告路径及日志哈希。恢复后验证已提交数据保留；尚未提交窗口可能损失与断线无回补必须明确。

## P1/P2：性能

- 一天真实库：交易日/字节/行数/完整目标月成员数/副本身份，冷热条件及并发=1：待填
- ≥100 次核心业务请求的原始耗时、成功/失败/超时总数及 P95（nearest-rank，排序第 ceil(0.95*n) 项）：待填
- 要求成功请求 P95 ≤2秒，同时报告全部失败，不能隐藏失败来达标；业务不可用需另行判失败。
- 活跃有效报价 canonical Bar identity 对应 bucket/last-event/receive/commit/浏览器显示时间、时钟同步依据、延迟与最大值：待填
- 接收至显示目标 ≤30秒，陈旧输入需标不可用；不以休市无行情评价延迟：待填

结论：NOT_RUN。

## 最终判定

逐项 G1–G6、P1/P2：PASS / FAIL / NOT_RUN；链接证据并说明限制。阻断问题清单：待填。只有所有必需门槛证据充分且无阻断问题才能声明 MVP 收尾；合成工程通过不自动改变现场门槛。
