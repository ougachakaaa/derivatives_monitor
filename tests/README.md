# Repository Verification

根 `tests/` 拥有跨模块测试与 repository-level verification。模块内部行为、fixture、oracle 和 SDK 校验留在对应模块；本目录的 runner 只选择 scope、调用 owner 入口、聚合结果并保存证据。结果分类、TEST DOUBLE、证据身份和现场边界统一见[验证证据语义](../docs/verification.md)。

<a id="profiles"></a>

## Profiles

从仓库根目录运行：

```bash
python3 tests/run.py docs
python3 tests/run.py analytics-contract
python3 tests/run.py analytics
python3 tests/run.py offline
python3 tests/run.py native
python3 tests/run.py browser
python3 tests/run.py packaging
python3 tests/run.py docker
```

| Profile | 前提与动作 |
|---|---|
| `docs` | 检查链接、authority、依赖方向、模块 Docker policy、Collector SDK manifest，并运行检查器自测；不访问外网 |
| `analytics-contract` | 标准库核对 Analytics 拥有的冻结策略、fixture、生成器哈希、价格/IV/delta/远期/两翼及失败回归 |
| `analytics` | 在 contract 检查上运行生产 Analytics、Skew HTTP 与临时 SQLite TEST DOUBLE 回归 |
| `offline` | 重建 Collector，运行 CTest、developer runner、Query、Universe、部署替身、SQLite CLI、React 与前端构建 |
| `native` | 重建 Collector，运行合成夜盘和真实 HTTP 独立停启测试；仅临时数据和随机端口 |
| `browser` | `native` 范围加 Playwright 浏览器闭环 |
| `packaging` | 用三个 Dockerfile 的 `context-audit` 导出实际上下文，按模块 policy 核对精确文件与字节 |
| `docker` | 包含 `packaging`，再通过隔离 Compose 项目运行三容器 read path 与 Collector 生命周期测试 |

每个 profile 独立；缺依赖、跳过或零项测试按 `NOT_RUN` 处理，不能由其他 profile 的通过替代。`browser` 已覆盖 native HTTP，无需为同一版本重复运行 `native`。报告写入 `artifacts/verification/<UTC>-<profile>-<id>/`。

## Ownership

- `collector/tests/`：Collector runtime、配置、SDK、存储、部署替身与容器生命周期。
- `data_provider/tests/`：Raw read、Calendar、coverage 与 Market Frame owner 行为。
- `analytics/tests/`：Skew 数值/service、冻结 fixture、contract checker 与独立 oracle；`query/tests/`：HTTP adapter 与当前 Market Indicator integration。
- `dashboard/tests/`：React 组件和浏览器交互。
- `tests/`：runner、文档与 repository invariants、developer runner、跨进程和 Docker 闭环。

生产与 TEST DOUBLE 的边界、报告字段和现场门槛见[验证证据语义](../docs/verification.md)，当前缺口见[根 Acceptance](../docs/acceptance.md)及各模块 Acceptance。

## Targeted Commands

Developer runner：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_dev*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 tests/dev_runner_smoke.py
```

Analytics / Skew：

```bash
python3 analytics/tests/analytics_contract.py
python3 -m unittest analytics.tests.test_analytics_contract -v
```

外部 oracle 仅在独立环境中复核，不加入生产依赖；默认比较且不覆盖 fixture：

```bash
python3 -m venv artifacts/analytics-oracle-env
artifacts/analytics-oracle-env/bin/python -m pip install -r analytics/tests/analytics-oracle-requirements.txt
artifacts/analytics-oracle-env/bin/python analytics/tests/analytics_oracle.py
```

生成器拒绝覆盖已有输出。不得因实现失败重生成 expected、修改冻结容差，或把合成结果登记为真实行情验收。
