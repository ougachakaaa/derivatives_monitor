# 只读查询后端

[系统架构](../docs/architecture.md) · [只读契约](../docs/contracts/read-path.md) · [验收矩阵](../docs/acceptance.md) · [Harness](../harness/README.md)

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

## Market State Read Model（Python 契约 v1）

`market_state.py` 提供 `Universe`、`Scope`、`MarketStateReader`，不需要启动 HTTP 或调度任务。它是 Analytics 的 Raw 读取边界；`analytics.py` 只消费一个 Market State minute frame、显式 ReferenceBundle 和请求时间，计算 MO 单月 IV/Skew。口径与输入字段见[冻结契约](../docs/contracts/analytics-skew.md)，Market State 完整语义见[设计基线](../docs/contracts/market-state.md)。官方参考导入器和 HTTP 适配尚未实现。

```python
from analytics import calculate_skew

frame = reader.minute(scope, minute, evaluated_at=requested_at,
                      stale_after_us=30_000_000, raw_revision=fixed_revision)
result = calculate_skew(frame, reference_bundle, requested_at, historical=False)
```

`historical` 必须由调用方按 Calendar 选择结果显式传入。结构缺失抛 `ValueError`；完整输入不满足参考、质量、同步或求解前提时返回 `status=UNAVAILABLE` 和原因，不返回旧值或猜测值。结果携带 Raw revision、Universe/Calendar/ReferenceBundle 哈希、算法参数，以及每个 observation 的时间、剔除原因和使用角色。函数不打开 SQLite、不读取 current 文件、不联网，也不保存派生数据。

```python
from datetime import datetime
from storage import Store
from market_state import MarketStateReader, Scope, Universe

reader = MarketStateReader(Store('../collector/data'))
scope = Scope.instrument('MO2609-C-5000', '20260908')
frame = reader.minute(scope, datetime.fromisoformat('2026-09-08T09:30:00+08:00'),
                      evaluated_at=datetime.fromisoformat('2026-09-08T09:31:00+08:00'))
point = reader.as_of(scope, datetime.fromisoformat('2026-09-08T09:30:45+08:00'))
latest = reader.latest(scope, datetime.fromisoformat('2026-09-08T12:00:00+08:00'))
```

分钟 `[09:30,09:31)` 选取严格早于09:31的最新真实 `received_us`，point 包含等于 at 的 observation。同一时段内更早 observation 保留原始时间和 age，不插入/补齐行情。竞价、连续交易和各休息段隔离。未 sealed 的分钟只查询到 `evaluated_at`；sealed 只表示分钟已经结束，不保证 Raw 不再追加迟到 observation。用返回的 `raw_revision` 参数可重放同一 append-only 日库切片。

每个 scope 成员对应一条 `rows`：`observation` 是原始事实（无行情则 null），`quality` 含 `quote_age_us`、missing/stale/invalid/usable 和原因。默认一级双边价格、挂量有效且 age ≤60秒才 usable；可显式传 `stale_after_us`。最新 invalid 不回退到旧报价。`completeness` 是 COMPLETE/PARTIAL/EMPTY；清单不完整时不会 COMPLETE。

完整产品/月/期权链需显式提供清单，不能从 Raw 出现过的代码推断全量：

```python
# saved_manifest 是调用者明确选择、保存的历史 manifest；不会自动读取 current。
universe = Universe.from_manifest(saved_manifest, 'CFFEX', 'MO', '20260908', 'saved-generation-id')
chain = Scope.select(universe, 'CFFEX', 'MO', month='2609', option_chain=True)
chain_frame = reader.minute(chain, minute, evaluated_at=evaluated_at)
# 不传 month 得到 product scope；不传 option_chain 得到 month scope。
```

也可直接构造 `Universe(trading_day, version, instruments, complete)`。complete 是调用方对参考清单的声明，版本应标识固定清单；未经验证的清单必须传 False。Latest OPEN 只查当前段；BREAK/CLOSED 返回明确 `historical=true` 的最近已结束段，其 `effective_as_of` 停留在段末，`age_reference` 为请求时刻。CLOSED 的 `calendar_trading_day` 可能是下一交易日，scope day 必须使用历史 frame 的实际交易日。UNKNOWN 不构造 frame；缺库/不可读仍报错，不伪装 EMPTY、不搜索更旧的有行情日。

命令行从仓库根目录运行：

```bash
query/.venv/bin/python query/market_state.py minute \
  --data-dir collector/data --day 20260908 --instrument MO2609-C-5000 \
  --at '2026-09-08T09:30:00+08:00' --evaluated-at '2026-09-08T09:31:00+08:00'
```

产品/月/链用 `--universe saved-universe.json --exchange CFFEX --product MO --month 2609 --option-chain` 替换 `--instrument`。JSON 格式为 `{"trading_day":"20260908","version":"saved-v1","instruments":["MO2609-C-5000","MO2609-P-5000"],"complete":false}`；示例的两个合约不能声称真实完整链。`as-of` / `latest` 使用 `--at` 且不传 `--evaluated-at`。输出 JSON，查询错误退出码2。
