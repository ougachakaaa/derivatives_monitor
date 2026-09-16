<a id="repository-deployment-contract"></a>

# 部署长期契约

目标为本地 Linux x86-64 / WSL。Collector、Query、Dashboard 三个独立项目；仓库根 `compose.yaml` 定义三服务的系统级 runtime composition，原生 systemd 和 Docker Compose 是两种部署方式，不同时写同一个 Raw 目录。命令与排障见[Collector 手册](../../collector/README.md)和[运行与恢复](../operations.md)。

## 数据与隔离

- 宿主 `collector/data/`、`collector/flow/` 的生命周期独立于服务/镜像/构建。没有数据迁移，也不是容器临时层；不得用清理镜像或项目目录的动作删除历史数据。
- 开发期旧 Runtime DB 的显式重建是上述保留规则的有限例外：仅为采用 [当前 Runtime schema](raw-boundary.md#运行库与发布)，可在停止 Collector、关闭读连接后，由部署/开发动作删除不符合该 schema 的 `collector-runtime.sqlite`，再启动已实现当前协议的 Collector 创建新库；不要求保留该旧格式运行历史。此例外不适用于 Market 日库、配置、flow 或符合当前 schema 的历史库，不授权服务更新自动清理数据。Collector 本身不得迁移、自动修复或删除不兼容库。
- Docker Collector 可写 `/app/data`；Query 同 UID/GID 只读挂载该目录到 `/data` 并设置只读 rootfs，不挂载 Docker socket、Collector flow 或 CTP 凭据；Dashboard 无数据/flow/配置/Docker socket 挂载，也无 CTP 凭据。
- Docker 配置只读挂载，以 0600 保存本地 INI；Docker 部署入口不覆盖已有配置。三个正式镜像保持 repository root build context，各自通过同目录 `Dockerfile.dockerignore` 采用 deny-by-default 白名单。Query 镜像的 build 输入明确包含同一环境中的 `data_provider/`、`analytics/`、`query/` 三个源码包及 owner tests，runtime stage 只携带生产源码与 Calendar；配置、凭据、Raw、日志、flow、参考咨询原件和本机工具不进入上下文。新增仓库文件默认不进入既有镜像，成为构建依赖时须显式更新所属镜像的白名单。
- 正式 Collector 只链接仓库官方 SDK。TEST DOUBLE 动态库仅为隔离测试显式加载，不进入正式 runtime 镜像。
- Query 只提供 JSON，Dashboard 独立服务页面并同源代理 `/api/`；Docker 使用 Nginx，原生 systemd 使用 Vite。默认宿主 `127.0.0.1:8101` 和 `127.0.0.1:8000`。容器 Nginx 内部 8080 与宿主 8101 不混用。

Skew 审核参考包可保存在数据目录的 `references/analytics/`，由独立运维导入、Query 随现有数据挂载只读消费；默认路径随 DATA_DIR，独立目录使用 SKEW_REFERENCE_DIR 和只读挂载。HTTP month 参数或显式 SKEW_TARGET_MONTH 选择目标月，不引入 Collector 配置或自动换月。参考包不进入镜像。详见 [Query 手册](../../query/README.md)。

## 生命周期

- Collector 无 Query/Dashboard 启动依赖。API 不调用管理器；日历不触发开收盘启停。
- 仓库级 `scripts/deploy.sh up` 是唯一正式 Docker system deployment 入口，首次交互配置、后续复用。它协调三服务构建、预检、启动、状态、日志和停止，但 Collector 的配置与 runtime state 仍归 `collector/`。固定 `DataDirectory=data`、`FlowPath=flow`、`RunSeconds=0`；默认单次登录请求超时 120 秒（首次连接失败保持常驻）、状态日志 10 秒，Market Bar 固定为 15 秒且封口 grace 固定为 1 秒，不是部署配置。构建、测试和权限/配置预检在更新现有容器前完成；固定 Compose 项目禁止另一 checkout 接管原实例。
- Docker 使用 `unless-stopped`，Collector 直接接收 SIGTERM，停止宽限 60 秒。`stop` 保留数据；故障可能反复重启，必须通过日志/退出码/重启计数判断，不把 running 当成功行情。
- Docker 日志每份 10MB、保留三份。`logs` 的退出不停止采集；更新前按需要导出旧容器日志。
- 原生管理器使用三个用户 systemd 服务及 universe 定时器，并按 [Universe Tool Contract](../../collector/scripts/CONTRACT.md#保留发布与失败)的发布结果决定是否正常重启活跃 Collector；手工 `up` 则启用并重启三个服务。08:45/09:00/09:15 与 20:40/21:00/21:15 为更新/重试点。此 Python 管理工具不进入 C++ 采集运行时。
- 原生 Collector 非人工退出后由 systemd 等待 10 秒重启，Query/Dashboard 保持异常退出重启；停止宽限 60 秒。Collector 的主循环自动恢复参数见[下文](#native-heartbeat-recovery)。WSL 停止或 Windows 睡眠时不能继续采集。用户管理器下次启动可能拉起已启用服务，长期禁用见操作手册。

## Runtime 自动恢复

以下是 [Collector 第一阶段](../mvp.md#collector-第一阶段完成条件)的部署完成要求；现有配置及待补闭环见 [Acceptance](../acceptance.md#collector-第一阶段可靠性缺口)。

- 正式 supervisor 必须在非人工停止的 Collector 进程退出后重新启动它；主循环停止推进时，必须形成 `heartbeat stale → runtime failed → terminate/restart → new run_id → resume collection` 的闭环，不能永久停在 unhealthy 而不执行恢复。
- Heartbeat 发布和存活窗口沿用 [Raw Boundary](raw-boundary.md#运行库与发布)及其[存活判定](raw-boundary.md#只读诊断与存活)，保持秒级 publication。Supervisor 使用主循环事实，不由独立线程持续签到掩盖主循环 stall，也不依赖 Query Health evaluator。
- 每种正式部署方式必须声明 heartbeat stale 阈值、检查间隔/超时、启动宽限、终止宽限及强制终止、重启等待/退避和限制策略，并给出从主循环失去进展到新 Collector 进程启动的时间上界。该上界不等于外部 CTP 可用或首根行情到达的时间保证；实际恢复采集须另验。
- CTP disconnect、login 未完成或订阅恢复中不等于 Runtime failure；只要主循环正常推进，就由 Collector reconnect/login/resubscribe，不因 session down 重启进程。人工 stop 的停止意图须保留。
- Docker restart policy 与 healthcheck 各自存在不构成上述完整闭环；原生异常退出重启也不能单独证明能够处理主循环 stall。两种部署方式分别验收实际恢复动作。

<a id="native-heartbeat-recovery"></a>

### Native heartbeat 自动恢复

原生 Collector unit 的 MainPID 为部署侧 `native_watchdog.py` 包装器；每次包装器只启动一个 Collector 子进程，不自行重启、不调用 Query、不写 Runtime DB。systemd 是唯一自动重启 authority。包装器复用 `healthcheck.sh` 的完整 Runtime schema、只读和存活校验；从启动前记录的 UTC 时间核对 `runs.started_us`，拒绝上一个 Process 遗留的新鲜 heartbeat，首次接受后绑定该 run_id。包装器不会独立更新 heartbeat，也不以 callback 活动替代主循环事实。

| 参数 | 固定 native 策略 |
|---|---|
| 存活窗口 | `0 <= now_us - heartbeat_us <= 10_000_000`，process_state 为 starting/running |
| 检查间隔 / 超时 | 每次检查结束后最多等待 1 秒；整个探测进程组总超时 2 秒，超时强制清理 |
| 启动宽限 | 从 Collector spawn 前起计 15 秒；首次有效发布立即结束宽限，缺失/旧 Run 等不能延长宽限 |
| 失效处理 | 宽限结束后，stale、未来 heartbeat、缺失/不兼容/不可读库、Run 身份变化或探测超时均记为 runtime_failed，开始终止 |
| 终止 | 向自有 Collector 进程组发送 SIGTERM，最多等待 60 秒；仍未退出则 SIGKILL 并回收 |
| systemd 重启 | `Restart=always`、`RestartSec=10`；非人工零退出、非零退出、信号终止均重启 |
| 限制 / 退避 | `StartLimitIntervalSec=0`；固定等待，无指数退避和次数上限 |
| unit 清理 | `KillMode=control-group`、`KillSignal=SIGTERM`、`TimeoutStopSec=60`、`SendSIGKILL=yes`、`FinalKillSignal=SIGKILL`；包装器异常退出也不得留下旧 writer |

稳态从主循环失去进展到新 Collector 启动的配置上界为 **83 秒**（10 秒存活窗口 + 1 秒检查间隔 + 2 秒探测超时 + 60 秒终止宽限 + 10 秒重启等待）；首次有效发布之前阻塞的保守上界为 **88 秒**（15 + 1 + 2 + 60 + 10）。这些是宿主、user systemd、时钟同步、进程调度与 SIGKILL 正常工作的配置时间界限，不是内核不可中断 I/O、宿主暂停或系统资源耗尽时的实时保证，也不是新 Run 成功持久化、CTP 可用或首根 Bar 的时间保证。

自动重启路径没有网络 Universe `ExecStartPre`；`up` 预刷新和既有定时器负责清单更新，重启复用已发布清单。包装器记录 `collector_spawn`、`collector_run_bound`、`runtime_failed`、`collector_terminate`、`collector_force_kill` 等事件及 Collector PID / 已知 run_id。运行库仍由 Collector 独占写入；强杀的旧 Run 可保持结束字段 NULL，不能由 supervisor 补写或推断终止事实。

只要主循环持续发布，CTP disconnect、login 等待、subscription recovery 及无 Tick 均不触发 Process restart。`systemctl stop` 和 native `stop` 不触发 `Restart=always`；停止期间包装器只清理子进程。Universe 仅使用 manager 的 `try-restart` 重启仍活跃的 unit，不通过“先查 active、再 restart”重新拉起已停止的服务。用户管理器以后重新启动时，enabled 服务的启动语义仍沿用[生命周期](#生命周期)。

工程验收使用独立的 `native-recovery` profile，保留真实 user systemd 状态、Process/Run 身份变化、恢复时间及新 Run Market commit，具体命令见 [Repository Verification](../../tests/README.md)。TEST DOUBLE 只证明自动恢复机制；Docker 闭环与真实 CTP 恢复分别见 [Acceptance](../acceptance.md#collector-第一阶段可靠性缺口)。

## 长期运行环境前提

- 宿主系统时间必须可靠同步；heartbeat、received、committed、Runtime interval 和 Market close grace 均依赖 wall clock。明显时钟漂移不属于正常运行条件，须保留同步状态证据并处理异常。
- Market DB、Runtime DB 及必要 CTP flow 数据都必须位于持久目录中，遵守[数据与隔离](#数据与隔离)；container、image、binary 或 deployment 更新不得删除历史数据。
- Collector 运行身份必须能够写 data directory，磁盘须有足够空间，并能观察 Market / Runtime SQLite 及其 sidecar 的大小和增长。日志必须有 bounded rotation；Docker 参数沿用[生命周期](#生命周期)，原生部署须声明并核验实际日志容量/保留限制。
- 磁盘耗尽不得通过自动删除已存在的 Raw Market Facts 恢复；处理步骤见 [Operations](../operations.md#长期运行环境检查)。宿主或 supervisor 不运行期间不承诺自动恢复时限。

## Developer runner

本地前台开发会话（仓库根 `./dev`）的命令面、输入解析、进程所有权、开发配置不变量、doctor 账号字段边界及启动/健康证据语义由 [Developer Runner Contract](developer-runner.md)拥有；实际操作见[运行与恢复](../operations.md#前台开发会话)。

## 验收边界

Docker 构建执行 CTest、Data Provider/Analytics/Query owner tests、React 测试与前端构建；隔离容器 smoke 检查实际挂载、健康、重启和保留数据。原生测试、Compose 静态解析、CLI 替身均不替代真实 Engine 验收。`up` 成功只说明部署完成，不说明真实 CTP 订阅或持续行情成立。

Docker build boundary 由对应服务的 `Dockerfile` 与 `Dockerfile.dockerignore` 共同拥有；仓库根 `compose.yaml` 负责 runtime composition。三个 service 均以仓库根为 build context；Compose 文件移动不改变 `collector/config.ini`、`collector/data/`、`collector/flow/` 的归属和挂载语义。边界验收须导出三个 Dockerfile 实际过滤后的上下文，逐字节核对明确输入且拒绝额外文件，并实际走完三个 runtime image 的依赖安装、构建和 build-stage 测试。

只读验收器 `verify YYYYMMDD` 检查非空、schema/日身份、外键/完整性及 run 来源；读取过程严格引用 [Raw Boundary](raw-boundary.md#只读消费与-wal)，不另定义 WAL、immutable 或 sidecar 规则。
