# 部署长期契约

目标为本地 Linux x86-64 / WSL。Collector、Query、Dashboard 三个独立项目；仓库根 `compose.yaml` 定义三服务的系统级 runtime composition，原生 systemd 和 Docker Compose 是两种部署方式，不同时写同一个 Raw 目录。命令与排障见[Collector 手册](../../collector/README.md)和[运行与恢复](../operations.md)。

## 数据与隔离

- 宿主 `collector/data/`、`collector/flow/` 的生命周期独立于服务/镜像/构建。没有数据迁移，也不是容器临时层；不得用清理镜像或项目目录的动作删除历史数据。
- Docker Collector 可写 `/app/data`；Query 同 UID/GID 只读挂载该目录到 `/data` 并设置只读 rootfs；Dashboard 无数据/flow/配置/Docker socket 挂载。Query 和 Dashboard 均无 CTP 凭据。
- Docker 配置只读挂载，以 0600 保存本地 INI；Docker 部署入口不覆盖已有配置。三个正式镜像保持 repository root build context，各自通过同目录 `Dockerfile.dockerignore` 采用 deny-by-default 白名单，只允许本镜像的源码、锁文件、必要 SDK/测试/日历等明确输入；配置、凭据、Raw、日志、flow、参考咨询原件和本机工具不进入上下文。新增仓库文件默认不进入既有镜像，成为构建依赖时须显式更新所属镜像的白名单。
- 正式 Collector 只链接仓库官方 SDK。TEST DOUBLE 动态库仅为隔离测试显式加载，不进入正式 runtime 镜像。
- Query 只提供 JSON，Dashboard 独立服务页面并同源代理 `/api/`；Docker 使用 Nginx，原生 systemd 使用 Vite。默认宿主 `127.0.0.1:8101` 和 `127.0.0.1:8000`。容器 Nginx 内部 8080 与宿主 8101 不混用。

Skew 审核参考包可保存在数据目录的 `references/analytics/`，由独立运维导入、Query 随现有数据挂载只读消费；默认路径随 DATA_DIR，独立目录使用 SKEW_REFERENCE_DIR 和只读挂载。HTTP month 参数或显式 SKEW_TARGET_MONTH 选择目标月，不引入 Collector 配置或自动换月。参考包不进入镜像。详见 [Query 手册](../../query/README.md)。

## 生命周期

- Collector 无 Query/Dashboard 启动依赖。API 不调用管理器；日历不触发开收盘启停。
- 仓库级 `scripts/deploy.sh up` 是唯一正式 Docker system deployment 入口，首次交互配置、后续复用。它协调三服务构建、预检、启动、状态、日志和停止，但 Collector 的配置与 runtime state 仍归 `collector/`。固定 `DataDirectory=data`、`FlowPath=flow`、`RunSeconds=0`；首次默认连接超时 120 秒、采样 15000ms、状态日志 10 秒。构建、测试和权限/配置预检在更新现有容器前完成；固定 Compose 项目禁止另一 checkout 接管原实例。
- Docker 使用 `unless-stopped`，Collector 直接接收 SIGTERM，停止宽限 60 秒。`stop` 保留数据；故障可能反复重启，必须通过日志/退出码/重启计数判断，不把 running 当成功行情。
- Docker 日志每份 10MB、保留三份。`logs` 的退出不停止采集；更新前按需要导出旧容器日志。
- 原生管理器使用三个用户 systemd 服务及 universe 定时器。清单更新在发布的合约集变化、运行订阅集不一致或已有订阅诊断无法解析时正常重启活跃 Collector；手工 `up` 则启用并重启三个服务。08:45/09:00/09:15 与 20:40/21:00/21:15 为更新/重试点。此 Python 管理工具不进入 C++ 采集运行时。
- 原生服务异常退出 10 秒后重启；停止宽限 60 秒。WSL 停止或 Windows 睡眠时不能继续采集。用户管理器下次启动可能拉起已启用服务，长期禁用见操作手册。

## Developer runner 的生命周期边界

本节定义本地前台开发会话的要求，不改变上文两种持久部署方式。实现与验证状态见 [Acceptance](../acceptance.md)，本次交付顺序见 [execution plan](../dev-runner-execution-plan.md)。

