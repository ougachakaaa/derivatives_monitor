# 历史证据归档

这里只保存历史验收观察和来源追踪，不保存第二套现行设计。当前目标与约束从[文档入口](../README.md)阅读，当前是否收尾由[验收矩阵](../acceptance.md)判断。

| 历史记录 | 日期/范围 | 解释边界 |
|---|---|---|
| [Collector](acceptance/Data_Collector_Acceptance_CN.md) | 早期独立采集与离线验收 | 当时前置受阻，不代表后来的实连仍失败 |
| [Docker](acceptance/Data_Collector_Docker_Acceptance_CN.md) | 初版部署 | 早期 Engine 不可用；后续容器证据见读路径/夜盘报告 |
| [Read Path](acceptance/Read_Path_Acceptance_CN.md) | 2026-09-07，原生/浏览器/后补容器 | 合成 SDK；旧 8080 宿主端口与临时地址不作当前运行说明 |
| [CFFEX 覆盖](acceptance/CFFEX_Coverage_Acceptance_CN.md) | 2026-09-07，714 合约短时实连 | 当日覆盖，不是永远固定合约数或三日稳定性证据 |
| [15 秒物化](acceptance/Collector_15s_Snapshot_Acceptance_CN.md) | 2026-09-07，默认采样语义 | 默认时钟实测与合成快时钟分开 |
| [SHFE 夜盘](acceptance/Market_Session_SHFE_Acceptance_CN.md) | 2026-09-07/08，多市场和部分真实夜盘 | 跨午夜连续实测待验，原临时 live 库已丢失；只保留当时摘要 |
| [Market State](acceptance/Market_State_Read_Model_Acceptance_CN.md) | 2026-09-08，46 项 Query 测试 | 离线真实 SQLite；没有 Analytics/生产负载实测 |

归档正文保留原历史结论，链接迁移并加历史状态提示。提及 `collector/logs/`、`collector/tmp/`、`/tmp/` 的文件可能只在当时机器存在；无原件不能宣称当前可重现。可运行验收入口统一到 [Harness](../../harness/README.md)。

## 文档迁移记录

整理基于 Git `56dcb4b`：

- `docs/Derivatives_Monitor_Phase1_Data_Collector_Architecture_CN.md` 的长期所有权/独立性/事实边界合并为[当前架构](../../ARCHITECTURE.md)。
- `Data_Collector_Constraints_CN.md`、`Read_Path_Constraints_CN.md`、`Data_Collector_Docker_Constraints_CN.md` 合并为 `docs/contracts/` 下对应长期契约；过时的单容器、无 Python/JS 部署限制由已经实现的三服务设计替代，C++ 无下游依赖的边界保持。
- `Market_Calendar_Session_Design_CN.md` 与 `Market_State_Read_Model_Design_CN.md` 转为同目录长期契约，保留时间/质量/清单/SQL 语义，删除实施顺序与逐任务提交要求。
- `docs/tasks/` 中 data-collector、market-session、market-state 全部过程 specs 从工作树删除。历史任务/commit 线索可用 `git show 56dcb4b:docs/tasks/data-collector/README.md` 等读取；不继续将它们作为活动约束。
- `docs/#TODO#.md` 的汇报模式、Skew、技术栈和部署事项归入[MVP 范围和后续事项](../mvp.md)，不再维护分散 TODO。
- 旧 `*Acceptance_CN.md` 移到本目录 `acceptance/`；中信建投原始 DOCX/历史 CHM 从 `fb25dc9` 恢复到[参考档案](../references/README.md)。`experiments/` 完全不动。

本轮整理与 harness 验证记录见[整理验收](reorganization-20260908.md)。本轮完成只意味着文档/架构/harness 整理完成，不代表业务 MVP 已完成。
