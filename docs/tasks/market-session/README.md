# Market Session 实施任务

依据：[整体设计](../../Market_Calendar_Session_Design_CN.md)。保留C++唯一Raw writer、源TradingDay、15秒物化及现有CTP生命周期。

1. [T1 日历与时段](T1-calendar.md)
2. [T2 SHFE universe](T2-universe.md)
3. [T3 Query / Dashboard](T3-read-path.md)
4. [T4 夜盘与回归验收](T4-acceptance.md)

每步实现、验证并独立提交；只读能力不控制Collector生命周期。
