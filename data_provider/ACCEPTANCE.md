# Data Provider 当前状态

Raw read、Calendar 与 Market Frame 已在旧 Raw v1 `snapshots` 上实现，并有临时 SQLite/WAL、版本化 2026 年历、边界/UNKNOWN/CLI TEST DOUBLE 回归。目标 Raw v2 `market_bars` 的 bucket/event-time 选择、partial reasons 与 provenance 尚未实现；旧回归不能证明新契约。真实跨零点、次日日盘和生产数据可用性证据仍以[根验收矩阵](../docs/acceptance.md)为准。

Collector 当前运行事实与 coverage 已接入唯一当前四表运行库协议，按同一事务校验完整 schema，并只读取 `current_status` 与 `instrument_status` 的总体、逐合约身份及计数；完整 Calendar Health evaluator 仍待接入，见[根缺口](../docs/acceptance.md#collector-health-缺口)。
