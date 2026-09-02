# Harness Design

## 边界

`experiments/data_coverage` 回答三个问题：目标数据是否覆盖、请求实际返回了什么、哪些原始证据支持结论。它不定义 `src/market_data`，也不承诺来源格式、生产接口、存储模型或运行方式。

## 为什么按 Data Type → Source 组织

任务通常从“我需要指数、期货或期权数据”开始，再比较能提供它的数据源。因此顶层按数据类型拆分，第二层按来源拆分。局部 `REFERENCE.md` 只保留该组合需要的 endpoint 和资料，使 Probe 可以渐进式读取，也让未来 Sina、EastMoney、Tencent、CTP 等来源并排比较而不相互耦合。

## 为什么 samples 是核心产物

公开 Web endpoint 的内容和组织只能由实测确认。原始或近原始样板允许后续工作在不重新调用来源的情况下：

- 复核 instrument identifier 及响应实际表达的信息；
- 观察字段、类型、时间戳、空值和批量组织等实际表现；
- 重新设计或测试解析器；
- 区分来源事实与人工推断。

因此先存响应，再做解释；规范化示例不能替代原始证据。

## 扩展方式

新增来源时，在每个相关数据类型下增加独立来源目录，只预建局部 `REFERENCE.md`、`coverage.md` 和 `samples/`。Probe Code 与 report 在实际实验中产生。共享的状态语义、sample 原则和 report 大纲只在根 `SPEC.md` 定义；数据类型要求只在各自 `SPEC.md` 定义。

## 后续工作而非本 Harness 验收项

来源通过覆盖验证后，可以另行进行实时延迟、持续稳定性、保守轮询、broker terminal 对比、CloudBase 网络可用性及 production adapter 设计。这些问题可以写入 report 的 Future Work，但不能阻塞本阶段 Harness 的建立。
