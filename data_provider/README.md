# Data Provider

Data Provider 是 Query 进程内的只读 Python 源码模块，拥有 Raw read adapter、版本化 Market Calendar、Universe/Collector coverage 和 Market Frame。它不是独立服务、镜像或部署单元；精确行为见 [Contract](CONTRACT.md)与 [Market Frame Contract](contracts/market-frame.md)，当前状态见 [Acceptance](ACCEPTANCE.md)。

从仓库根运行 Calendar CLI：

```bash
python3 -m data_provider.market_calendar --exchange SHFE --product AU --at '2026-09-07T23:30:00+08:00'
python3 -m data_provider.market_calendar --validate data_provider/calendars/2026.json
```

年历维护见 [Calendar README](calendars/README.md)。Calendar 不读取行情、不触发采集启停；Query HTTP 和 Universe 工具都直接消费本模块。

Market Frame 从仓库根使用现有 Query Python 环境运行：

```bash
query/.venv/bin/python -m data_provider.market_frame minute --data-dir collector/data --day 20260908 --instrument MO2609-C-5000 --at '2026-09-08T09:30:00+08:00' --evaluated-at '2026-09-08T09:31:00+08:00'
```

Collector 运行诊断由 `runtime_status.py` 只读访问独立运行库，协议见 [Raw Boundary](../docs/contracts/raw-boundary.md#collector-运行诊断协议)；不依赖行情日库存在。
