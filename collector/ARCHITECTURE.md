<a id="collector-internal-architecture"></a>

# Collector 内部结构

本文件只描述 `collector/` C++ runtime 的内部关系。跨模块数据流和部署拓扑见[根 Architecture](../ARCHITECTURE.md)；精确行为见本级 [Contract](CONTRACT.md)。`collector/scripts/` 是单独的工具 scope，由其[入口](scripts/README.md)导航，不属于以下运行时调用链。

```text
src/app/main.cpp → src/config/config.hpp → src/app/runtime.cpp
                                             ├─ src/ingestion/session.* → CTP MdApi callbacks
                                             ├─ src/domain/market.* → AlignedBarAggregator / MarketBar
                                             ├─ src/persistence/sqlite_store.* → daily Raw SQLite
                                             └─ src/observability/health.* → status publication
```

- `app/` 拥有 CLI、进程信号和 runtime 编排；runtime 只协调各 owner，不定义行情或 SQLite 语义。
- `config/` 拥有 INI 到运行配置的解析、固定键白名单和字段校验。
- `ingestion/` 隔离 MdApi 连接、登录、订阅和 callback 状态；callback 立即复制行情并交给 `AlignedBarAggregator`，不直接写 SQLite。
- `domain/` 以 CTP event time 按 `(TradingDay, InstrumentID)` 维护自然时间对齐的 15 秒 bucket、累计 baseline 与 continuity，并输出领域对象 `MarketBar`。
- `persistence/` 是 canonical `market_bars` 的唯一 Raw writer 边界；它与只读消费者共同遵守的 schema、身份、目录所有权、锁、WAL 与发布协议由[共享 Raw Boundary](../docs/contracts/raw-boundary.md)定义。
- `observability/` 发布共享诊断投影；字段和消费者解释仍由 Raw Boundary 拥有。

C++ runtime 不导入或启动 Query/Dashboard。系统级 manager、Compose 与三服务生命周期由[根 Deployment Contract](../docs/contracts/deployment.md)约束；前台 runner 的命令面、输入解析与所有权由 [Developer Runner Contract](../docs/contracts/developer-runner.md)约束。
