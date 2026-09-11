# React MO Skew 业务汇报

Dashboard 是独立 React/Vite 前端，用于展示 MO Skew 业务结果和运行诊断。它通过 JSON API 工作，不在浏览器内计算 IV / Skew；页面在系统中的位置见[系统架构](../ARCHITECTURE.md)，产品目标见 [MVP](../docs/mvp.md)。页面布局、轮询、显示、当前/历史交互与失败清值见[本级 Contract](CONTRACT.md)，公共 HTTP 协议和 wire shape 见[共享 Read Path](../docs/contracts/read-path.md)。

相关入口：[本级 Acceptance](ACCEPTANCE.md) · [Deployment Contract](../docs/contracts/deployment.md) · [Operations](../docs/operations.md) · [根 Acceptance](../docs/acceptance.md) · [Harness](../harness/README.md)

统一前台开发入口位于仓库根：`./dev doctor dashboard` 检查本组件，`./dev up dashboard` 运行本组件，`./dev up` 运行完整开发会话。参数示例和与持久部署的区别见 [Operations](../docs/operations.md#前台开发会话)；下面保留 Dashboard 自身的依赖安装、直接运行和测试用法。

## 本地开发

需要 Node 22.12+。从 `dashboard/` 目录执行：

```bash
npm ci
npm run dev
```

开发服务监听 **http://127.0.0.1:8101**，默认将 `/api/` 代理到本机 8000 端口的 Query。后端使用其他端口时：

```bash
QUERY_URL=http://127.0.0.1:18000 npm run dev
```

页面行为不在 README 重复，统一见[本级 Contract](CONTRACT.md)；API 字段与指标语义分别见[共享 Read Path](../docs/contracts/read-path.md)和 [Analytics / Skew Contract](../query/contracts/analytics-skew.md)。

## 构建与组件测试

```bash
npm test
npm run build
```

产物位于 `dashboard/dist/`。生产镜像由 Nginx 提供静态文件并代理同源 `/api/`；具体镜像、端口和挂载边界见 [Deployment Contract](../docs/contracts/deployment.md)。

## 持久部署完整系统

从仓库根目录选择一种方式：

```bash
# 原生 WSL
./collector/scripts/native.sh up

# Docker Compose
./scripts/deploy.sh up
```

浏览器默认打开 **http://localhost:8101**，FastAPI 文档位于 **http://localhost:8000/docs**。启动、停止、更新和恢复步骤见 [Operations](../docs/operations.md)；不要同时让两种部署方式写同一 Raw 目录。

## 浏览器与合成闭环测试

原生浏览器回归需要 Collector Release build、Query Poetry 环境和 Playwright Chromium：

```bash
cd dashboard
npx playwright install chromium
cd ..
python3 tests/read_path_smoke.py --browser
```

Docker 合成闭环：

```bash
KEEP_RUNNING=1 bash tests/read_path_docker_smoke.sh
```

`KEEP_RUNNING=1` 会保留隔离测试容器，并输出随机 localhost 端口及停止脚本。这些场景使用明确的 TEST DOUBLE；它们验证页面和集成行为，但不等价于真实 CTP、真实 Skew 值或 G4 日常使用验收。当前页面证据见[本级 Acceptance](ACCEPTANCE.md)，系统门槛见[根 Acceptance](../docs/acceptance.md)。

## 常见问题

- **8101 端口占用**：本地 Vite 默认使用 8101，可用 `npm run dev -- --port 18101` 显式调整；严格端口模式不会自动换端口。完整 Docker 部署使用 `DASHBOARD_PORT`，原生 systemd 当前固定为 8101。已有部署的停止操作使用对应管理入口。
- **页面显示 Query 请求失败**：先直接访问 Query `/healthz` 和 `/docs`，再检查 `QUERY_URL` 或 Nginx 代理。
- **页面没有 MO 月份**：检查 `/api/coverage` 的返回和 Collector Universe；不要在前端生成合约。
- **Skew 不可用或显示历史结果**：保留 API 返回的 reason、时间和参考身份，按 Query README 及相应 Contract 排查，不在浏览器中补值。
- **需要检查运行状态**：使用 `./collector/scripts/native.sh status` 或 `./scripts/deploy.sh status`，不要从页面单一状态推断 Collector 进程或市场活跃度。
