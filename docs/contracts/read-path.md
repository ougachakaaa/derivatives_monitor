<a id="read-path-http-contract"></a>
<a id="query-read-contract"></a>
<a id="dashboard-read-contract"></a>

# 最小 Python 只读层与 JS 看板约束


API 按共享 [Raw Boundary](raw-boundary.md) 只读同一份数据，页面独立。当前操作见[Query](../../query/README.md)与[Dashboard](../../dashboard/README.md)。

## Feature 查询扩展（已冻结）

只读 `POST /api/features/evaluate` 以 JSON body 承载一次单 Feature 查询，不写规则或应用状态。请求/响应、采样身份、Skew 映射及失败语义唯一由 [Feature Contract](features.md)定义；沿用本契约本地 HTTP、[Raw 只读保护](raw-boundary.md#只读消费与-wal)和 no-store。既有 Skew GET 与 Dashboard 不迁移，Query 不依赖 Monitoring；当前实现与验证程度只见 [Acceptance](../acceptance.md)。

## 边界

- Query 使用 FastAPI/Uvicorn 提供 JSON，Dashboard 通过同源 `/api/` 消费；系统组件与依赖方向见 [Architecture](../../ARCHITECTURE.md)，镜像、挂载及 lifecycle 见 [Deployment](deployment.md)。
- Query 按 [Raw Boundary](raw-boundary.md#只读消费与-wal) 打开日库，查询使用参数绑定；不接受任意 SQL 或文件路径。Query 的内部读取适配要求在后续局部迁移前仍由本节承接。
- 前端 HTTP 仅发布至宿主 `127.0.0.1:8101`，后端直接访问仅发布至 `127.0.0.1:8000`；浏览器通过前端同源 `/api/` 查询，无需宽泛 CORS；开发时 Vite 使用相同代理。服务用于本地观察，不引入认证、外网部署、交易或 WebSocket。

## 最小接口与页面

- `GET /healthz`：Python HTTP 服务自身存活，与 Collector/行情是否可用独立。
- `GET /api/health`：Python 状态、共享目录可读性、Collector 心跳/进程状态、CTP 连接登录、接收及写入计数和最后时间。
- `GET /api/days`：可用交易日及文件占用字节（主文件与 WAL），只接受真实合法日期文件名。
- `GET /api/summary?day=YYYYMMDD`：该日确切 snapshot 总行数、逐合约行数/最后接收时间、文件占用字节。
- `GET /api/snapshots?day=YYYYMMDD&instrument=CODE&limit=50`：返回最近行情事实；instrument 可省略，limit 限制 1–200，不允许任意 SQL/路径。
- 非法参数返回 400，缺失日文件 404，数据库不可读/不兼容/查询超时返回 503；空目录和空数据明确显示，不能伪造成“采集失败”。
- JS 每 5 秒轮询，展示 Python 与 Collector 状态、CTP 连接状态、交易日选择、日数据行数/体积、逐合约数量及少量最新行情。错误会清除相应的健康/新鲜标识，保留旧数据时注明旧值，不继续显示绿色成功。

## 健康证据

`GET /api/health` 对 [Collector 运行诊断协议](raw-boundary.md#collector-运行诊断协议)做只读投影，不建立第二套心跳、存活或行情新鲜定义。

- Docker healthcheck 分别检查 Collector 主循环新鲜心跳、Python `/healthz` 与前端静态服务 `/healthz`；页面显示的是应用健康证据，不声称通过 Docker 管理 API 查询容器状态。

## SQLite 只读限制

WAL、sidecar、immutable、共享锁、复制和 backup 的唯一约束见 [Raw Boundary](raw-boundary.md#只读消费与-wal)。本 HTTP 层将缺失合法日库映射为 404，将日库不可读、不兼容、锁/WAL 条件不成立或查询超时映射为 503。

## 验证与依据

覆盖真实 SQLite/HTTP、并发写入只读消费、独立停启、心跳过期、坏参数/坏库、浏览器错误恢复及部署隔离。统一入口见[Harness](../../harness/README.md)。Docker 不可用时不能用宿主测试宣称容器通过。

技术选型来源：[FastAPI 容器部署](https://fastapi.tiangolo.com/deployment/docker/)、[Poetry 锁定依赖](https://python-poetry.org/docs/basic-usage/)、[Vite 项目构建](https://vite.dev/guide/)。SQLite 依据由 [Raw Boundary](raw-boundary.md) 统一维护。

## 市场时段与覆盖

`/api/sessions` 独立读取审核后的交易日历，按 exchange/product 回答交易日、时段与连续交易状态，不读取/改写行情，也不控制采集进程。日历未知必须明确UNKNOWN。覆盖统计支持原有CFFEX与SHFE AU/AG期货，按各自来源目标交易日核对清单；市场休市/休息、行情无推送、订阅失败与进程健康分别表达。Query模块及参考年历随Docker镜像发布，Collector没有新增依赖。

## MVP MO Skew JSON 业务查询

已实现于 `query/skew_service.py` / `skew_references.py`；数学定义和时间选择严格沿用 [mo-skew-25d-v1](analytics-skew.md)，不新增行情时间模型。当前证据为 TEST DOUBLE 工程回归，G2/G3 真实业务门槛仍待验。

| GET 路径 | 必需参数 | 能力 |
|---|---|---|
| `/api/skew/latest` | 无（需配置目标月或显式 `month`） | 按日历选择最近可展示的封口连续分钟，返回该分钟 Skew |
| `/api/skew/minute` | `day=YYYYMMDD`、`minute=带时区ISO整分钟` | 指定交易分钟回看；始终 `historical=true`、`current_usable=false` |
| `/api/skew/series` | `day=YYYYMMDD` | 该日截至评估时刻的已封口连续分钟、首个有效基准与变化 |

公共可选参数：`month=YYMM`（否则用 `SKEW_TARGET_MONTH`，不自动换月）、`at=带时区ISO时间`（默认请求时钟，作为 Market State `evaluated_at` / Analytics `requested_at`）、非负整数 `raw_revision`、`bundle_id`。后两者用于固定输入回放，不是 SQL 或文件路径。`at` 显式传入时是在该评估时刻下重建；`current_usable` 也是相对此时刻的判断。实际盯盘省略 `at`。历史分钟估值与 quote age 仍以 minute end 为准。参数未知、重复、类型错误、无时区、非整分钟、MO 月格式错误、day/minute 不匹配、未来分钟或超出可见 revision 返回400。

### React 汇报投影

Dashboard 的首屏业务投影只消费上述 JSON：按 coverage 中的 MO 月份显式选择 `month`，展示 latest 的对象、`skew_25d_vp`、`valuation_at`、`historical/current_usable`、`quality`和 `reasons`，展示 series 直接返回的 `baseline/change_vp/points`，并用 minute 接口完成指定分钟回看。图表只对 API 数值做显示缩放，不求 IV、delta、forward 或 Skew，不对失败分钟补点。

latest 请求失败会同时清空当前值和旧序列；series 单独失败会清空变化与走势，但可保留本次已成功 latest 响应并明确标注。历史回看不复用当前日变化，`SYNTHETIC` 参考包在首屏显式标记 `TEST DOUBLE`。Collector/CTP/coverage/database/session 诊断保留在折叠区，不与 Skew 业务可用性混为一个状态。

最新值不消费 Market State `latest()` 的盘后陈旧标志，而是复用 Calendar periods 定位并调用 `reader.minute(..., stale_after_us=30000000)`。首分钟未封口返回 WAITING_FOR_MINUTE；BREAK/CLOSED/竞价只选择最近结束的连续分钟并明确 historical。缺数据不搜索更旧行情；日历下一 trading_day 与实际历史分钟 day 分开返回。UNKNOWN 返回 CALENDAR_UNKNOWN，无猜测时间。

单点返回 `schema_version=1`、契约/算法版本、业务 scope（exchange/product/month/trading_day）、minute、valuation_at/effective_as_of、requested_at/evaluated_at、session、historical/current_usable/reconstructed/display_age_us、status/reasons、`skew_25d_vp` 和 `unit=vol_point`。`quality` 保留 Market State 完整性及 expected/observed/usable/missing/stale/invalid 计数；Analytics eligible/excluded 与计算原因单独表达。原始 Raw rows、内部 scope 清单、表结构和本地路径不公开。

追溯字段包括 raw_revision、Universe/Calendar/ReferenceBundle 版本与实际原文件 SHA-256、参考 manifest 和官方清单原响应哈希、冻结模型参数、平价三对、两翼端点及权重、provenance。每个 provenance 提供 instrument、observation_id、run_id、received_us、snapshot_us、源 trading_day/action_day/time/millisec、bid/ask/mid、质量、排除原因、使用角色和求解结果。源时间保留原值；不拼造交易所时间戳。Market State 的四个 `invalid_BidPrice1/AskPrice1/BidVolume1/AskVolume1` 原因在 HTTP 中对应 `invalid_bid/invalid_ask/invalid_bid_size/invalid_ask_size`，其余质量语义不变。完整数值不按页面显示精度舍入。

当日响应 `points` 按分钟升序，固定首帧返回的同一 revision、同一参考包、Universe 和 Calendar；后续每帧显式传 revision。MVP 日历当前最多237个 MO 连续分钟；不枚举竞价/午休，不 forward-fill，失败分钟保留 null 与原因。`baseline={minute,skew_25d_vp}` 取首个 OK；`change_vp` 为最后枚举分钟值减基准，同时给出 `change_minute`。最后一分钟失败、无基准或当前连续段仍 WAITING 时变化为null，不回退到最近成功值。所有点均失败则序列 UNAVAILABLE；至少一点有效可为OK，但每点 status 和 reasons 仍必须检查。无封口分钟返回空 points、null revision/baseline/change；不因此读取 Raw。历史日序列的变化仍明确属于该历史日。

缺目标月、参考包、无效/不匹配参考、未知日历、非连续/未封口分钟以及不能计算的行情前提返回200和 UNAVAILABLE/null/原因，current_usable=false；尚未读取 Raw 时 revision/quality/provenance 明确未知或空，不伪造完整性。日库实际读取抛出的404/503原样保留，不变成业务缺翼。序列采用10秒执行预算（逐分钟检查，单帧仍受 Store 的3秒 SQL预算约束），超限503并丢弃部分响应；这不是 P95≤2秒的性能证明。所有响应 no-store，不启用派生持久化或缓存。

参考选择只在请求入口读取一次 `<day>/<month>.json` 的 bundle_id，然后核对不可变输入包的原文件哈希；显式 bundle_id 可重放旧包。历史查询不使用 Collector 的 universe/current；最新定位所用 Calendar 必须与参考包 Calendar 一致。Production 只接受 OFFICIAL 及已归档官方来源字节，SYNTHETIC 仅可通过测试构造器注入，HTTP/环境变量没有绕过开关。导入工具不会自动抓取或审核金融数据，审核者仍须核对原发布内容和归一化值；详见 [Query 手册](../../query/README.md)。
