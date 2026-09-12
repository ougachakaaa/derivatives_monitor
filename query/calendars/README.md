# Reviewed market reference calendars

本目录保存随 Query 发布、经过审核的版本化交易日历。它是参考输入，不是行情来源；交易日、夜盘归属、Session 状态、UNKNOWN 和 source TradingDay 的精确语义只由 [Market Session Contract](../../docs/contracts/market-session.md) 定义，Query 加载与 coverage 适配见[组件 Contract](../CONTRACT.md#calendar-与-coverage-适配)。

## 更新日历

1. 核对各交易所年度休市公告、临时休市/夜盘取消公告及当前交易时间规则。
2. 从现有文件创建候选版本，更新显式交易日、night anchor、来源 URL、`reviewed_on` 和 `version`；不要覆盖旧版本或在运行时生成候选交易日。
3. 验证候选文件：

   ```bash
   python3 query/market_calendar.py --validate /path/to/candidate.json
   query/.venv/bin/python -m unittest discover -s query/tests -p 'test_calendar.py' -v
   ```

4. 审核通过后随普通代码发布提交。若维护独立 Calendar 目录，先在同一目录暂存并验证，再原子替换；验证失败时保留当前文件不动。

## 来源与官方依据

机器可读的来源清单保存在 [2026.json](2026.json) 的 `exchanges.*.sources`；产品时段 profile 位于 `../market_calendar.py`。更新年历或时段前核对下表并保持一致：

- [SHFE 2026 休市及取消夜盘日期](https://www.shfe.cn/services/calenderandholidays/holiday/)：周末调休不等于交易所开市；春节前 2/13、清明前 4/3、劳动节前 4/30、端午前 6/18、中秋前 9/24、国庆前 9/30 无夜盘；2025/12/31 无元旦前夜盘。
- [CFFEX 2026 休市安排](https://www.cffex.com.cn/en_new/Notices/20251217/46426.html)：交易所自己的年历，不使用国务院调休上班日直接推断。
- [SHFE 交易时间](https://www.shfe.cn/services/calenderandholidays/tradinghours/)：AU/AG 连续夜盘 21:00–次日02:30；日盘09:00–10:15、10:30–11:30、13:30–15:00；另有日/夜开盘前五分钟集合竞价。
- [SHFE 连续交易说明](https://www.shfe.com.cn/docview/docview_35218417.htm)：周一至周五晚间开始；普通周五夜盘延续至周六凌晨，归属下一个交易日，并非周日夜盘。
- [CFFEX IF](https://www.cffex.com.cn/hs300/)、[TL](https://www.cffex.com.cn/30tl/)、[股指期权细则](https://www.cffex.com.cn/ssxz/20221214/43100.html)：股指期货13:00–15:00、国债13:00–15:15；期权连续竞价截至14:57，之后收盘集合竞价。产品级会话不是单合约到期日交易资格，国债到期日仅上午交易的例外不应由产品状态替代合约元数据。

查询示例与 `MARKET_CALENDAR_DIR` 配置见 [Query README](../README.md)。日历更新不会启动、停止或修改 Collector；系统操作见 [Operations](../../docs/operations.md)。
