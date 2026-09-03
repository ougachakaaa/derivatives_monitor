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
3. 按实际响应保存在本地的 raw / near-raw sample；
4. 对实际 identifier、可识别信息和限制的简短说明；
5. Probe 已成功时，从该 sample 生成并提交的版本化解释性 template 与 provenance manifest；
6. coverage matrix 中的持久化 template 路径和备注。

样板的内容、文件格式、扩展名和目录内组织由实际响应决定。应尽量保持收到的内容，只在删除秘密或确有必要时保存 near-raw 版本，并说明改动。raw response 必须保留来源字节与编码；如其不是 UTF-8，应根据响应声明的 charset 生成独立 UTF-8 可读副本，并保留两者的关系和哈希。UTF-8 副本不能替代 raw evidence，也不能在 charset 缺失或解码失败时靠猜测生成。请求上下文可以与响应一起或分开记录，不要求固定 metadata 文件。失败证据应记录足以理解结果的状态或异常摘要，但不保存秘密。

Coverage 验收只规定必须证明的业务语义，不规定字段名、字段顺序、响应层级或 schema。Reference 中的格式信息只能作为 Probe 线索。

## Probe 与 Template 验收

Probe 被证明可运行，至少意味着进程成功结束、局部 Spec 要求的目标范围已取得成功证据、report 与 coverage 已更新，并且 raw body 的大小和 hash 与请求 metadata 一致。此后 timestamped sample run 保留为本地证据并由 Git 忽略，不作为 clean clone 的必备文件。

每个已支持的 Data Type → Source capability 应有可提交的 versioned response template。Template 只归纳样本中实测的结构、类型模式、identifier 映射和带置信度的语义；它不是固定返回格式或生产 schema。Manifest 必须记录版本、来源 run、raw hash、格式指纹与语义指纹。

如果本地存在成功 sample，应先与当前 template 比较：

- 结构与语义一致：维持当前版本，只追加 validation 记录；
- wrapper、分隔方式、逻辑字段结构、位置类型模式或目标 identifier 映射变化：创建下一不可变版本并记录相对上一版的差异；
- 只有行情数值、日期、时间、body 长度或 raw hash 变化：不升级版本；
- 本地 sample 缺失：普通审阅返回 `NO_SAMPLE` 且不访问网络；明确的 Probe 或 refresh 任务可以重新请求并生成 sample。

## 实验报告

实际 Probe 开始时创建 `report.md`，只约定以下大纲，内部组织由实测结果决定：

- `Scope`：实际验证的对象、能力和上下文；
- `Evidence`：Probe Code、请求记录和 samples 的位置；
- `Findings`：从真实响应得出的成功、缺失、限制和结论；
- `Open Questions`：尚未解决的问题及需要另行开展的验证。

## 非验收项

本 Coverage Harness 不要求实时性基准、稳定性长测、轮询频率、CloudBase 网络表现、broker comparison、IV/Greeks/basis、监控规则、告警或任何 production architecture。
