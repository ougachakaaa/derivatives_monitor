# 部署长期契约

目标为本地 Linux x86-64 / WSL。Collector、Query、Dashboard 三个独立项目；原生 systemd 和 Docker Compose 是两种部署方式，不同时写同一个 Raw 目录。命令与排障见[Collector 手册](../../collector/README.md)和[运行与恢复](../operations.md)。

## 数据与隔离

- 宿主 `collector/data/`、`collector/flow/` 的生命周期独立于服务/镜像/构建。没有数据迁移，也不是容器临时层；不得用清理镜像或项目目录的动作删除历史数据。
- Docker Collector 可写 `/app/data`；Query 同 UID/GID 只读挂载该目录到 `/data` 并设置只读 rootfs；Dashboard 无数据/flow/配置/Docker socket 挂载。Query 和 Dashboard 均无 CTP 凭据。
- 配置只读挂载，以 0600 保存本地 INI；已有配置不覆盖。三个正式镜像保持 repository root build context，各自通过同目录 `Dockerfile.dockerignore` 采用 deny-by-default 白名单，只允许本镜像的源码、锁文件、必要 SDK/测试/日历等明确输入；配置、凭据、Raw、日志、flow、参考咨询原件和本机工具不进入上下文。新增仓库文件默认不进入既有镜像，成为构建依赖时须显式更新所属镜像的白名单。
- 正式 Collector 只链接仓库官方 SDK。TEST DOUBLE 动态库仅为隔离测试显式加载，不进入正式 runtime 镜像。
- Query 只提供 JSON，React/Nginx 独立服务页面，同源 `/api/` 代理；默认宿主 `127.0.0.1:8101` 和 `127.0.0.1:8000`。容器 Nginx 内部 8080 与宿主 8101 不混用。

Skew 审核参考包可保存在数据目录的 `references/analytics/`，由独立运维导入、Query 随现有数据挂载只读消费；默认路径随 DATA_DIR，独立目录使用 SKEW_REFERENCE_DIR 和只读挂载。HTTP month 参数或显式 SKEW_TARGET_MONTH 选择目标月，不引入 Collector 配置或自动换月。参考包不进入镜像。详见 [Query 手册](../../query/README.md)。

## 生命周期

- Collector 无 Query/Dashboard 启动依赖。API 不调用管理器；日历不触发开收盘启停。
- Docker `deploy.sh up` 首次交互配置，后续复用。固定 `DataDirectory=data`、`FlowPath=flow`、`RunSeconds=0`；首次默认连接超时 120 秒、采样 15000ms、状态日志 10 秒。构建、测试和权限/配置预检在更新现有容器前完成；固定 Compose 项目禁止另一 checkout 接管原实例。
- Docker 使用 `unless-stopped`，Collector 直接接收 SIGTERM，停止宽限 60 秒。`stop` 保留数据；故障可能反复重启，必须通过日志/退出码/重启计数判断，不把 running 当成功行情。
- Docker 日志每份 10MB、保留三份。`logs` 的退出不停止采集；更新前按需要导出旧容器日志。
- 原生管理器使用三个用户 systemd 服务及 universe 定时器。清单变化才正常重启 Collector；08:45/09:00/09:15 与 20:40/21:00/21:15 为更新/重试点。此 Python 管理工具不进入 C++ 采集运行时。
- 原生服务异常退出 10 秒后重启；停止宽限 60 秒。WSL 停止或 Windows 睡眠时不能继续采集。用户管理器下次启动可能拉起已启用服务，长期禁用见操作手册。

## 验收边界

Docker 构建执行 CTest、Query 测试、React 测试/构建；隔离容器 smoke 检查实际挂载、健康、重启和保留数据。原生测试、Compose 静态解析、CLI 替身均不替代真实 Engine 验收。`up` 成功只说明部署完成，不说明真实 CTP 订阅或持续行情成立。

Docker build boundary 由对应服务的 `Dockerfile` 与 `Dockerfile.dockerignore` 共同拥有；它与 Compose 负责的 runtime composition 分离。边界验收须导出三个 Dockerfile 实际过滤后的上下文，逐字节核对明确输入且拒绝额外文件，并实际走完三个 runtime image 的依赖安装、构建和 build-stage 测试。

只读验收器 `verify YYYYMMDD` 检查非空、schema/日身份、外键/完整性及 run 来源。活跃 WAL 正常只读；停机无非空 WAL 且取得目录共享锁才使用 immutable。旧日缺 sidecar 且 Collector 活跃时明确失败，不创建空库、不删除 WAL、不放宽只读。
