# 只读查询后端

Query 是 Python 3.12 / FastAPI 服务：读取 Collector 的 Raw 数据，提供诊断、Market Session、Market State 和 MO Skew JSON。这里提供安装、启动、调用和排障方法；组件边界见[系统架构](../docs/architecture.md)，HTTP 与只读行为见 [Read Path Contract](../docs/contracts/read-path.md)。

领域契约：[Market State](../docs/contracts/market-state.md) · [Market Session](../docs/contracts/market-session.md) · [Analytics / Skew](../docs/contracts/analytics-skew.md) · [Acceptance](../docs/acceptance.md) · [Harness](../harness/README.md)

统一前台开发入口位于仓库根：`./dev doctor query` 检查本组件，`./dev query` 运行本组件，`./dev up` 运行完整开发会话。参数示例和与持久部署的区别见 [Operations](../docs/operations.md#前台开发会话)；下面保留 Query 自身的安装、直接运行和调用用法。

## 安装、启动与测试

从 `query/` 目录执行：

```bash
poetry config virtualenvs.in-project true --local
poetry sync
DATA_DIR=../collector/data poetry run uvicorn app:app --host 127.0.0.1 --port 8000
```

FastAPI 文档默认位于 **http://127.0.0.1:8000/docs**。运行完整 Query 测试：

```bash
poetry run python -m unittest discover -s tests -v
```

Docker 构建使用同一 `poetry.lock` 并执行测试；系统级启动使用仓库根 `./scripts/deploy.sh up`，具体运维步骤见 [Operations](../docs/operations.md)。

## 运行配置

| 环境变量 | 用途 |
|---|---|
| `DATA_DIR` | Raw 数据目录；本地示例为 `../collector/data`，容器默认 `/data` |
| `MARKET_CALENDAR_DIR` | 可选 Calendar 目录；默认使用随 Query 发布的 `calendars/` |
| `SKEW_REFERENCE_DIR` | 可选审核参考包目录；默认 `${DATA_DIR}/references/analytics` |
| `SKEW_TARGET_MONTH` | 可选默认 MO 月；请求仍可显式传 `month` |

Query 不需要 CTP 凭据。生产挂载、只读权限、端口和服务生命周期以 [Deployment Contract](../docs/contracts/deployment.md) 为准。

## HTTP 入口

| 请求 | 用途 |
|---|---|
| `GET /healthz` | Query 进程存活 |
| `GET /api/health` | 数据目录与 Collector 运行诊断 |
| `GET /api/coverage` | 清单、订阅、接收和缺口摘要 |
| `GET /api/sessions` | 交易所/品种的 Market Session 查询 |
| `GET /api/days` | 可用 Raw 日文件 |
| `GET /api/summary?day=YYYYMMDD` | 指定日汇总 |
| `GET /api/snapshots?day=YYYYMMDD&instrument=CODE&limit=50` | 最近 Raw snapshot |
| `GET /api/skew/latest?month=YYMM` | 最近可展示的 MO Skew |
| `GET /api/skew/series?day=YYYYMMDD&month=YYMM` | 当日分钟序列和变化 |
| `GET /api/skew/minute?day=YYYYMMDD&minute=ISO&month=YYMM` | 指定分钟回看 |
| `GET /docs` | OpenAPI 交互文档 |

上表用于快速调用，不定义参数校验、状态、错误或业务语义。诊断及 HTTP 失败语义见 [Read Path Contract](../docs/contracts/read-path.md)；Market Session 和 Skew 结果分别见对应领域 Contract。

## Market Calendar CLI

无需启动 HTTP 即可查询或验证 Calendar：

```bash
python3 query/market_calendar.py --exchange SHFE --product AU --at '2026-09-07T23:30:00+08:00'

python3 query/market_calendar.py --validate query/calendars/2026.json
```

输入需使用带时区时间。Calendar 的交易日、OPEN/BREAK/CLOSED/UNKNOWN、夜盘归属和 source TradingDay 边界由 [Market Session Contract](../docs/contracts/market-session.md) 定义；参考文件维护见 [Calendar README](calendars/README.md)。

## Market State Python / CLI

`market_state.py` 可作为 Python 读模型使用：

```python
from datetime import datetime
from market_state import MarketStateReader, Scope
from storage import Store

reader = MarketStateReader(Store("../collector/data"))
scope = Scope.instrument("MO2609-C-5000", "20260908")
frame = reader.minute(
    scope,
    datetime.fromisoformat("2026-09-08T09:30:00+08:00"),
    evaluated_at=datetime.fromisoformat("2026-09-08T09:31:00+08:00"),
)
```

从仓库根目录运行等价 CLI：

```bash
query/.venv/bin/python query/market_state.py minute --data-dir collector/data --day 20260908 --instrument MO2609-C-5000 --at '2026-09-08T09:30:00+08:00' --evaluated-at '2026-09-08T09:31:00+08:00'
```

产品、月份或期权链读取需要通过 `--universe` 显式提供保存的 Universe；查看完整参数用 `--help`。Scope、分钟选择、revision、quality、freshness、完整性和失败语义只由 [Market State Contract](../docs/contracts/market-state.md) 定义。

## Skew API

后端启动后可直接调用 JSON，无需启动 Dashboard：

```bash
curl --get http://127.0.0.1:8000/api/skew/latest --data-urlencode 'month=2610'

curl --get http://127.0.0.1:8000/api/skew/series --data-urlencode 'month=2610' --data-urlencode 'day=20260916'

curl --get http://127.0.0.1:8000/api/skew/minute --data-urlencode 'month=2610' --data-urlencode 'day=20260916' --data-urlencode 'minute=2026-09-16T09:30:00+08:00'
```

示例日期和月份只展示调用格式，不代表存在生产参考包或真实市场验收。查询参数和 JSON 投影见 [Read Path Contract](../docs/contracts/read-path.md)；算法、ReferenceBundle、质量、重放和不可计算原因见 [Analytics / Skew Contract](../docs/contracts/analytics-skew.md)。

## 审核参考包的离线导入

参考包是 Query 的只读输入。运维包目录至少包含：

```text
audited-package/
  manifest.json
  bundle.json
  universe.json
  calendar.json
  listing.source
  rules.source
  rate.source
```

包内容必须符合 [Analytics / Skew Contract](../docs/contracts/analytics-skew.md)。导入器会验证并复制已有审核包，但不会联网抓取、替代人工审核或修改 Raw：

```bash
query/.venv/bin/python query/skew_references.py /path/to/audited-package --directory /path/to/references/analytics
```

导入结果位于 `<directory>/<trading_day>/<bundle_id>/`，已有 bundle ID 不覆盖。审核者随后在同一 trading day 目录原子发布 `<month>.json` 选择文件：

```json
{"bundle_id":"reviewed-mo2610-v1"}
```

生产与 TEST DOUBLE 的准入、文件身份、哈希、来源、版本及重放规则不在 README 重复，统一以 Contract 为准。

## 回归与排障

- Query 单元/集成测试：`cd query && poetry run python -m unittest discover -s tests -v`。
- Analytics 与 Skew HTTP TEST DOUBLE 回归：`python3 harness/run.py analytics`。
- 完整离线工程回归：`python3 harness/run.py offline`。
- 返回参考缺失、日历未知、质量不可用或固定 revision 问题时，先保留完整 JSON reason/identity，再查相应 Contract；不要用默认值或旧结果绕过错误。
- 历史日因 WAL/sidecar/锁不可读时，不要改成读写挂载或删除 WAL；按 [Operations](../docs/operations.md) 正常停采或做隔离恢复。
- 自动测试和 TEST DOUBLE 不能证明真实 MO 数据或生产参考包已验收；当前证据边界见 [Acceptance](../docs/acceptance.md)。
