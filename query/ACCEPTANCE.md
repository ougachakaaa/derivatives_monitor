# Query 实现与验证状态

本文件只记录 Query 当前实现、工程证据与缺口；系统 G1–G6/P1/P2 门槛仍由[根 Acceptance](../docs/acceptance.md)汇总。精确行为见[本级 Contract](CONTRACT.md)、[Market State](contracts/market-state.md)、[Skew](contracts/analytics-skew.md)和 [Reference adapter](contracts/references.md)。

## Analytics 数值核心与冻结基线（2026-09-08）

冻结时 `python3 harness/run.py analytics-contract` 通过，覆盖固定状态、12 组数值向量、两条合成链及插值例；独立 QuantLib 1.40 / mpmath 1.3.0 环境实际运行 `harness/analytics_oracle.py` 并可一致比较。两条 tick 舍入链约为 `+1.1730254434` 与 `−1.1790944252` vol points；均为 SYNTHETIC，不是实际 MO 观测。

`query/analytics.py` 已实现 `black_price`、`solve_iv` 和 `calculate_skew`，只依赖单个 Market State minute frame、显式日参考包、请求时间与调用方的历史标志。生产回归覆盖平坦及正负 Skew、数值向量、利率/日数、平价远期、两翼、同步边界、盘口质量、solver、参考错误、Calendar/session、到期、固定 revision 与 PARTIAL。

这些工程证据不替代已审核生产参考包、真实完整 MO 月链或至少 10 个真实时点的独立对账；G3/P1/P2 仍待验。

## Skew JSON 与参考适配工程证据（2026-09-08）

真实临时 SQLite/FastAPI、明确 TEST DOUBLE 行情和参考覆盖 latest/minute/series、封口与 session、历史/当前、质量/缺口、固定 revision 与 bundle 回放、原文件哈希、导入不覆盖、生产拒绝 SYNTHETIC 及 HTTP 400/404/503。历史报告 `artifacts/harness/20260908T113644Z-analytics-3e874a2f/result.json` 为 PASS；同版本 Query 76 项通过，packaging 报告仅证明构建输入边界。

<a id="query-feature-evidence"></a>

## Feature service / HTTP 工程证据（2026-09-10）

提交 `8c6c900` 与 `351003e` 已实现通用 v1 envelope、显式注册表、`mo-skew-25d-v1` provider 与只读 `POST /api/features/evaluate`。service/provider 6 项及 HTTP 7 项 TEST DOUBLE 回归验证与既有 Skew 数值、时间、状态、质量、scope、sample key 和 evidence 对等，并覆盖严格参数、生产拒绝 SYNTHETIC、Raw 404/503 与未预期异常传播。完整 Query 89 项及 `python3 harness/run.py analytics` 为 PASS（`artifacts/harness/20260910T151944Z-analytics-beea795b/result.json`），docs 报告为 `artifacts/harness/20260910T152100Z-docs-b207185b/result.json`。当时 packaging 报告 `artifacts/harness/20260910T151708Z-packaging-e477e8ee/result.json` 因 Docker 不可用为 FAIL/NOT_RUN，不能写成通过。

## 参考目录路径修复（2026-09-10）

提交 `9cc5870` 使单 Query 与联合启动的 `MARKET_CALENDAR_DIR`、`SKEW_REFERENCE_DIR` 相对路径都按调用目录解析；34 项 developer runner TEST DOUBLE 回归及 docs profile 通过。没有读取生产参考包或真实配置，也未重跑完整 offline/browser/Docker。
