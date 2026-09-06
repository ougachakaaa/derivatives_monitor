# T11 — 最小 JS 看板与三容器部署

- 前置：T10 已提交。
- 目标：一条部署命令启动独立 Collector、query 和 dashboard，浏览器查看服务健康与采集数据量。
- 范围：独立 React/Vite 项目、Nginx 静态服务和同源 API 代理、npm 锁文件、5 秒轮询、状态/日数量/合约数据展示；Compose 同一 bind mount 的 rw/ro 权限、localhost HTTP、独立健康检查；部署脚本和文档更新。
- 验证：HTTP 实际进程端到端读取合成 Collector 输出；JS 更新/断线/恢复/空数据；Python 与 Collector 独立停启；共享数据持续更新、停机后可读；部署/Compose 回归和隔离三容器 smoke test。真实 Docker 不可用需明确记录。
- 完成记录：独立 React/Vite/Nginx 项目、三服务 Compose、一键部署和运维更新完成。4 项 React 组件测试、生产构建、真实 Chromium 断线恢复/移动布局、真实 C++/FastAPI 进程独立停启及 SIGKILL 心跳过期通过；8 项部署替身测试、4 项 SQLite CLI 回归、6 项 CTest、8 项后端测试、ShellCheck 和 Compose v2 解析通过。三容器隔离 smoke 脚本已提供；Docker Engine 不可用，实际调用明确 NOT RUN，容器验收尚待目标机。详见 [验收证据及命令](../../Read_Path_Acceptance_CN.md)。
