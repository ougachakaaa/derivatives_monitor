# Futures Coverage Specification

## 产品全集

必须覆盖 CFFEX 股指期货：`IH`、`IF`、`IC`、`IM`。

## Probe 验收

对每个产品分别确认并留证：

- 当前有效合约能否由来源动态发现，而非只请求预先知道的合约；
- 至少对当前月和下一月合约记录来源使用的 contract code；
- snapshot quote 能否获取及其 raw response 结构；
- quote 中可识别的价格、成交量、持仓量、时间和买卖盘字段；
- 1 分钟数据能否获取及其 raw response 结构；如只支持其他粒度，记录实际能力；
- 缺失合约、空字段、无来源时间戳等限制。

不得把 Reference 示例中的 `2609` 硬编码为当前合约，也不得在保存 raw payload 前套用历史字段位置。

