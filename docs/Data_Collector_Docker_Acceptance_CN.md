# Docker 部署实现与验收记录

**2026-09-07 更新：** T12 已恢复 Docker Desktop/WSL 集成，并实际通过 Collector 容器生命周期验收和三容器读路径验收。当前结果见 [T12 实机证据](Read_Path_Acceptance_CN.md)。以下 T6–T8 的静态验证与 NOT RUN 是初始阶段历史记录，不再代表当前 Docker 状态。

依据 [部署约束](Data_Collector_Docker_Constraints_CN.md) 和 [T6–T8 Specs](tasks/data-collector/README.md)。本轮保持既有 C++ 采集与 SQLite schema，不增加 Python/Browser 运行依赖。

## 已实现与已验证

- Dockerfile：Ubuntu 24.04 多阶段构建，复用官方 SDK；构建层执行五项 CTest，最终层仅部署正式二进制、SDK、SQLite/锁工具及验收脚本。
- Compose：单服务、配置只读、宿主 data/flow 持久化、调用者 UID/GID、SIGTERM/60 秒宽限、unless-stopped、10MB × 3 日志轮转、无端口映射。
- Bash 入口：up/logs/status/stop/verify，首次交互隐藏密码并保存 0600 INI，后续配置不覆盖，更新前完成构建和预检；固定 Compose 项目对不同 checkout 做身份保护。
- 真实 Compose v2.24.6 CLI 的 `config --format json` 解析通过，自动核对平台、UID/GID、挂载、停止宽限、restart 和日志设置。此操作无需 Docker daemon，**不等于容器启动成功**。
- 三份 shell 脚本语法及 ShellCheck 0.9.0 通过。
- `deploy_test.py` 的 8 项 Docker CLI 替身测试通过：真实 PTY 首次输入/密码不回显、权限 0600、路径空格、已有配置不变、INI 不执行、配置错误不泄露原文、预检顺序、失败不替换原容器、跨 checkout 保护、只读挂载参数与运维行为。
- `verify_test.py` 的 4 项真实 SQLite CLI 测试通过：活跃 WAL 的新提交可见、关闭后没有 sidecar 的只读库、空库/错日/schema/坏外键拒绝、缺失/损坏库不创建或修改文件。
- 现有 Release 五项 CTest 回归通过，C++ 代码与 schema 未修改。

SQLite CLI 和 ShellCheck 由 Ubuntu 包下载解压到 `/tmp/dm-deploy-test-tools` 用于开发验证，未修改系统包或提交工具产物。测试 Python 只用于开发测试，不属于宿主部署脚本或采集运行时。

## 容器实测限制

当前开发 WSL 调用 `docker version` 仍提示 Docker Desktop 的 WSL 集成未启用。因此以下项目本次**未实测**：

- 拉取基础镜像、Docker build 及镜像内 CTest。
- Docker Engine 的实际 bind mount/UID、信号转发和重启行为。
- 合成 SDK 在容器中持续采集、日切、停机、重建与只读验收。

运行容器验收脚本得到：

```text
Docker Engine + Compose v2 required; container smoke test NOT RUN.
exit_code=1
```

已交付可在目标机执行的隔离验收脚本；不能把上述静态和宿主测试列为容器验收通过。脚本不会自动更改 Docker Desktop 设置，也没有执行 Git push。

## 目标 WSL 一条命令验收

在仓库根目录执行：

```bash
./collector/tests/docker_smoke.sh
```

只需 Docker + Compose v2 和宿主 Bash/常用 Linux 工具。它构建独立测试镜像，构建阶段跑当前六项 CTest；随后在临时目录中使用合成 SDK 测试：

1. 持续接收、两日分区、断线恢复与只读查询。
2. 同一 Compose 配置重复启动不增加实例。
3. 进程收到 SIGTERM 后自动恢复、run 追加和数据保留。
4. 显式停止后保持停止、stopped_us 标记及尾部持久化。
5. 强制重建容器后继续写入已有数据库。
6. 最终镜像不包含测试库、源代码、本地配置或编译器/Python；数据所有者正确。
7. 官方 SDK 在禁用网络的隔离容器中启动超时，由 Docker 自动重新启动；此部分不产生假行情。

脚本使用唯一测试镜像/容器/Compose 项目和 `/tmp/dm-docker-smoke.*` 数据目录，不读取或修改真实 `collector/config.ini`、`collector/data/`、`collector/flow/`。测试库从 build 层提取，只有合成测试容器挂载和预加载它；正式镜像不包含测试库。

成功输出 `PASS` 并清理测试资源；失败清理测试容器/镜像，保留临时日志和合成数据库，打印证据路径。首次构建耗时取决于网络；运行测试还需等待真实的启动超时和重启窗口。

## 真实采集准备

```bash
./collector/scripts/deploy.sh up
./collector/scripts/deploy.sh logs
```

第一次仍需填写已确认前置和合约，不应直接把测试日期/测试合约当成当前实盘清单。8:50 提前运行时观察登录状态；开盘后确认各合约 `session_received`、`accepted`、`written` 和 `last_commit_us` 推进，然后执行（日期按实际修改）：

```bash
./collector/scripts/deploy.sh verify 20260907
./collector/scripts/deploy.sh status
```

`verify` 检查的是一个时点的数据库；持续更新需要重复观察。`running`、退出码 0 或只有登录成功均不能代替真实行情验收。首次采集结束用 `stop` 正常停止并再次 `verify`，之后 `up` 验证同日追加。实盘完整条件见 [第一阶段验收记录](Data_Collector_Acceptance_CN.md)。

只读 WAL 的补充限制：正常关闭的库没有 sidecar 时，验收器只在持有 Collector 目录锁且无非空 WAL 的条件下用 immutable。活跃采集使用普通只读 WAL；若同时查看已关闭的另一历史日而 sidecar 不在，应先正常停止 Collector 再查询。详见 [SQLite 只读 WAL 条件](https://www.sqlite.org/wal.html#read_only_databases)。
