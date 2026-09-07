# T12 — 修复 Docker 环境并执行容器闭环验收

- 前置：T9–T11 已提交；用户明确授权解决当前 Docker/WSL 问题并跑通最小闭环。
- 目标：恢复当前 WSL 的 Docker Engine 访问，实际构建并验证 Collector → 共享 SQLite → FastAPI → 独立 React/Nginx。
- 边界：复用现有 Docker Desktop 与 WSL 2，不重装发行版、不清除用户数据；测试使用隔离项目和明确标记的合成 SDK；真实行情须单独确认前置和订阅，不把合成数据当实盘。
- 步骤：诊断并恢复 Desktop/集成 → 执行三容器及 Collector 生命周期 smoke → 修复实测问题并针对性回归 → 更新验收证据和启动说明。
- 验证：Linux Docker CLI/Compose 可访问 Engine；实际镜像构建测试、三服务健康、Nginx HTTP 数据增长、只读挂载、独立停启和数据保留通过。真实前置不可用时记录实际结果。
- 预期 commit：`test(monitor): validate the container read path on WSL`（必要修复随该闭环提交）。
- 完成记录：执行中。
