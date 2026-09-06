# T11 — 最小 JS 看板与双容器部署

- 前置：T10 已提交。
- 目标：一条部署命令启动独立 Collector 和 query，浏览器查看服务健康与采集数据量。
- 范围：无框架静态页面、5 秒轮询、状态/日数量/合约数据展示；Compose 同一 bind mount 的 rw/ro 权限、localhost HTTP、独立健康检查；部署脚本和文档更新。
- 验证：HTTP 实际进程端到端读取合成 Collector 输出；JS 更新/断线/恢复/空数据；Python 与 Collector 独立停启；共享数据持续更新、停机后可读；部署/Compose 回归和隔离双容器 smoke test。真实 Docker 不可用需明确记录。
- 完成记录：待执行。
