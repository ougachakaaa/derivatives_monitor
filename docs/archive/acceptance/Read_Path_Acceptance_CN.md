# 只读后端与独立 React 看板验收

> 历史验收快照：仅证明文中日期/版本/环境下的观察。旧端口、临时路径、待验状态和操作命令可能已过时；当前设计见[文档入口](../../README.md)，当前门槛见[验收矩阵](../../acceptance.md)，运行见[操作说明](../../operations.md)。原始日志缺失时仅作为历史摘要。


验证日期：2026-09-07。约束见 [读路径设计](../../contracts/read-path.md)，步骤见 [T9–T11](../README.md)。所有行情样本来自明确标记 `CTP TEST DOUBLE - synthetic market data` 的合成 SDK；没有把它们当作真实 CTP 验收。

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

## 2026-09-07 Docker 实机补充验收（T12）

此前的 `NOT RUN` 限制已解除。用户授权修复 Docker 后，启动了 Windows Docker Desktop；原有 WSL 2 配置与 Ubuntu-24.04 集成均已启用，启动时遇到 `setup groups / whoami / 0x8007274c` 超时。在确认 WSL 命令恢复后，重试 Desktop 的 **Restart the WSL integration** 操作，WSL 的 Docker socket 与 Engine 访问恢复。没有重装、清理 Docker 数据或更改发行版配置。

实际环境：Docker Desktop 4.89.0、Engine 29.7.2（Linux amd64）、Compose v5.5.0。新增证据：

- 三个正式 runtime 镜像实际构建成功；镜像内 CTest 6/6、FastAPI 8/8、React 4/4 与 Vite 生产构建通过。
- `tests/read_path_docker_smoke.sh` **PASS**：三服务 Docker healthcheck 全 healthy；Nginx 返回构建后的 React 页面并转发 API；HTTP 行数持续增长；同目录 RW/RO、SQLite 写拒绝、同 UID、重复部署、独立停止和重建追加通过。
- `collector/tests/docker_smoke.sh` **PASS**：两日数据、连接恢复、SIGTERM/正常停机、Docker 自动重启与手动停止、数据保留；正式镜像无测试 SDK/编译器/Python、动态依赖齐全；官方 SDK 在 network none 下超时并重启。
- 非 root、只读 rootfs 下实际执行 Nginx `-t` 和 Python 数据目录预检通过。
- Chromium 对 **容器 Nginx 提供的生产 React 页面** 实测通过：实际 HTTP 数据、断网清除与恢复、移动布局、无 pageerror。Windows PowerShell 直接访问宿主 localhost 的 Nginx API，看到 API/Collector 均 healthy、日行数 572（仍持续增加）、来源明确 TEST DOUBLE。

本次按用户确认仅验收合成行情。真实 CTP 前置、账号和精确合约待后续配置；未向实盘发起本轮采集。

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

已知 WAL 限制保持不变：采集另一天时，缺 sidecar 的历史日可能返回 503。要通过 HTTP 查询该日，应仅正常停止 Collector（参见 [操作手册](../../../collector/README.md)），保留 Python 和前端运行；不要删除 WAL 或放宽后端挂载权限。

## 保留一套可查看的合成演示

```bash
KEEP_RUNNING=1 bash tests/read_path_docker_smoke.sh
```

全部验收通过后保留隔离项目、镜像与临时数据，输出实际看板/API 地址和 `stop.sh` 路径。默认不设置该变量则验收后自动清理；两种模式均已实际通过完整 smoke，默认模式的容器和专用镜像已清理。演示数据位于 `/tmp/dm-read-docker.*/collector/data/`，不写真实 `collector/data/`；这是临时合成演示，长期真实采集仍用 `deploy.sh up`。

本次保留项目 `dm-read-dm-read-docker-ees6qv`：看板 `http://localhost:32770`，API `http://localhost:32772/docs`；停止并移除演示容器与专用镜像可执行 `bash /tmp/dm-read-docker.EES6Qv/stop.sh`，数据保留。端口和路径仅对应本次运行；下次以脚本输出为准。
