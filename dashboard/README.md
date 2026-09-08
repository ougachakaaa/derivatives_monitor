# React 采集看板

[系统架构](../docs/architecture.md) · [MVP 汇报页目标](../docs/mvp.md) · [验收矩阵](../docs/acceptance.md) · [Harness](../harness/README.md)

独立 React/Vite 项目。Python 只提供 JSON；生产镜像由 Nginx 提供页面，并将同源 `/api/` 转发到 `query:8000`。前端不挂载 SQLite、CTP 配置或 Docker socket。

当前 WSL 原生部署使用 `./collector/scripts/native.sh up`，Windows 打开 **http://localhost:8101**。页面增加 CFFEX 各品种/月的覆盖统计，展示清单来源和过期状态、订阅失败及已订阅暂无推送的区别。

Docker 全栈部署，在仓库根目录执行 `./collector/scripts/deploy.sh up`，浏览器打开 **http://localhost:8101**。后端直接访问 **http://localhost:8000/docs**。两个 HTTP 端口都只绑定宿主回环地址。

本地前端开发需要 Node 22.12+：

```bash
npm ci
npm run dev
```

开发服务固定监听 `127.0.0.1:8101`，端口占用时报错。默认代理本机 8000 端口 FastAPI；用 `QUERY_URL=http://127.0.0.1:其他端口 npm run dev` 调整。构建 `npm run build`，组件测试 `npm test`；部署镜像构建会运行这两项，最终镜像不含 Node 或测试依赖。

页面每 5 秒查询：Python API 可达性、Collector 主循环心跳、CTP 连接/登录/订阅、每日 snapshot 数量及合约明细、最近 20 行。单次请求 4 秒超时；API 断线会清除绿色状态，数据查询失败会清空数值而不展示旧值。休市无行情不等于进程停止。日文件大小包括 WAL，不等于逻辑数据大小；最后接收时间统一显示北京时间。run 来源包含 `TEST DOUBLE` 的数据是测试数据。

真正的浏览器验收（还需要原生 Collector Release 构建和 query Poetry 环境）：

```bash
npx playwright install chromium
# 若系统缺浏览器依赖，按 Playwright 的提示安装系统依赖后再运行。
cd ..
python3 tests/read_path_smoke.py --browser
```

此测试启动临时合成 Collector、真实 FastAPI、Vite 与 Chromium，验证页面、断线恢复和独立停启。使用临时数据，不读取真实账号或修改 `collector/data/`；它不等价于 Docker 或真实 CTP 验收。容器验收执行 `bash tests/read_path_docker_smoke.sh`。

无需真实 CTP 配置即可查看合成闭环：仓库根目录执行 `KEEP_RUNNING=1 bash tests/read_path_docker_smoke.sh`。通过验收后保留三容器，输出随机 localhost 端口及停止脚本；数据和镜像均隔离，来源明确 TEST DOUBLE。

市场时段表独立请求 `/api/sessions`，按交易所/品种显示逻辑交易日、开市/休息/休市/未知、日夜盘与连续交易/集合竞价，以及最近和下一连续时段。可同时显示 CFFEX 休市与 SHFE AU/AG 夜盘开市；时段接口失败清空旧表，保留单独的服务健康结果。市场时段不用于自动启停或告警。覆盖表增加交易所及SHFE清单目标日期，原订阅/接收/缺口诊断保留。
