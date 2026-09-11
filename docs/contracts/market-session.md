<a id="market-session-shared-contract"></a>

# Market Calendar / Session 与 SHFE AU、AG 设计


Calendar 和 Universe 是独立参考能力，不进入 C++ callback 或 Raw 写入链路。C++ 接受精确代码、源 TradingDay 分区、默认 15 秒物化，无交易所专用分支。当前覆盖原有 11 个 CFFEX 品种与 SHFE AU/AG 期货。

Query 的 Calendar/coverage 适配见 [Query Contract](../../query/CONTRACT.md#calendar-与-coverage-适配)；独立 universe 工具使用同一共享日历协议选择来源日期。来源链接是 2026-09-07/08 的既有设计依据，整理时未重新核对交易所规则。

## 已核对的官方依据

- [SHFE 2026 休市及取消夜盘日期](https://www.shfe.cn/services/calenderandholidays/holiday/)：周末调休不等于交易所开市；春节前 2/13、清明前 4/3、劳动节前 4/30、端午前 6/18、中秋前 9/24、国庆前 9/30 无夜盘；2025/12/31 无元旦前夜盘。
- [CFFEX 2026 休市安排](https://www.cffex.com.cn/en_new/Notices/20251217/46426.html)：交易所自己的年历，不使用国务院调休上班日直接推断。
- [SHFE 交易时间](https://www.shfe.cn/services/calenderandholidays/tradinghours/)：AU/AG 连续夜盘 21:00–次日02:30；日盘09:00–10:15、10:30–11:30、13:30–15:00；另有日/夜开盘前五分钟集合竞价。
- [SHFE 连续交易说明](https://www.shfe.com.cn/docview/docview_35218417.htm)：周一至周五晚间开始；普通周五夜盘延续至周六凌晨，归属下一个交易日，并非周日夜盘。
- [CFFEX IF](https://www.cffex.com.cn/hs300/)、[TL](https://www.cffex.com.cn/30tl/)、[股指期权细则](https://www.cffex.com.cn/ssxz/20221214/43100.html)：股指期货13:00–15:00、国债13:00–15:15；期权连续竞价截至14:57，之后收盘集合竞价。产品级会话不是单合约到期日交易资格，国债到期日仅上午交易的例外不应由产品状态替代合约元数据。
- 官方黄金页面加载 [api.js](https://www.shfe.com.cn/images/api.js) 的 ContractBaseInfo 日期接口；现场读取 [20260907](https://www.shfe.com.cn/data/busiparamdata/future/ContractBaseInfo20260907.dat) 与 [20260908](https://www.shfe.com.cn/data/busiparamdata/future/ContractBaseInfo20260908.dat)，确认字段 INSTRUMENTID、EXCHANGEID、COMMODITYID、TRADINGDAY、OPENDATE、EXPIREDATE。精确代码小写 au/ag；不采集接口中的价格。

## Calendar / Session 契约

- 版本化参考文件显式列出每交易所的交易日及 SHFE 每个交易日对应的 night_start 自然日期（无夜盘为 null），附来源、核对日期、有效自然日期范围。年历从官方年公告人工核对后生成并审查，运行时不抓取网页，不以周一到周五兜底。临时休市通过修订对应交易日/night_start 表达，保留版本与来源。
- 首版覆盖 2026。缺失、损坏、范围外或无法确认跨年下一交易日时返回 UNKNOWN 和原因；不把未知当 CLOSED/OPEN。更新方式为审核新文件、CLI 校验、测试后原子替换/发布；JSON 下次请求生效，profile 代码发布才需重启 Query；旧文件保留在 Git，更新失败不影响 Collector。
- Asia/Shanghai 为解释时区；输入必须带时区，统一转换。会话区间左闭右开；night_start 的次日02:30仍归同一 trading_day。日盘段间为 BREAK；夜盘结束到日盘开始、周末/节假日及盘后为 CLOSED。
- 输出 exchange/product、as_of、trading_day、market_state（OPEN/BREAK/CLOSED/UNKNOWN）、session（DAY/NIGHT/null）、phase（CONTINUOUS/AUCTION/null）、is_continuous、当前区间、最近已开始的有效连续时段与下一连续时段。OPEN 包含集合竞价但 is_continuous=false；quote_expected 只代表连续交易时段应有市场活动，不代表每合约必有推送，不生成报警。
- OPEN/BREAK 的 trading_day 为当前逻辑交易日；CLOSED 使用下一已知有效交易时段所属交易日，同时提供最近时段自己的交易日。没有可确认归属时为 null/UNKNOWN。此推导只解释日历，绝不改写 CTP 事实 TradingDay。
- `GET /api/sessions?exchange=SHFE&product=AU&at=<带时区ISO时间>`；exchange/product 可省略以返回全部/某交易所；product 单独给出非法。默认当前时刻。非法参数400，日历不可用在200响应中明确UNKNOWN。CLI提供同等查询和 `--validate`。

## Universe / Coverage 共享交接

- Universe manifest v1 保留原 `products` 键，并向生产者与消费者共享 exchange、各产品 requested day、来源、完整性及 stale/error 状态。清单只提供精确订阅代码与审核元数据，不把来源价格转成 Raw 行情，也不改写 CTP `TradingDay`。
- Universe 工具使用本 Calendar 的逻辑交易日选择 SHFE 来源日；显式日期同时作为两交易所 requested day。Calendar 无法确认时必须以未知/失败交接，不能由消费者按自然日期补猜。具体来源抓取、字段校验、旧代码保留、generation 发布与可选重启归 [Universe Tool Contract](../../collector/scripts/CONTRACT.md)。
- Query coverage 按 exchange/product 分组，SHFE 以各自目标日期核对清单；保留原订阅、无推送、缺口与心跳语义。页面如何并列展示各市场及在请求失败时清理状态由 [Dashboard Contract](../../dashboard/CONTRACT.md#dashboard-session-contract)定义。
- Market Session 只解释市场时段，不据此启动或停止 Collector，也不新增 Runtime Scheduler。repository manager 的三服务生命周期见 [Deployment Contract](deployment.md)。

## 维护与验收

年历更新步骤见[参考年历说明](../../query/calendars/README.md)。SHFE 清单成功与真实行情权限分别验收；跨零点及次日日盘真实连续证据仍待补齐，见[验收矩阵](../acceptance.md)。合成时钟测试不能替代实盘记录。
