# Derivatives Monitor — 第一阶段 Data Collector 架构说明

## 1. 文档目的

本文档用于描述 Derivatives Monitor **第一阶段 Data Collector 的架构定位与能力边界**。

本文档刻意不进入具体实现设计。

Codex 应基于：

- 当前仓库结构；
- 现有 CTP Demo / SDK 接入代码；
- 当前项目约定；
- 实际运行环境与依赖；

自行完成具体实现设计。

本文档只定义：

- 第一阶段系统是什么；
- Data Collector 负责什么；
- Data Collector 明确不负责什么；
- 第一阶段必须产出什么 durable data；
- 后续模块如何消费这些数据；
- 哪些架构边界和不变量应保持稳定。

本文档不定义：

- 具体类结构；
- 具体表结构；
- 具体目录布局；
- 具体 HTTP API；
- 具体线程模型；
- 具体 SQL；
- Repository / Port 等接口形式；
- 具体错误类型；
- 具体 snapshot 采样算法。

这些应由 Codex 阅读现有代码后再设计。

---

# 2. 第一阶段的产品形态

第一阶段是一个**本地运行的市场数据采集子系统**。

它的目标不是直接完成完整的 Monitor 产品，而是建立第一个可以独立运行、独立验收、独立产生价值的小闭环：

```text
CTP 实时行情
    ↓
Data Collector
    ↓
按交易日持久化的市场数据集
```

这个阶段最重要的产品属性是：

> 即使 Python 后端没有启动、浏览器没有打开、分析和提醒功能都不存在，行情采集本身依然能够独立运行并持续保存数据。

因此，第一阶段本质上是后续监控产品的 **durable data foundation**。

---

# 3. 当前行情范围

当前第一阶段主要行情源是中信建投期货提供的 CTP 行情接口，用于获取中金所股指衍生品行情。

当前目标市场范围：

### 股指期货

- IF
- IH
- IC
- IM

### 股指期权

- IO
- HO
- MO

根据目前券商侧确认的信息：

- 中金所推送的相关行情可以通过 CTP 收取；
- 行情刷新频率约为每秒 2 次；
- 可以同时订阅相关股指期货和股指期权合约；
- CTP 行情源不提供沪深 300、上证 50、中证 500、中证 1000 等现货指数实时行情。

因此第一阶段的边界应明确：

> CTP Data Collector 只负责期货和期权市场事实采集。

现货指数行情应视为未来独立的数据源能力，不应为了补齐现货指数而复杂化第一阶段最小闭环。

---

# 4. 第一阶段高层架构

第一阶段架构为：

```text
                外部市场
                   │
                   ▼
                  CTP
                   │
                   ▼
          ┌─────────────────┐
          │  Data Collector │
          │      C++        │
          └────────┬────────┘
                   │
                   ▼
             Durable Snapshot
                   │
                   ▼
          ┌─────────────────┐
          │  Daily SQLite   │
          │   Data Files    │
          └─────────────────┘
```

Data Collector 负责完整的：

```text
CTP 行情接收
    ↓
内存市场状态
    ↓
Snapshot 生成
    ↓
本地持久化
```

这条链路不依赖其他运行时组件。

---

# 5. Data Collector 的架构角色

Data Collector 是系统中的：

> **Market Fact Acquisition Boundary**

也就是“市场事实采集边界”。

它的核心职责可以概括为：

> 接收外部市场事实，维护生成 snapshot 所需要的内存状态，将市场状态物化为 durable market snapshot，并可靠保存到当前交易日的数据集中。

Data Collector 不是：

- Analytics Service；
- Browser Backend；
- Monitor Rule Engine；
- Trading Engine。

它的核心任务是：

> 把外部实时行情转化为系统自己的、可靠持久化的市场事实。

---

# 6. Data Collector 的核心能力

## 6.1 CTP 连接能力

Data Collector 负责 CTP 行情连接的生命周期。

能力包括：

- 连接配置的行情 Front；
- 完成必要的 Session / Login 流程；
- 维护连接状态；
- 在连接中断时具备必要的重连或恢复能力；
- 能够明确暴露当前采集是否健康。

具体的：

- 状态机；
- retry 策略；
- callback 组织；
- 连接对象设计；

不在本文档中规定，应基于 CTP SDK 和现有代码决定。

---

## 6.2 Instrument Subscription 能力

Data Collector 负责行情订阅。

它需要能够：

