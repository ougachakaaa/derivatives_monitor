# T3 多市场只读展示

交付：/api/sessions接口、exchange-aware coverage、独立市场时段表，Docker打包日历模块/参考文件。市场状态与进程/连接/订阅健康分离，保留原诊断能力。

验证：接口筛选/时区/坏参数、同时CFFEX CLOSED与SHFE OPEN、文件缺失/未知年UNKNOWN、夜盘清单日期、AU/AG订阅与暂无推送计数、无Raw数据仍可查日历、API不写目录、React展示/错误清空/恢复、现有Query和Dashboard回归/生产构建。

完成后独立commit。

完成：/api/sessions、独立标准库调用、13个市场/品种、带交易所和各自日期的coverage、只读参考文件Docker打包、多市场Dashboard及错误清空已实现。Query共22项测试通过；React7项及生产构建通过；补充严格合约类型/月份校验后coverage4项重跑通过。无行情数据目录时日历仍可读取，日历失效不抹除CTP健康/订阅事实。
