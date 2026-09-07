# T2 AU / AG 官方清单

交付：SHFE ContractBaseInfo adapter及多市场manifest元数据，夜盘逻辑日期查询，native说明与配置文档。只使用官方明确上市小写au/ag期货代码，校验交易所/品种/日期/上市/到期字段；所有11个CFFEX产品保留。

验证：混合产品、期权排除、日期/身份错误、空/损坏/超时、部分响应保留未到期旧代码、不得发布全空、原子generation与失败保护、显式日期优先、SHFE夜盘选下一交易日、旧CFFEXmanifest兼容、不新增会话启停控制。尝试实际公开来源并记录URL/日期/摘要；公开列表成功不代表CTP权限。

完成后独立commit。
