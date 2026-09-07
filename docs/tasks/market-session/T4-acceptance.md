# T4 夜盘数据与完整验收

交付：合成CTP夜盘→跨00:00→日盘→新TradingDay端到端回归、只读Query读取验证、操作文档及逐项验收记录。

验证：AU/AG精确代码可订阅；正常物化与停机尾部；自然日期变化不换源TradingDay文件；真实新交易日才建新库；源时间/接收/物化保留；CFFEX共存；WAL/single writer/restart append/reconnect/resubscribe/失败恢复及默认15秒全套CTest。运行universe/Query/React/部署测试与原生浏览器smoke，Docker可用则跑隔离容器验证。

真实AU/AG需有效前置/账号/上市清单并检查逐合约订阅、callback、snapshot、夜盘跨零点及次日日盘。无法实测明确implemented / live acceptance pending，不用synthetic替代。完成能力、记录限制并独立commit。

完成：新增夜盘测试SDK场景与真实C++→Query集成回归；原生7项CTest、Query22项、universe9项、部署9项、只读验收4项、React7项/生产构建、原生Chromium闭环、两套Docker隔离验收通过。实际公开清单734个；真实AU/AG夜盘callback和15秒提交已观察，跨00:00/次日日盘的连续实盘证据pending。详细证据与限制见 [验收记录](../../Market_Session_SHFE_Acceptance_CN.md)。
