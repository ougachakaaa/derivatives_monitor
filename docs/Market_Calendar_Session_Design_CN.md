# Market Calendar / Session 与 SHFE AU、AG 设计

2026-09-07。实施前已阅读 Collector、universe、native manager、coverage、Query、Dashboard、采集/读路径约束及现有测试。

## 当前实现与边界

C++ 接受精确合约代码，按源 TradingDay 分区，默认 15 秒物化；不需要新增交易所分支。CFFEX-only 假设在 Python universe 的产品表/正则、Query coverage 分组与自然日清单核对、Dashboard 标题，以及 native discovery 说明。现有 11 个 CFFEX 产品含国债期货，不仅是股指。

新增纯标准库 `query/market_calendar.py` 和版本化 `query/calendars/2026.json`。模块不依赖 FastAPI、SQLite 或 Collector，可独立 CLI/导入；Query 提供只读接口，独立 universe 工具复用日历选择各交易所清单日期。C++ 不加载日历、不根据时间过滤 callback、不改采样或生命周期。Python 仅管理公开参考清单与时段解释，不写 Raw SQLite。

## 已核对的官方依据

- [SHFE 2026 休市及取消夜盘日期](https://www.shfe.cn/services/calenderandholidays/holiday/)：周末调休不等于交易所开市；春节前 2/13、清明前 4/3、劳动节前 4/30、端午前 6/18、中秋前 9/24、国庆前 9/30 无夜盘；2025/12/31 无元旦前夜盘。
- [CFFEX 2026 休市安排](https://www.cffex.com.cn/en_new/Notices/20251217/46426.html)：交易所自己的年历，不使用国务院调休上班日直接推断。
- [SHFE 交易时间](https://www.shfe.cn/services/calenderandholidays/tradinghours/)：AU/AG 连续夜盘 21:00–次日02:30；日盘09:00–10:15、10:30–11:30、13:30–15:00；另有日/夜开盘前五分钟集合竞价。
- [SHFE 连续交易说明](https://www.shfe.com.cn/docview/docview_35218417.htm)：周一至周五晚间开始；普通周五夜盘延续至周六凌晨，归属下一个交易日，并非周日夜盘。
- [CFFEX IF](https://www.cffex.com.cn/hs300/)、[TL](https://www.cffex.com.cn/30tl/)、[股指期权细则](https://www.cffex.com.cn/ssxz/20221214/43100.html)：股指期货13:00–15:00、国债13:00–15:15；期权连续竞价截至14:57，之后收盘集合竞价。产品级会话不是单合约到期日交易资格，国债到期日仅上午交易的例外不应由产品状态替代合约元数据。
- 官方黄金页面加载 [api.js](https://www.shfe.com.cn/images/api.js) 的 ContractBaseInfo 日期接口；现场读取 [20260907](https://www.shfe.com.cn/data/busiparamdata/future/ContractBaseInfo20260907.dat) 与 [20260908](https://www.shfe.com.cn/data/busiparamdata/future/ContractBaseInfo20260908.dat)，确认字段 INSTRUMENTID、EXCHANGEID、COMMODITYID、TRADINGDAY、OPENDATE、EXPIREDATE。精确代码小写 au/ag；不采集接口中的价格。

## Calendar / Session 契约

- 版本化参考文件显式列出每交易所的交易日及 SHFE 每个交易日对应的 night_start 自然日期（无夜盘为 null），附来源、核对日期、有效自然日期范围。年历从官方年公告人工核对后生成并审查，运行时不抓取网页，不以周一到周五兜底。临时休市通过修订对应交易日/night_start 表达，保留版本与来源。
- 首版覆盖 2026。缺失、损坏、范围外或无法确认跨年下一交易日时返回 UNKNOWN 和原因；不把未知当 CLOSED/OPEN。更新方式为审核新文件、CLI 校验、测试后原子替换/发布并重启只读 Query；旧文件保留在 Git，更新失败不影响 Collector。
- Asia/Shanghai 为解释时区；输入必须带时区，统一转换。会话区间左闭右开；night_start 的次日02:30仍归同一 trading_day。日盘段间为 BREAK；夜盘结束到日盘开始、周末/节假日及盘后为 CLOSED。
- 输出 exchange/product、as_of、trading_day、market_state（OPEN/BREAK/CLOSED/UNKNOWN）、session（DAY/NIGHT/null）、phase（CONTINUOUS/AUCTION/null）、is_continuous、当前区间、最近已开始的有效连续时段与下一连续时段。OPEN 包含集合竞价但 is_continuous=false；quote_expected 只代表连续交易时段应有市场活动，不代表每合约必有推送，不生成报警。
- OPEN/BREAK 的 trading_day 为当前逻辑交易日；CLOSED 使用下一已知有效交易时段所属交易日，同时提供最近时段自己的交易日。没有可确认归属时为 null/UNKNOWN。此推导只解释日历，绝不改写 CTP 事实 TradingDay。
- `GET /api/sessions?exchange=SHFE&product=AU&at=<带时区ISO时间>`；exchange/product 可省略以返回全部/某交易所；product 单独给出非法。默认当前时刻。非法参数400，日历不可用在200响应中明确UNKNOWN。CLI提供同等查询和 `--validate`。

## Universe / Coverage

- 保留原11个CFFEX产品和Sina fallback；增AU/AG期货，拒绝期权及其他商品。manifest v1保留原 products 键，新增 exchange 与各产品 requested_day；源代码/日期/上市日/到期日严格验证，价格不进入持久行情。
- CFFEX保持既有清单刷新日期口径；SHFE使用日历当前/下一逻辑交易日，支持夜盘前发布的次日清单。`--date` 显式指定时两交易所均按该日期查询。缺失日历时保留旧SHFE清单并明确失败，不靠自然日期猜测夜盘归属。
- SHFE来源失败或部分返回时按产品保留未到期旧代码，标记stale/未完整确认；初次SHFE无可用代码不能伪装完整覆盖，已有CFFEX清单继续可用；全量空清单拒绝发布。继续沿用原子generation切换、锁、变化才重启的原流程。
- Query coverage按exchange/product分组，SHFE以各自目标日期核对清单；保留原订阅、无推送、缺口与心跳语义。Dashboard增加独立市场时段表，支持同时CFFEX CLOSED / SHFE OPEN；时段请求失败清空旧状态，绝不改变Collector健康的定义。
- native仍只有既有universe刷新及变更后重启机制；本任务不根据Session启动/停止Collector，不新增Runtime Scheduler。

## 实施与提交

先提交本设计及独立Task Specs，再分别完成T1日历、T2清单、T3只读集成、T4夜盘回归/验收，每逻辑步骤独立commit。实盘配置在当前工作区缺失时不得复用过期文档臆造账号；记录implemented / live acceptance pending及可复现夜盘验收步骤。
