<a id="query-internal-architecture"></a>

# Query 内部架构

Query 是只读 Python/FastAPI 组件。跨组件数据流、所有权与部署边界见[系统 Architecture](../ARCHITECTURE.md)；这里仅说明 Query 内部文件关系。

```text
storage.py + market_calendar.py
             │
             v
       market_state.py
             │
             v
analytics.py + skew_references.py
             │
             v
       skew_service.py
          ├─ app.py（Skew HTTP）
          └─ feature_service.py（Feature provider）→ app.py（Feature HTTP）
```

- `storage.py` 在共享 Raw 只读协议内访问日 SQLite；`market_calendar.py` 解释版本化 Calendar，并为 Market State 与 coverage 提供日历能力。
- `market_state.py` 将 Raw、显式 Universe 和 Calendar 组合为 point/minute/latest frame，是 Analytics 的行情读取边界。
- `analytics.py` 只消费 Market State frame 与显式参考输入；`skew_references.py` 固定审核包、Universe 和 Calendar 的读取上下文。
- `skew_service.py` 选择业务时间切片并投影公共 Skew 结果；`feature_service.py` 复用该结果形成通用 Feature envelope。二者都不写 Raw 或派生数据库，也不依赖 Dashboard/Monitoring。
- `app.py` 只承接 HTTP 适配。公共路径、wire shape、状态码与 no-store 由 repository [Read Path](../docs/contracts/read-path.md)和 [Feature Contract](../docs/contracts/features.md)拥有。

精确读取、Calendar adapter 与 provider 规则见[本级 Contract](CONTRACT.md)；Market State、Skew 与参考包分别由[领域分卷](contracts/)负责。
