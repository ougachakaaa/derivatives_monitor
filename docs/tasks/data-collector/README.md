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

T0–T5 不改动无关 `experiments/data_coverage`，不添加 Docker/后端。上游设计文档原样纳入 T0，便于所有约束链接随 commit 独立审查。

## 后续 Docker 部署（用户已授权）

先提交 [部署约束](../../Data_Collector_Docker_Constraints_CN.md) 与以下 Specs，再按顺序逐项提交；不增加后端或改变采集链路。

| Task | 小闭环 | 预期 commit |
|---|---|---|
| [T6](T6-docker.md) | 源码 → 多阶段镜像与单服务 Compose | `build(collector): add Docker image and persistent Compose service` |
| [T7](T7-deploy.md) | 首次配置 → 构建预检 → 启动/运维 | `feat(collector): add one-command Docker deployment` |
| [T8](T8-docker-acceptance.md) | 隔离验收 → WSL 部署手册 | `test(collector): verify Docker deployment and document WSL operations` |

## 最小只读层与 JS 看板（用户已授权）

先提交 [读路径约束](../../Read_Path_Constraints_CN.md) 和 Specs；不改变 C++ 唯一 writer 边界。

| Task | 小闭环 | 预期 commit |
|---|---|---|
| [T9](T9-heartbeat.md) | C++ 主循环 → 可只读观察的心跳 | `feat(collector): publish independent runtime heartbeat` |
| [T10](T10-query.md) | 已有日文件 → Python 只读 HTTP | `feat(query): serve read-only daily market data over HTTP` |
| [T11](T11-dashboard.md) | React/FastAPI 三容器 → 浏览器状态和数量看板 | `feat(monitor): add minimal dashboard and shared-volume deployment` |

## Docker 实机恢复与补充验收

- [T12](T12-container-acceptance.md)：恢复 Desktop/WSL 集成并执行三容器和 Collector 生命周期验收；保留 T9–T11 的历史验证限制，以新证据更新当前验收结论。
