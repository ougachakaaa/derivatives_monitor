# Coverage Experiment Specification

## 全局目标

每个 Data Type → Source 实验必须用可重复的 Probe 和保存的真实响应，证明目标标的的发现能力、请求方式和返回结构。

具体覆盖全集由局部 Spec 定义：

- `index/SPEC.md`：7 个指数；
- `futures/SPEC.md`：IH、IF、IC、IM；
- `options/SPEC.md`：HO、IO、MO 的 expiry discovery 与完整期权链。

## 状态定义

| 状态 | 判定 |
|---|---|
| `SUPPORTED` | 本 Spec 要求的发现、获取和证据均已由成功实测确认。 |
| `PARTIAL` | 已有成功证据，但一个或多个必需标的、层级、字段或请求能力缺失。 |
| `UNSUPPORTED` | 经可复查的多次尝试或来源明确限制，确认该能力不可用；不能由单次失败得出。 |
| `NOT_TESTED` | 尚未运行，或现有失败不足以形成覆盖结论。 |

覆盖矩阵应按足够细的能力维度记录状态，避免用一个聚合状态掩盖部分缺失。

## 必需证据

每项 `SUPPORTED` 或 `PARTIAL` 结论至少要能追溯到：

1. 可重复执行的 Probe Code；
2. 请求 endpoint、参数和接收时间；
3. raw / near-raw response sample；
4. 对 identifier、返回结构、字段和缺失值的简短说明；
5. coverage matrix 中的样板路径和备注。

原始样板应足以离线判断单条/批量结构、字段类型、timestamp 表达和 null/missing 行为。失败证据应记录 HTTP 状态或异常摘要，但不保存秘密。

## 实验报告

`report.md` 必须说明：

- 实际验证的标的、能力与时间；
- 成功获得和未获得的内容；
- raw sample 的相对路径；
- 推断、限制和未解决问题；
- 需要另行开展的 latency、stability 或 deployment 验证（如有）。

## 非验收项

本 Coverage Harness 不要求实时性基准、稳定性长测、轮询频率、CloudBase 网络表现、broker comparison、IV/Greeks/basis、监控规则、告警或任何 production architecture。

