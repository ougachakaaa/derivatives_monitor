# 只读查询后端

FastAPI + Uvicorn；Python 3.12，Poetry 2.2.1 管理独立环境与 `poetry.lock`。只提供 JSON/OpenAPI，不提供 React 或其他静态资源。

从本目录开发运行（先安装 Python 3.12 和 Poetry）：

```bash
poetry config virtualenvs.in-project true --local
poetry sync
DATA_DIR=../collector/data poetry run uvicorn app:app --host 127.0.0.1 --port 8000
```

验证：`poetry run python -m unittest discover -s tests -v`。Docker 构建使用相同锁文件、执行测试，最终镜像仅安装 main 依赖；Docker 部署无需宿主安装 Python/Poetry。

| 请求 | 内容 |
|---|---|
| `/healthz` | API 自身存活，不取决于行情 |
| `/api/health` | 共享目录、Collector 主循环心跳和 CTP 状态 |
| `/api/coverage` | 当前 CFFEX 品种/月清单与会话覆盖、合约缺口和来源；不接受查询参数 |
| `/api/days` | 日文件列表；size_bytes = 主文件 + WAL，非逻辑数据大小 |
| `/api/summary?day=20260904` | 精确行数、逐合约数量与最近接收时间、最近 100 个 run 来源 |
| `/api/snapshots?day=20260904&instrument=IF2609&limit=50` | 最近 snapshot，instrument 可省略，limit 1–200 |
| `/docs` | FastAPI 交互接口文档 |

时间字段是 Unix 微秒。采样行数不等于原始 tick 数；`accepted` 是本次 Collector 接收计数，`written` 是本次写入计数，日行数跨 run 累计。查询错误返回 JSON `error`：400 参数错误、404 日文件缺失、503 数据暂不可读/不兼容/超时。查询有 1 秒 busy timeout、3 秒执行预算；大库精确统计若超时，页面应显示错误，不把旧值当新值。

持久目录沿用宿主 `collector/data/`。后端容器同 UID **只读**挂载 `/data`；SQLite URI `mode=ro` 和 `query_only=ON`。活跃 WAL 数据库使用已有 WAL/SHM。离线数据库无 WAL 时，只有获得 `.collector.lock` 共享锁才使用 immutable；持锁到查询结束。Collector 活跃但历史日缺 sidecar 时返回 503，可正常停止 Collector 后读取，不删除 WAL，也不允许后端写入目录。

Collector 无依赖本服务。心跳缺失、过期或损坏为 unknown/stale；休市无行情不会单独让健康状态变红。页面观察应用状态，Docker 进程状态由部署脚本 `status` 查看。

## 市场日历与交易时段

`GET /api/sessions` 不需要数据目录或 Collector 存活；返回全部 13 个 exchange/product 状态。可按 `exchange=SHFE`、`product=AU` 筛选，`at` 可指定带时区的 ISO 8601 时间（通过 URL 编码传递 `+08:00`）；默认当前时间。无效/重复参数400，日历未知返回200且市场状态为UNKNOWN，不假装休市。`MARKET_CALENDAR_DIR` 可指定只读参考文件目录，默认随程序发布的 `calendars/`。

输出包括交易日、OPEN/BREAK/CLOSED/UNKNOWN、DAY/NIGHT、CONTINUOUS/AUCTION、is_continuous、quote_expected、当前区间、最近已开始的连续时段、下一连续时段及日历版本/来源。所有区间左闭右开。CLOSED 时 trading_day 指下一已知时段；来源事实仍以 CTP TradingDay 为准。产品时段不保证每个合约活跃，也不替代国债合约最后交易日仅上午交易等单合约规则。市场状态不参与健康红绿判定、不控制 Collector。

示例（纯标准库，无需启动 HTTP）：

```bash
python3 query/market_calendar.py --exchange SHFE --product AU --at '2026-09-07T23:30:00+08:00'
```

在仓库根目录执行，得到 `OPEN / NIGHT / CONTINUOUS / 20260908`。日期覆盖与更新流程见 [参考年历说明](calendars/README.md)。

`/api/coverage` 保留原产品/月分组与计数，增加 exchange、各交易所 requested_days；SHFE 针对当前/下一逻辑交易日核对清单。旧 CFFEX manifest 仍可读取；缺少AU/AG不能声明多市场全覆盖。日历失效会让SHFE清单状态未知/过期，但不会抹去有效的CTP订阅证据或把无推送当失败。
