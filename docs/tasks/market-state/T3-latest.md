# T3 Latest 与入口

Spec：OPEN 查询当前 period，BREAK/CLOSED 返回显式历史 frame，UNKNOWN 无 frame；实际 frame day 与日历下一交易日分离；休市 age 以请求 at 增长。不跨 session 或无数据日兜底。提供 Python/JSON CLI 示例并随 Docker 镜像发布，无新增调度/HTTP/Analytics。

验证：开盘缺失、午休、盘后竞价、周末、SHFE跨午夜、UNKNOWN；CLI 实际执行；回归现有 Query。
