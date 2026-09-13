<a id="market-session-shared-contract"></a>

# Market Calendar / Session 共享契约


Calendar 和 Universe 是独立参考能力，不进入 C++ callback 或 Raw 写入链路；采集侧的精确代码、分区与采样规则见 [Collector Contract](../../collector/CONTRACT.md)。采集范围由 [MVP](../mvp.md)定义。

Data Provider 的 Calendar 适配见 [Data Provider Contract](../../data_provider/CONTRACT.md#data-provider-calendar-contract)；独立 universe 工具使用同一共享日历协议选择来源日期。官方来源与年历维护见[参考年历说明](../../data_provider/calendars/README.md)。

## Calendar / Session 契约

- 版本化参考文件显式列出每交易所的交易日及 SHFE 每个交易日对应的 night_start 自然日期（无夜盘为 null）；文件字段与来源清单见[参考年历说明](../../data_provider/calendars/README.md)。年历从官方年公告人工核对后生成并审查，运行时不抓取网页，不以周一到周五兜底。临时休市通过修订对应交易日/night_start 表达，保留版本与来源。
- 首版覆盖 2026。缺失、损坏、范围外或无法确认跨年下一交易日时返回 UNKNOWN 和原因；不把未知当 CLOSED/OPEN。年历的审核、校验与发布步骤见[参考年历说明](../../data_provider/calendars/README.md)，加载与生效行为见 [Data Provider Contract](../../data_provider/CONTRACT.md#data-provider-calendar-contract)；更新失败不影响 Collector。
- Asia/Shanghai 为解释时区；输入必须带时区，统一转换。会话区间左闭右开；night_start 的次日02:30仍归同一 trading_day。日盘段间为 BREAK；夜盘结束到日盘开始、周末/节假日及盘后为 CLOSED。
- 输出 exchange/product、as_of、trading_day、session_state（OPEN/BREAK/CLOSED/UNKNOWN）、session（DAY/NIGHT/null）、phase（CONTINUOUS/AUCTION/null）、is_continuous、当前区间、最近已开始的有效连续时段与下一连续时段。OPEN 包含集合竞价但 is_continuous=false；quote_expected 只代表连续交易时段应有市场活动，不代表每合约必有推送，不生成报警。
- OPEN/BREAK 的 trading_day 为当前逻辑交易日；CLOSED 使用下一已知有效交易时段所属交易日，同时提供最近时段自己的交易日。没有可确认归属时为 null/UNKNOWN。此推导只解释日历，绝不改写 CTP 事实 TradingDay。
- 公共 HTTP 入口、参数与错误映射见 [Read Path](read-path.md#市场时段与覆盖)；CLI 提供同等查询和 `--validate`。

## Universe / Coverage 共享交接

- Universe manifest v1 的字段、生成与发布由 [Universe Tool Contract](../../collector/scripts/CONTRACT.md)定义；消费者只使用其中精确订阅代码与审核元数据，按各产品 requested day 与完整性状态交接，不把来源价格转成 Raw 行情，也不改写 CTP `TradingDay`。
- Universe 工具使用本 Calendar 的逻辑交易日选择 SHFE 来源日；显式日期同时作为两交易所 requested day。Calendar 无法确认时必须以未知/失败交接，不能由消费者按自然日期补猜。具体来源抓取、字段校验、旧代码保留、generation 发布与可选重启归 [Universe Tool Contract](../../collector/scripts/CONTRACT.md)。
- Data Provider coverage 的分组、目标日核对与订阅/接收/缺口/stale/进程健康语义见 [Data Provider Contract](../../data_provider/CONTRACT.md#coverage)；页面如何并列展示各市场及在请求失败时清理状态由 [Dashboard Contract](../../dashboard/CONTRACT.md#dashboard-session-contract)定义。
- Market Session 只解释市场时段，不据此启动或停止 Collector，也不新增 Runtime Scheduler。repository manager 的三服务生命周期见 [Deployment Contract](deployment.md)。

## 维护与验收

年历更新步骤见[参考年历说明](../../data_provider/calendars/README.md)。SHFE 清单成功与真实行情权限分别验收；跨零点及次日日盘真实连续证据仍待补齐，见[验收矩阵](../acceptance.md)。合成时钟测试不能替代实盘记录。
