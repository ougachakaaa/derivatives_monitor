# Collector Docker 部署约束

依据已确认的 Docker 一键部署计划，扩展 [采集约束](Data_Collector_Constraints_CN.md)。本轮只封装部署，不改变 CTP、采样、schema 或 Python 只读边界。

- 用户入口：`./collector/scripts/deploy.sh up`。首次交互填写连接信息和精确合约，隐藏密码并以 0600 保存本地 INI；后续复用，不覆盖。
- 目标 Linux x86-64 / WSL、Docker Engine + Compose v2；宿主无需 C++、SQLite、Python。镜像使用 Ubuntu 24.04 多阶段构建、仓库 SDK 和既有五项 CTest。
- 配置只读挂载；`collector/data/`、`collector/flow/` 留在宿主，分别挂载到配置相对目录。容器使用调用用户 UID/GID。不可把本地配置、凭据、数据库、flow 或日志加入构建上下文/最终镜像。
- Docker 配置固定 `DataDirectory=data`、`FlowPath=flow`、`RunSeconds=0`；首次默认连接超时 120 秒、采样 1000ms、状态 10 秒。已有不兼容配置明确拒绝，不悄悄改写。
- 构建、配置及写权限预检均在更新原容器之前。`up` 幂等；后台单服务、默认桥接网络、无端口映射。
- Collector 直接接收 SIGTERM，60 秒停止宽限。采用用户选择的 `unless-stopped`，允许前置未就绪时进程超时后自动恢复；显式 stop 不重新启动。持久故障也可能反复重启，必须暴露日志/退出码/重启计数。
- Docker 日志每份 10MB、保留三份。`up` 只报告已部署，不宣称有真实行情。查看日志退出不停止采集。
- `verify YYYYMMDD` 使用临时容器和只读数据挂载，验证非空数据、schema、日身份、完整性并显示合约记录/时间/run 来源；不得创建空库或依赖宿主 SQLite。
- 模拟容器测试隔离于实际配置/数据，来源明确标识，测试 SDK 不进入正式运行镜像。
- 不更改 Docker Desktop/WSL 设置，不自动推送提交，不增加 Python/JS 服务。当前 WSL Docker 不可用时，区分静态/脚本测试和未完成的容器实测。

执行顺序：先提交本文与 T6–T8 Specs，再逐 Task 验证、单独提交。详细计划见 [任务目录](tasks/data-collector/README.md)。

只读 WAL 实现补充：停机且无 sidecar 的库在只读目录上不能直接创建 SQLite 共享内存。验收器只在获得 Collector 目录锁且无非空 WAL 时使用 immutable；运行中的数据不使用 immutable。锁不可用且该日无 sidecar 时不绕过安全条件，提示正常停止后复验。
