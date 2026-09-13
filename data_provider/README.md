# Data Provider

Data Provider 是 Query 进程内的只读 Python 源码模块，当前拥有版本化 Market Calendar 与 Market Session 解释。它不是独立服务、镜像或部署单元；共享协议见 [Market Session Contract](../docs/contracts/market-session.md)，当前状态见 [Acceptance](ACCEPTANCE.md)。

从仓库根运行 Calendar CLI：

```bash
python3 -m data_provider.market_calendar --exchange SHFE --product AU --at '2026-09-07T23:30:00+08:00'
python3 -m data_provider.market_calendar --validate data_provider/calendars/2026.json
```

年历维护见 [Calendar README](calendars/README.md)。Calendar 不读取行情、不触发采集启停；Query HTTP 和 Universe 工具都直接消费本模块。
