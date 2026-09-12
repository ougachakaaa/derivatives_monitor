<a id="collector-runtime-contract"></a>

# Collector 长期契约

本契约适用于 MVP 及后续下游扩展。整体定位见[系统架构](../ARCHITECTURE.md)，内部组件关系见[Collector Architecture](ARCHITECTURE.md)，共享 Raw 协议见 [Raw Boundary](../docs/contracts/raw-boundary.md)，可执行用法见[Collector 手册](README.md)。

## 边界与职责

- 唯一闭环：CTP → C++ Collector → 每交易日 SQLite。Python、Browser、HTTP、策略、交易、现货指数、IV/基差计算均不进入采集链路。
- Collector 按共享 [Raw Boundary](../docs/contracts/raw-boundary.md#所有权与已发布事实)写入市场事实；运行目录与持久数据目录可分别配置，重启不得截断旧数据。
- 演进现有 C++17/Linux SDK 接入：`collector/` 自有 INI、固定字段校验、日志、SDK 构建规则与最小第三方 SDK；保留实验 demo 的 CSV 探测用途，实验代码可依赖正式模块。不引入服务框架、消息队列或 Python runtime。
- C++ 接受配置接口提供的精确合约代码，不做合约发现；公开清单的生成和发布由独立的 [Universe Tool Contract](scripts/CONTRACT.md)定义。

## 行情接入与可选账号字段

正式 Collector 仅使用 MdApi；交易接口能力边界见 [MVP](../docs/mvp.md#行情接入能力边界)。`UserID` 和 `Password` 为可选行情接入字段，允许缺省或空值，不将其非空作为行情配置有效的前提。已有值按原 MdApi 请求流程处理，不删除字段、不改写配置，不移除 `ReqUserLogin` 或现有连接/登录/订阅失败诊断。已填写值仍遵守 SDK 字段长度等安全约束。空值被本地接受不证明任意前置均允许匿名接入，真实接入结果由 MdApi 响应表达。

## 配置接口

- `FrontMdAddr` 必填；`BrokerID` 与 `UserProductInfo` 按接入方要求填写。`UserID` / `Password` 遵守上节边界。
- 订阅代码可由 `Instruments`（冒号或逗号分隔）、可选 `InstrumentsFile`（逐行代码）或重复的 `--instrument CODE` 提供；命令行合约覆盖文件，文件覆盖 `Instruments`。结果必须为非空、精确、去重的代码集。
- `DataDirectory` 默认 `data`；`FlowPath` 默认 `flow` 且每个运行实例使用独立目录。配置中的相对路径以配置文件目录为基准。
- `SnapshotIntervalMs` 的默认值和范围由下节采样不变量定义；`StatusIntervalSeconds` 默认 `10`，`ConnectTimeoutSeconds` 默认 `20`，`RetryIntervalSeconds` 默认 `5`，`SubscriptionBatchSize` 默认 `100`。`RunSeconds` 默认 `0`，表示持续运行。
- CLI 为 `--config PATH`、可重复的 `--instrument CODE`、`--run-seconds N`、`--check-config` 和 `--help`。

## 数据与采样不变量

- callback 立即复制 SDK 结构和本地 UTC epoch 微秒接收时间，不持有厂商指针，不做 SQLite I/O。主线程定期物化、写事务；共享状态只在短临界区复制/更新。
- 默认每 15000ms 采样一次每 `(TradingDay, InstrumentID)` 最新的未物化更新，仍可通过 `SnapshotIntervalMs` 配置 1–60000ms；同窗口多次更新合并，无新 callback 不重复制造新鲜行情。间隔不改变 callback 接收频率；沿用单调时钟调度，不对齐自然时钟，正常停机提前提交尾部。保留源时间、接收时间、物化时间及进程内序号；不承诺逐 callback 无损或断线补采。
- 原始有效字段全部保存（五档、成交量额、持仓、结算、涨跌停等），不存 SDK padding/reserve 字节。CTP 无效极大浮点值和非有限数写 NULL；源字符串保持原值。不由合约代码猜测交易所或合约元数据。
- **分区仅取每条行情的合法 `TradingDay`**；不使用本地日期、`ActionDay` 或登录日替代。非法/空交易日拒收并计数。登录日仅用于诊断。
- 状态按 `(TradingDay, InstrumentID)` 隔离；保留相邻两天的状态，乱序旧日不覆盖新日；第三个交易日到来前未物化状态不得静默丢弃，超容量终止并报错。很旧数据拒收并计数。
- 采集产物按共享 [Raw Boundary 的已发布事实形状](../docs/contracts/raw-boundary.md#所有权与已发布事实)写入（日文件与 schema 元数据、同日追加、run ID、同次物化唯一性）；本契约不重复该形状。

<a id="collector-lifecycle-contract"></a>

## 生命周期与失败语义

- SDK 头文件说明断线自动重连；应用在每次连接后登录，登录成功后重新订阅。请求返回 0 只表示本地受理，订阅响应单独跟踪，区分 pending/成功/失败/已订阅但无行情。
- 主线程负责有间隔的登录重试、订阅批次和超时检测；callback 不 sleep。重新连接后清除本次 session 的健康状态，保留待持久化事实。
- Raw writer 锁、SQLite 持久性和逐日事务边界统一见 [Raw Boundary](../docs/contracts/raw-boundary.md#writer-协调与持久性)。
- 写入失败必须明确日志且非零退出，不能继续报告健康。成功 commit 后才累计 durable 行数。SIGINT/SIGTERM 先释放 SDK（SPI 仍存活），再物化尾部状态并关闭数据库。强制杀进程可能丢最后尚未提交窗口。
- 日志包含 run ID、连接/登录/断线/重连、逐合约订阅及接收状态、最近接收/成功写入时间、拒收计数与持久化错误；无凭据输出。

## 验收约束

- 核心状态、日切、事务、失败及 SDK 生命周期可离线通过 C++/CTest 验证；模拟输入必须明确标识，不能当作真实行情证据。
- 实盘连接、真实订阅和真实持续行情分别记录证据。前置不可达或非交易时段只能报告已验证的部分，不以空库、登录成功或模拟行情冒充实盘闭环。
- 下游只读、WAL、复制和 backup 约束统一见 [Raw Boundary](../docs/contracts/raw-boundary.md#只读消费与-wal)。

技术依据：[本仓库 SDK](third_party/ctp/v6.7.13_20260225/linux64/mdapi/ThostFtdcMdApi.h)。
