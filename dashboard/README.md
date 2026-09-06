# React 采集看板

独立 React/Vite 项目。Python 只提供 JSON；生产镜像由 Nginx 提供页面，并将同源 `/api/` 转发到 `query:8000`。前端不挂载 SQLite、CTP 配置或 Docker socket。

全栈部署，在仓库根目录执行 `./collector/scripts/deploy.sh up`，浏览器打开 **http://localhost:8080**。后端直接访问 **http://localhost:8000/docs**。两个 HTTP 端口都只绑定宿主回环地址。

本地前端开发需要 Node 22.12+：

```bash
npm ci
npm run dev
```

默认代理本机 8000 端口 FastAPI；用 `QUERY_URL=http://127.0.0.1:其他端口 npm run dev` 调整。构建 `npm run build`，组件测试 `npm test`；部署镜像构建会运行这两项，最终镜像不含 Node 或测试依赖。

页面每 5 秒查询：Python API 可达性、Collector 主循环心跳、CTP 连接/登录/订阅、每日 snapshot 数量及合约明细、最近 20 行。单次请求 4 秒超时；API 断线会清除绿色状态，数据查询失败会清空数值而不展示旧值。休市无行情不等于进程停止。日文件大小包括 WAL，不等于逻辑数据大小；最后接收时间统一显示北京时间。run 来源包含 `TEST DOUBLE` 的数据是测试数据。

真正的浏览器验收（还需要原生 Collector Release 构建和 query Poetry 环境）：

```bash
npx playwright install chromium
# 若系统缺浏览器依赖，按 Playwright 的提示安装系统依赖后再运行。
cd ..
python3 tests/read_path_smoke.py --browser
```

此测试启动临时合成 Collector、真实 FastAPI、Vite 与 Chromium，验证页面、断线恢复和独立停启。使用临时数据，不读取真实账号或修改 `collector/data/`；它不等价于 Docker 或真实 CTP 验收。容器验收执行 `bash tests/read_path_docker_smoke.sh`。
