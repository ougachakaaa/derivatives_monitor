# Coverage Experiment Specification

## 全局目标

每个 Data Type → Source 实验必须用可重复的 Probe 和保存的真实响应，证明目标标的的发现能力、请求方式和实际返回内容。

具体覆盖全集由局部 Spec 定义：

- `index/SPEC.md`：7 个指数；
- `futures/SPEC.md`：IH、IF、IC、IM；
- `options/SPEC.md`：HO、IO、MO 的 expiry discovery 与完整期权链。

## 状态定义

| 状态 | 判定 |
|---|---|
| `SUPPORTED` | 本 Spec 要求的发现、获取和证据均已由成功实测确认。 |
| `PARTIAL` | 已有成功证据，但一个或多个必需标的或语义能力缺失。 |
| `UNSUPPORTED` | 经可复查的多次尝试或来源明确限制，确认该能力不可用；不能由单次失败得出。 |
| `NOT_TESTED` | 尚未运行，或现有失败不足以形成覆盖结论。 |

覆盖矩阵应按足够细的能力维度记录状态，避免用一个聚合状态掩盖部分缺失。

## 必需证据

每项 `SUPPORTED` 或 `PARTIAL` 结论至少要能追溯到：

1. 可重复执行的 Probe Code；
2. 足以复核请求的 endpoint、非敏感参数、接收时间和结果上下文；
3. 按实际响应保存的 raw / near-raw sample；
4. 对实际 identifier、可识别信息和限制的简短说明；
5. coverage matrix 中的样板路径和备注。

样板的内容、文件格式、扩展名和目录内组织由实际响应决定。应尽量保持收到的内容，只在删除秘密或确有必要时保存 near-raw 版本，并说明改动。请求上下文可以与响应一起或分开记录，不要求固定 metadata 文件。失败证据应记录足以理解结果的状态或异常摘要，但不保存秘密。

Coverage 验收只规定必须证明的业务语义，不规定字段名、字段顺序、响应层级或 schema。Reference 中的格式信息只能作为 Probe 线索。

## 实验报告

实际 Probe 开始时创建 `report.md`，只约定以下大纲，内部组织由实测结果决定：

- `Scope`：实际验证的对象、能力和上下文；
- `Evidence`：Probe Code、请求记录和 samples 的位置；
- `Findings`：从真实响应得出的成功、缺失、限制和结论；
- `Open Questions`：尚未解决的问题及需要另行开展的验证。

## 非验收项

本 Coverage Harness 不要求实时性基准、稳定性长测、轮询频率、CloudBase 网络表现、broker comparison、IV/Greeks/basis、监控规则、告警或任何 production architecture。
