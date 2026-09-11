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

查询示例与 `MARKET_CALENDAR_DIR` 配置见 [Query README](../README.md)。日历更新不会启动、停止或修改 Collector；系统操作见 [Operations](../../docs/operations.md)。
