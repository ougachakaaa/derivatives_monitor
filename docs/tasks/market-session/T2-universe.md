# T2 AU / AG 官方清单

交付：SHFE ContractBaseInfo adapter及多市场manifest元数据，夜盘逻辑日期查询，native说明与配置文档。只使用官方明确上市小写au/ag期货代码，校验交易所/品种/日期/上市/到期字段；所有11个CFFEX产品保留。

验证：混合产品、期权排除、日期/身份错误、空/损坏/超时、部分响应保留未到期旧代码、不得发布全空、原子generation与失败保护、显式日期优先、SHFE夜盘选下一交易日、旧CFFEXmanifest兼容、不新增会话启停控制。尝试实际公开来源并记录URL/日期/摘要；公开列表成功不代表CTP权限。

完成后独立commit。

完成：官方SHFE adapter、逐交易所目标日期及兼容manifest、保留/原子发布路径、原生夜盘前清单刷新时点已实现。9项universe测试通过；systemd解析新增21:00/21:15日历表达式成功。2026-09-07 23:26实际公开来源发现原CFFEX 714个、AU 8个、AG 12个，共734个；SHFE来源日期20260908。请求与哈希位于 `/tmp/dm-shfe-reference-acceptance/universe/raw/20260907-232617-d15fae49/`。未连接CTP、未发布到实际数据目录、未重启实盘服务。
