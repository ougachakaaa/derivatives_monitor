# Harness Design

## 边界

`experiments/data_coverage` 回答三个问题：目标数据是否覆盖、真实返回结构是什么、哪些原始证据支持结论。它不定义 `src/market_data`，也不承诺生产接口、存储模型或运行方式。

## 为什么按 Data Type → Source 组织

任务通常从“我需要指数、期货或期权数据”开始，再比较能提供它的数据源。因此顶层按数据类型拆分，第二层按来源拆分。局部 `REFERENCE.md` 只保留该组合需要的 endpoint 和资料，使 Probe 可以渐进式读取，也让未来 Sina、EastMoney、Tencent、CTP 等来源并排比较而不相互耦合。

## 为什么 samples 是核心产物

公开 Web endpoint 的字段、顺序和编码只能由实测确认。原始或近原始样板允许后续工作在不重新调用来源的情况下：

- 复核 instrument identifier、字段名、类型和时间戳；
- 观察 null、缺失值、单条与批量结构；
- 重新设计或测试解析器；
- 区分来源事实与人工推断。

因此先存响应，再做解释；规范化示例不能替代原始证据。

## 扩展方式

新增来源时，在每个相关数据类型下增加独立来源目录，并提供局部入口、局部 Reference、samples、coverage 和 report。共享的状态语义与证据要求只在根 `SPEC.md` 定义；数据类型要求只在各自 `SPEC.md` 定义，避免重复。

## 后续工作而非本 Harness 验收项

来源通过覆盖验证后，可以另行进行实时延迟、持续稳定性、保守轮询、broker terminal 对比、CloudBase 网络可用性及 production adapter 设计。这些问题可以写入 report 的 Future Work，但不能阻塞本阶段 Harness 的建立。