- Runner 的 lifecycle ownership 仅覆盖本次调用创建的组件子进程及其受控后代；它随当前 terminal session 工作，不接管其他终端、其他 checkout 或已经存在的进程。不得按进程名、端口或历史 PID 文件取得控制权。
- Runner 不调用 native/systemd 或 Docker/Compose 管理器来启动、停止、安装、启用、更新或替换部署；不创建持久服务、定时器或可跨会话接管的运行状态，不后台驻留、不自动重启。已有部署占用端口或数据目录时报告冲突，由操作者通过原部署入口处理。
- Collector、Query、Dashboard 可分别启动。联合启动只协调本次开发会话，不建立组件间启动或健康依赖。启动后的 Query/Dashboard 退出、HTTP 不可达或业务不可用，不触发 Collector 停止或重启；其他组件也不因同伴退出而被自动停止。Runner 保持管理仍存活的子进程并明确记录失败。
- 用户结束会话，或 runner 收到 SIGINT、SIGTERM、终端 SIGHUP 时，只收尾本次拥有的进程，先发送 SIGTERM 并给予 60 秒正常退出宽限；超时仅可强制结束本次残留进程并明确报告。Collector 正常停止的 SDK 释放与尾部提交仍由 [Collector Contract](collector.md)定义。SIGKILL、宿主退出或无法送达终端信号不具备正常收尾保证；不得报告尾部已提交。
- Runner 的异常退出路径应尽力收尾自己已创建的进程；不能因清理失败扩大控制范围或隐瞒残留。非零子进程退出、启动失败和强制终止不得被汇总为会话成功。

## 开发配置与数据不变量

- Collector 配置、flow、Raw 仍归 Collector；Runner 只消费已有配置，不创建或改写凭据、采样参数、运行时长、订阅配置，不自动刷新 Universe 或导入参考包。原生管理器的配置准备行为不因此改变，其操作见 [Collector 手册](../../collector/README.md)。
- Collector 始终是 Raw 唯一 writer，Query 只读，Dashboard 只访问 JSON。开发入口不建立第二套事实、迁移 schema、放宽 SQLite 只读规则，或为启动/停止清理数据、flow、日志及现场证据。跨开发会话、native 和 Docker 的同目录互斥仍由 Collector 的目录锁最终保证；预检不能代替该锁。
- 联合启动时 Query 必须读取本次 Collector 配置指向的同一数据目录；显式输入冲突应在启动前拒绝，不能静默选择不同目录。单独启动 Query 不需要读取 Collector 凭据配置，也不要求 Collector 运行。
- 配置内相对路径继续以所选配置文件目录为基准，不因统一入口改变含义。Runner 不将 Collector 凭据或 INI 内容传给 Query/Dashboard；诊断不回显凭据或包含凭据的错误原行。
- 环境、配置和端口诊断不启动服务、不改写持久文件、不自动修复配置或释放端口。端口或锁的预检结果只是当时观察；权限不足、不可检查和缺证据必须明确标为未知，不能视为通过。

## 启动与健康的证据语义

| 证据 | 能证明什么 | 不能据此推断什么 |
|---|---|---|
| Process liveness | 本次拥有的进程尚未退出；Collector 心跳另按 Read Path 判定 | HTTP 已监听、CTP 登录/订阅成功、行情在推进 |
| HTTP reachability | 指定地址的 HTTP 请求成功；Query `/healthz` 表达服务自身存活 | 请求一定来自本次新进程、Raw 可读、指标可计算 |
| Business readiness | 按领域 API/Contract 返回的行情、质量、参考输入及可计算状态 | 仅凭进程存在或 HTTP 200 不能建立该结论 |

上述证据分别报告，不合并成“系统就绪”。已有进程可能响应相同 URL，HTTP 检查必须与本次子进程状态分开；业务响应可以是 HTTP 200 且 UNAVAILABLE。休市、缺行情、缺参考包不等于进程失败，也不成为 Collector 启动条件。具体心跳、HTTP 错误和业务质量语义沿用 [Read Path](read-path.md)及其领域契约链接，Runner 不另设业务健康标准。

## 验收边界

Docker 构建执行 CTest、Query 测试、React 测试/构建；隔离容器 smoke 检查实际挂载、健康、重启和保留数据。原生测试、Compose 静态解析、CLI 替身均不替代真实 Engine 验收。`up` 成功只说明部署完成，不说明真实 CTP 订阅或持续行情成立。

Docker build boundary 由对应服务的 `Dockerfile` 与 `Dockerfile.dockerignore` 共同拥有；仓库根 `compose.yaml` 负责 runtime composition。三个 service 均以仓库根为 build context；Compose 文件移动不改变 `collector/config.ini`、`collector/data/`、`collector/flow/` 的归属和挂载语义。边界验收须导出三个 Dockerfile 实际过滤后的上下文，逐字节核对明确输入且拒绝额外文件，并实际走完三个 runtime image 的依赖安装、构建和 build-stage 测试。

只读验收器 `verify YYYYMMDD` 检查非空、schema/日身份、外键/完整性及 run 来源。活跃 WAL 正常只读；停机无非空 WAL 且取得目录共享锁才使用 immutable。旧日缺 sidecar 且 Collector 活跃时明确失败，不创建空库、不删除 WAL、不放宽只读。
