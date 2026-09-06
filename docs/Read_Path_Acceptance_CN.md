# 只读后端与独立 React 看板验收

验证日期：2026-09-07。约束见 [读路径设计](Read_Path_Constraints_CN.md)，步骤见 [T9–T11](tasks/data-collector/README.md)。所有行情样本来自明确标记 `CTP TEST DOUBLE - synthetic market data` 的合成 SDK；没有把它们当作真实 CTP 验收。

## 当前实现

```text
CTP → collector (C++) → 宿主 collector/data/YYYYMMDD.sqlite
                              ↑ 同目录，只读挂载 /data
                         query (FastAPI / Poetry)
                              ↑ /api/ 反向代理
                         dashboard (React / Nginx) ← Browser
```

三个项目各有 Dockerfile；一条 `./collector/scripts/deploy.sh up` 构建和预检后启动三服务。Collector 唯一写入，后端没有 CTP/flow/配置挂载，前端没有数据挂载。宿主目录是持久 bind mount，不是镜像层，也没有迁移成另一份数据库。Python 不提供 JS。

## 已获得的证据

| 验证 | 结果和范围 |
|---|---|
| Release CTest | 6/6：config、state、storage、runtime、health、process |
| FastAPI / SQLite 测试 | 8/8：真实 SQLite、API 参数/错误码、schema/错日/损坏、空目录和空库、只读目录中的 WAL 追加可见、离线共享锁、写操作拒绝、心跳未知/过期/停止 |
| React Vitest | 4/4：健康和数量、交易日切换、网络断线清空与恢复、空目录/过期心跳、数据库错误不影响 API 存活判断 |
| React 生产构建 | `npm run build` 成功；使用提交的 package-lock；构建产物由 Nginx 服务 |
| 部署脚本 Docker CLI 替身测试 | 8/8：隐藏密码/配置复用、非交互缺配置失败、三镜像构建和三项预检顺序、后端或前端预检失败不替换旧服务、只读 verify、运维不构建；这不是 Docker 实测 |
| SQLite CLI 验收器回归 | 4/4：活跃 WAL、停止后读取、坏库/错日/空库等 |
| ShellCheck / Compose v2 config | 通过；实际解析出三服务、相同源目录 RW/RO 挂载、相同 UID/GID、回环 HTTP、独立 healthcheck，Collector 无依赖 |
| 原生进程集成 | `python3 tests/read_path_smoke.py` 通过：真实 C++ 二进制 → SQLite → 真实 Uvicorn HTTP；持续数量增长；Python 停止后采集继续；Python 重启读新增数据；Collector 停止后查询历史日；Collector 重启追加；SIGKILL 后心跳过期 |
| 真正浏览器集成 | `python3 tests/read_path_smoke.py --browser` 通过：Chromium 渲染 React，通过 Vite 同源代理读取真实 FastAPI；断网后清除健康和数量、恢复后重新显示；390px 页面无整体横向溢出，无 pageerror |

Python 测试应从 `query/` 执行 `poetry run python -m unittest discover -s tests -v`。Chromium 本机缺失的运行库只解压至临时工具目录用于验证；没有修改 Docker Desktop、WSL 或系统包配置。原生与浏览器集成测试使用临时目录，并清理各自子进程。

## 未完成的容器验收

当前 WSL 的 `docker version` 仍提示没有启用集成；Windows Docker CLI 能运行，但 `dockerDesktopLinuxEngine` 管道不存在。**真实三容器构建、运行时 RO bind mount、Nginx 容器代理和 Docker healthcheck 尚未实测。** `tests/read_path_docker_smoke.sh` 已实际调用并明确返回 `NOT RUN`，未把静态检查记为容器通过。

目标 Linux x86-64 / WSL 机器上启动 Docker Engine 后，在仓库根目录执行：

```bash
# 隔离测试：临时配置/数据、唯一项目和镜像、随机回环端口。
# 会构建镜像及运行各自测试，不接真实 CTP，不触碰 collector/data/。
bash tests/read_path_docker_smoke.sh

# 既有 Collector 容器生命周期 / 自动恢复专项（同样只用临时数据）。
bash collector/tests/docker_smoke.sh

# 真实配置部署
./collector/scripts/deploy.sh up
./collector/scripts/deploy.sh status
```

第一个测试验证三镜像构建、应用 healthcheck、Nginx 页面/API 代理、只读挂载和 SQLite 写拒绝、HTTP 数量增长、重复启动不增加实例、停止后端/前端仍采集、停止 Collector 后 API 仍查询、重建后的追加和 UID。第二个测试验证 Collector 自动重启、显式停止、官方 SDK 无网络超时和数据保留。失败会保留临时合成日志并非零退出。

打开 **http://localhost:8080**，应看到 Python API 与 Collector 应用状态；看板健康不代表真实行情验收。交易时段要确认 CTP 登录/订阅，间隔观察日行数、最近接收时间和 `snapshot_commit`，再执行 `./collector/scripts/deploy.sh verify YYYYMMDD`。API 文档在 **http://localhost:8000/docs**。

已知 WAL 限制保持不变：采集另一天时，缺 sidecar 的历史日可能返回 503。要通过 HTTP 查询该日，应仅正常停止 Collector（参见 [操作手册](../collector/README.md)），保留 Python 和前端运行；不要删除 WAL 或放宽后端挂载权限。
