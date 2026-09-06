# 第一阶段实现计划与 Task Specs

所有 Task 均受 [设计约束](../../Data_Collector_Constraints_CN.md) 约束。严格按 T0 → T5 执行；每项验证完成后单独 commit，验证记录写回相应 Spec。遇到实盘时段/网络限制，明确区分实现验收与真实行情验收。

| Task | 小闭环 | 预期 commit |
|---|---|---|
| [T0](T0-design.md) | 现状审查 → 约束与完整 Specs | `docs(collector): define constraints and phased task specs` |
| [T1](T1-bootstrap.md) | 复用 CTP 基础 → 独立可构建、可校验配置的入口 | `refactor(ctp): share client support and bootstrap collector` |
| [T2](T2-state.md) | SDK update → 有界状态 → 可验证 snapshot | `feat(collector): materialize trading-day market snapshots` |
| [T3](T3-storage.md) | snapshot → 日 SQLite → 独立只读验证 | `feat(collector): persist snapshots to daily SQLite` |
| [T4](T4-runtime.md) | CTP 生命周期 → 状态采样 → 持久化与停机 | `feat(collector): integrate resilient CTP collection runtime` |
| [T5](T5-acceptance.md) | 完整回归、现场探测、运行与查询手册 | `test(collector): verify standalone collection and document operations` |

不改动无关 `experiments/data_coverage`，不添加 Docker/后端。上游设计文档原样纳入 T0，便于所有约束链接随 commit 独立审查。
