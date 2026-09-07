# 最小 Python 只读层与 JS 看板约束

基于 [第一阶段约束](Data_Collector_Constraints_CN.md) 和 [Docker 部署约束](Data_Collector_Docker_Constraints_CN.md)。实现前已核对：SQLite 实际在宿主 `collector/data/`，Compose 把该目录 bind mount 到 Collector `/app/data`，不是镜像或容器临时层。保留此路径和全部历史文件。

## 边界

- 三个独立项目和容器：C++ `collector` 采集和唯一写入；Python `query` 使用 FastAPI/Uvicorn 提供只读 HTTP，Poetry 管理依赖并提交 lock；React `dashboard` 使用 Vite 构建，Nginx 提供静态资源并反向代理 `/api/` 至 query。Python 不提供 JS。
- Python 对同一宿主 `collector/data/` 挂载为 `/data:ro`，SQLite 用 URI `mode=ro`、`query_only=ON`、短事务及参数绑定；不建立第二份行情库、不修改现有 schema。
- Collector 不依赖 Python 启动、请求或健康。Compose 不给 Collector 添加 query 依赖。没有 Docker socket、CTP 凭据或 flow 文件挂入 Python。
- 前端 HTTP 仅发布至宿主 `127.0.0.1:8080`，后端直接访问仅发布至 `127.0.0.1:8000`；浏览器通过前端同源 `/api/` 查询，无需宽泛 CORS；开发时 Vite 使用相同代理。服务用于本地观察，不引入认证、外网部署、交易、分析、图表框架或 WebSocket。

## 最小接口与页面

- `GET /healthz`：Python HTTP 服务自身存活，与 Collector/行情是否可用独立。
- `GET /api/health`：Python 状态、共享目录可读性、Collector 心跳/进程状态、CTP 连接登录、接收及写入计数和最后时间。
- `GET /api/days`：可用交易日及文件占用字节（主文件与 WAL），只接受真实合法日期文件名。
- `GET /api/summary?day=YYYYMMDD`：该日确切 snapshot 总行数、逐合约行数/最后接收时间、文件占用字节。
- `GET /api/snapshots?day=YYYYMMDD&instrument=CODE&limit=50`：返回最近行情事实；instrument 可省略，limit 限制 1–200，不允许任意 SQL/路径。
- 非法参数返回 400，缺失日文件 404，数据库不可读/不兼容/查询超时返回 503；空目录和空数据明确显示，不能伪造成“采集失败”。
- JS 每 5 秒轮询，展示 Python 与 Collector 状态、CTP 连接状态、交易日选择、日数据行数/体积、逐合约数量及少量最新行情。错误会清除相应的健康/新鲜标识，保留旧数据时注明旧值，不继续显示绿色成功。

## 健康证据

- Collector 在持有原数据目录 writer 锁期间，每 2 秒原子替换 `.collector-status.json`，包括 schema_version、run_id、updated_us、process_state、连接/登录、订阅、accepted/written 与最后接收/提交时间。启动、正常停止、异常退出尽可能发布状态；不输出凭据。
- 心跳来自主循环，独立于行情；超过 10 秒、时钟明显倒退、内容损坏或缺失时不能判定存活。SIGKILL 后历史文件不能继续证明健康。
- 进程存活、CTP 已连接、行情最近更新是三个不同事实。休市无新行情不等于进程停止；只有采集连接/登录或已知错误才影响相应指标。
- 状态输出失败记录日志并继续采集；Python/浏览器的失败不会进入采集控制路径。该 JSON 是运行诊断，不是新增行情 Source of Truth。
- Docker healthcheck 分别检查 Collector 主循环新鲜心跳、Python `/healthz` 与前端静态服务 `/healthz`；页面显示的是应用健康证据，不声称通过 Docker 管理 API 查询容器状态。

## SQLite 只读限制

沿用上一阶段已验证的 WAL 策略：活跃数据库从只读挂载读取现存 WAL/SHM；离线且没有非空 WAL 时，仅在获得 Collector 共享目录锁后使用 immutable，并在连接关闭前持锁。不得根据文件年龄猜测 immutable 安全性。若 Collector 正在采集另一天、旧日缺少 sidecar，返回明确可重试的 503，提示正常停机后查询该历史日；不得绕过锁或修改持久目录。

## 实施与验收

先提交本文和 T9–T11 Specs，再逐 Task 完成验证和独立提交。覆盖真实 SQLite/HTTP、并发写入只读消费、Collector 停止而 Python 仍可读、Python 停止而 Collector 仍采集、心跳过期、空库/坏参数/损坏库、浏览器错误与恢复、Compose 三服务隔离及读写挂载。Docker Engine 不可用时不能把宿主进程测试当成真实容器实测。

技术选型依据：[FastAPI 容器部署](https://fastapi.tiangolo.com/deployment/docker/)、[Poetry 锁定依赖](https://python-poetry.org/docs/basic-usage/)、[Vite 项目构建](https://vite.dev/guide/)。以上为用户最新要求的调整；T9 心跳契约保持不变。