- 接收或解析当前需要采集的 instrument universe；
- 向 CTP 订阅目标期货和期权合约；
- 知道理论上哪些 instrument 应该产生行情；
- 区分“没有行情”和“订阅失败”。

未来 instrument universe 的生成方式可能发生变化，因此：

> Collector 不应被不必要地绑定到一个永远硬编码的合约列表。

具体 instrument discovery 如何实现，留给后续设计。

---

## 6.3 Market Data Reception 能力

Data Collector 负责接收 CTP 行情更新，并转换成系统内部可维护的市场状态。

需要保留后续分析可能需要的重要 market facts。

时间信息至少应能区分：

- CTP / 交易所提供的行情时间（如有）；
- 本地实际接收时间（如有必要）。

第一阶段持久化的数据应能够支持后续：

- 分钟级监控；
- 当日行情回看；
- 基差计算；
- IV 计算；
- 期权链分析；
- 基础研究。

---

## 6.4 In-Memory Market State 能力

CTP callback 不要求一条对应一条 durable record。

Collector 可以维护每个 instrument 的最新内存状态：

```text
CTP update
    ↓
Instrument Latest State
    ↓
Snapshot Materialization
```

内存状态的职责是：

> 承接高频外部更新，并为 durable snapshot 生成提供当前市场状态。

它不是长期 Source of Truth。

---

## 6.5 Snapshot Materialization 能力

Data Collector 负责划分：

> volatile market update

与：

> durable market snapshot

之间的边界。

架构意图是：

> 不要求盲目地将每一个 CTP callback 原样写成永久记录，而是先形成系统需要保存的 snapshot，再持久化。

具体：

- 多久生成一次 snapshot；
- 每个 instrument 是否独立采样；
- 是否按统一时钟物化；
- 如何处理 callback 缺失；
- 如何处理重复 snapshot；

都属于实现设计问题。

但有一个边界需要保持：

> 持久化的是市场事实 snapshot，而不是为了某个页面预先加工好的 UI 数据。

---

## 6.6 Durable Persistence 能力

Data Collector 负责保存它生成的 snapshot。

第一阶段采用：

> **一个交易日对应一个 SQLite 数据集。**

Data Collector 是这份 SQLite 数据的 owner 和 writer。

当 Collector 停止运行以后：

- 数据文件仍然存在；
- 文件可以被独立读取；
- Python 不需要参与写入过程；
- Browser 不需要参与写入过程。

---

## 6.7 Trading Day Lifecycle 能力

第一阶段将交易日作为最基本的数据分区和生命周期边界：

```text
Trading Day A → SQLite A
Trading Day B → SQLite B
Trading Day C → SQLite C
```

Collector 需要保证：

- 不同交易日的数据不会互相覆盖；
- 当前交易日的数据在合理情况下可以继续写入；
- 历史每日文件保持独立可读；
- 每个数据集能够明确识别自己的 trading day。

具体文件名不是架构约束。

---

## 6.8 Collector Observability 能力

Data Collector 必须具有最基本的可观测性。

至少应该能够回答：

- 当前是否连接 CTP？
- 当前订阅了哪些 instrument？
- 哪些 instrument 正在收到行情？
- 最近一条行情是什么时间收到的？
- SQLite 是否正在持续写入？
- 今天是否发生过断线？
- 是否发生过重连？
- Collector 是否中途重启过？
- 是否出现持久化失败？

第一阶段不需要建设完整 Monitoring Platform。

只要：

- 日志；
- 简单状态；
- 诊断输出；

能够明确回答这些问题即可。

---

# 7. Data Collector 明确不负责什么

为了避免 Data Collector 演变成整个系统的“大后端”，第一阶段必须保持边界克制。

Data Collector 不负责：

- Browser 页面；
- 前端状态管理；
- 给浏览器提供 HTTP API；
- WebSocket；
- 服务端向浏览器推送；
- Monitor Rule；
- Alert；
- 交易建议；
- 自动下单；
- Portfolio；
- P&L；
- 回测；
- 长周期历史研究；
- 现货指数行情；
- 新闻和宏观数据；
- 用户认证；
- 云端部署能力。

Data Collector 也不应该默认负责复杂 derived analytics。

例如：

- Basis；
- Annualized Basis；
- ATM；
- IV；
- Option Chain Summary；
- Term Structure；
- Strategy Metrics；
- Monitor Signal。

这些原则上属于下游派生状态。

