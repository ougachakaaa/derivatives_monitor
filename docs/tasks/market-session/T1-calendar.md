# T1 日历与时段

交付：纯标准库模块、2026官方参考年历、CLI、来源与更新文档。显式exchange/product profiles与night_start→trading_day映射；集合竞价独立phase；未知日历不可猜测。

验证：所有连续/休息边界，AU/AG跨00:00、普通周五夜盘→周一、周日无夜盘、春节/国庆/元旦、节前取消夜盘、调休周末不开市、节后首日日盘、CFFEX期权14:57与国债15:15、带时区转换、无时区拒绝、最近时段、年界/缺失/损坏日历、独立CLI不导入FastAPI或SQLite。

完成后独立commit；不修改Collector。
