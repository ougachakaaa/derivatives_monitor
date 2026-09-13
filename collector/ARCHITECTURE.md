<a id="collector-internal-architecture"></a>

# Collector 内部结构

本文件只描述 `collector/` C++ runtime 的内部关系。跨模块数据流和部署拓扑见[根 Architecture](../ARCHITECTURE.md)；精确行为见本级 [Contract](CONTRACT.md)。`collector/scripts/` 是单独的工具 scope，由其[入口](scripts/README.md)导航，不属于以下运行时调用链。

```text
main.cpp → config.hpp → runtime.cpp
                         ├─ session.cpp → CTP MdApi callbacks
                         ├─ market.hpp  → AlignedBarAggregator / MarketBar
                         ├─ storage.cpp → daily Raw SQLite
                         └─ health.hpp  → collector status publication
```

- `main.cpp` 拥有 CLI 解析、配置校验入口和进程信号转为停止请求。
- `session.*` 隔离 MdApi 连接、登录、订阅和 callback 状态；callback 复制行情并交给 `AlignedBarAggregator`，不直接写 SQLite。
- `market.hpp` 以 CTP event time 按 `(TradingDay, InstrumentID)` 维护自然时间对齐的 15 秒 bucket、累计 baseline 与 continuity，并输出领域对象 `MarketBar`。
- `runtime.cpp` 协调 session、自然 bucket 的 1 秒封口 grace、已结束 Bar 提交、状态输出和正常收尾；当前未结束 bucket 不在停机时持久化。
- `storage.*` 是 canonical `market_bars` 的唯一 Raw writer 边界；它与只读消费者共同遵守的 schema、身份、目录所有权、锁、WAL 与发布协议由[共享 Raw Boundary](../docs/contracts/raw-boundary.md)定义。
- `health.hpp` 发布共享诊断投影；字段和消费者解释仍由 Raw Boundary 拥有。

C++ runtime 不导入或启动 Query/Dashboard。系统级 manager、Compose 与三服务生命周期由[根 Deployment Contract](../docs/contracts/deployment.md)约束；前台 runner 的命令面、输入解析与所有权由 [Developer Runner Contract](../docs/contracts/developer-runner.md)约束。