只有未来出现明确理由时，才考虑将某些计算向上游移动。

---

# 8. 数据所有权边界

系统需要明确区分两种数据：

## 8.1 Durable Market Facts

Data Collector 负责。

例如：

- instrument identity；
- market timestamp；
- receive timestamp；
- last price；
- bid / ask；
- volume；
- open interest；
- 未来计算需要但无法事后恢复的 source fields。

这些属于：

> durable source facts

---

## 8.2 Derived State / View

后续模块负责。

例如：

- 基差；
- 年化基差；
- ATM；
- IV；
- skew；
- term structure；
- futures curve；
- intraday summary；
- monitor indicator。

架构原则是：

> Collector 保存“事实”；下游生成“解释”和“视图”。

因此数据库不应为了某一个前端页面而设计。

需要优先保存的是：

> 一旦丢失以后无法低成本重新构建的数据。

---

# 9. Storage Ownership

第一阶段的数据所有权采用非常明确的不对称模型：

```text
C++ Data Collector
        │
        │ read / write
        ▼
    Daily SQLite
        ▲
        │ read-only
        │
 Future Python Query Layer
```

核心规则：

> C++ Data Collector 是 Daily SQLite 的 owner 和唯一 writer。

Python 后续可以读取，但第一阶段不参与修改这些 collector-owned datasets。

这个边界的价值是：

- 避免多 writer；
- 避免采集依赖 Python；
- 避免查询功能影响采集；
- 避免 Browser 故障扩散到 ingestion path。

---

# 10. Independence Requirement

Data Collector 必须能够在下面这种运行状态下持续正常工作：

```text
C++ Data Collector : Running
Python Backend      : Stopped
Browser             : Closed
```

这时：

> 行情依然必须被正常接收和持久化。

这是第一阶段最重要的架构不变量之一。

同样：

- Python 可以重启；
- Browser 可以刷新；
- Browser 可以完全关闭；

这些行为都不应该影响 Collector。

---

# 11. 本地部署边界

第一阶段首先服务于本地运行。

高层产品形态为：

```text
Local Machine
    │
    ├── Data Collector Runtime
    │
    └── Persistent Data Directory
            │
            ├── TradingDay_A.sqlite
            ├── TradingDay_B.sqlite
            └── TradingDay_C.sqlite
```

Collector 可以被 Docker 化。

但架构关注点不是 Docker 本身，而是：

> Runtime 和 Durable Data 必须是两个不同生命周期。

也就是说：

- Collector container 可以重启；
- Collector image 可以更新；
- Runtime 可以重新创建；

但历史数据不能因此消失。

CVM / 云部署暂时不是第一阶段架构设计驱动力。

---

# 12. 第一阶段完成边界

第一阶段真正需要完成的是：

```text
CTP
 ↓
C++ Data Collector
 ↓
Snapshot
 ↓
Daily SQLite
```

能够端到端证明：

- 可以建立 CTP 行情连接；
- 可以订阅目标 instrument；
- 可以收到真实市场行情；
- 行情可以形成系统自己的市场状态；
- 市场状态可以物化为 snapshot；
- snapshot 可以写入正确 trading day 的 SQLite；
- Collector 停止后数据仍然存在；
- SQLite 可以被独立读取；
- Python 和 Browser 在采集过程中都不是必要组件。

完成这一点以后：

> Data Collector 就成为 Derivatives Monitor 第一个完整、可独立使用的 subsystem。

---

# 13. 第二阶段的架构衔接

第二阶段增加的是：

> Read Path

而不是修改第一阶段 Write Path。

系统扩展为：

```text
                       CTP
                        │
                        ▼
                 Data Collector
                        │
                        ▼
                  Daily SQLite
                        │
                        │ read-only
                        ▼
                Python Query Layer
                        │
                        ▼
                     HTTP
                        │
                        ▼
               Browser / JavaScript
```

核心不变量是：

> Phase 2 消费 Phase 1 的 durable output，但不能成为 Phase 1 的运行依赖。

---

# 14. Python Query Layer 的能力边界

第二阶段中的 Python 应主要承担：

> Storage-facing Read Adapter

它预计负责：

- 找到正确的 Daily SQLite；
- 读取 snapshot；
- 根据请求读取一个或多个 trading day；
- 将多个文件的数据进行必要合并；
- 暴露对 Browser 更友好的查询契约；
- 对 Browser 隐藏底层 storage 细节。

Browser 不应该知道：

- 数据在哪个 SQLite 文件里；
- 查询跨了几个文件；
- 未来 SQLite 是否被替换；
- 历史数据以后是否迁移到 Parquet / PostgreSQL / analytical store。

因此 Python Query Layer 是：

> Browser 与 Physical Storage 之间的 read boundary。

---

# 15. Browser 的能力边界

第二阶段 Browser 初始采用：

> HTTP Polling

高层流程：

```text
Browser
   │
   │ periodic request
   ▼
Python Query Layer
   │
   ▼
Durable Market Facts
   │
   ▼
JavaScript Derived State
```

浏览器可以负责：

- Futures Basis；
- Annualized Basis；
- Option Chain View；
- ATM；
- IV；
- Futures Curve；
- Term Structure；
- Intraday Summary；
- 页面级 Monitor 指标。

第一轮不要求 WebSocket。

只有在产品需求真正需要 server push 时再引入。

---

# 16. 多日数据读取的演进方向

第一阶段：

> 一天一个 SQLite。

第二阶段 Python 可以根据日期范围读取多个 SQLite。

对 Browser 暴露的应该是类似：

```text
start_date
end_date
instrument
...
```

这样的逻辑查询能力。

Browser 不需要理解：

```text
2026-09-01.sqlite
2026-09-02.sqlite
2026-09-03.sqlite
```

未来如果出现大量历史研究需求，可以再增加：

- historical compaction；
- Parquet；
- analytical database；
- long-term warehouse。

但这些不应该提前反向污染 Phase 1 Collector。

---

# 17. 长期演进方向

整个系统后续可以沿下面的方向自然扩展：

```text
External Market Sources
        ↓
Collectors
        ↓
Durable Market Facts
        ↓
Query / Analytics
        ↓
Browser Monitor
        ↓
Rules / Alerts
        ↓
Decision Support
```

未来可能增加：

- Spot Index Collector；
- Historical Compaction；
- Server-side Analytics；
- Rule Engine；
- Alert Engine；
- CVM Deployment；
- Mobile Notification；
- Market State Detection；
- Decision Support。

这些能力应该围绕：

> Durable Market Fact Boundary

继续向外扩展，而不是不断塞回 CTP Data Collector。

---

# 18. Codex 设计时必须保持的架构不变量

Codex 基于现有仓库进行设计时，应保持：

1. **第一阶段最小闭环是 CTP → C++ Data Collector → Daily Durable Dataset。**
2. **Python 不属于采集依赖链。**
3. **Browser 不属于采集依赖链。**
4. **C++ 是 collector-owned SQLite 的 writer。**
5. **Python 对 collector SQLite 只读。**
6. **Data Collector 保存市场事实，而不是为 UI 预计算全部分析结果。**
7. **CTP update 可以先更新内存状态，再生成 durable snapshot。**
8. **Trading Day 是第一阶段最基本的数据生命周期边界。**
9. **Data Collector 必须可以独立运行、独立测试、独立验收。**
10. **第二阶段应消费第一阶段产物，而不是改变第一阶段 ingestion path。**
11. **不要因为假设中的未来规模提前引入复杂基础设施。**
12. **具体设计应优先适应现有仓库，而不是按照本文档重新发明一套平行架构。**

---

# 19. 给 Codex 的设计指导

本文档是：

> Architecture Constraint

不是 Low-level Implementation Spec。

Codex 在提出具体方案之前，应先：

1. 阅读当前仓库目录；
2. 找到当前 CTP Demo / SDK 衍生代码；
3. 理解已有 runtime boundary；
4. 理解已有 configuration 方式；
5. 理解已有测试方式；
6. 理解 Docker / deployment 的现状；
7. 理解现有代码已经做了哪些 CTP lifecycle 工作。

然后再设计：

> 满足上述架构边界的最小实现。

优先选择：

> 在当前代码基础上演进。

而不是：

> 为了“架构漂亮”先引入大量新抽象。

对于本文档没有规定的细节，设计优先级应为：

1. CTP SDK 的真实约束；
2. 当前仓库结构；
3. 当前项目约定；
4. 最小、可靠、容易验证的方案。

第一阶段的目标不是提前完成最终版 Derivatives Monitor。

目标只有一个：

> **把 Data Collector 做成一个小而可靠、拥有明确数据所有权、能够稳定产生 durable market facts 的第一个完整子系统。**
