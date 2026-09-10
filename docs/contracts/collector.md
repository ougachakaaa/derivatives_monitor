# Collector 长期契约


本契约适用于 MVP 及后续下游扩展。整体定位见[系统架构](../architecture.md)，可执行用法见[Collector 手册](../../collector/README.md)。

## 边界与职责

- 唯一闭环：CTP → C++ Collector → 每交易日 SQLite。Python、Browser、HTTP、策略、交易、现货指数、IV/基差计算均不进入采集链路。
- Collector 是数据目录的唯一 writer；下游以 SQLite `mode=ro` 读取市场事实。运行目录与持久数据目录可分别配置，重启不得截断旧数据。
- 演进现有 C++17/Linux SDK 接入：`collector/` 自有 INI、固定字段校验、日志、SDK 构建规则与最小第三方 SDK；保留实验 demo 的 CSV 探测用途，实验代码可依赖正式模块。不引入服务框架、消息队列或 Python runtime。
- 合约 universe 来自配置、`InstrumentsFile` 或重复的 `--instrument` 参数，精确代码、去重、非空。C++ 不做合约发现；独立公开清单程序负责 CFFEX 与 SHFE AU/AG 期货发现和更新，原生管理器在清单变化时正常重启 Collector。

## 行情接入与可选账号字段

正式 Collector 仅使用 MdApi；交易接口能力边界见 [MVP](../mvp.md#行情接入能力边界)。`UserID` 和 `Password` 为可选行情接入字段，允许缺省或空值，不将其非空作为行情配置有效的前提。已有值按原 MdApi 请求流程处理，不删除字段、不改写配置，不移除 `ReqUserLogin` 或现有连接/登录/订阅失败诊断。已填写值仍遵守 SDK 字段长度等安全约束。空值被本地接受不证明任意前置均允许匿名接入，真实接入结果由 MdApi 响应表达。

## 数据与采样不变量

- callback 立即复制 SDK 结构和本地 UTC epoch 微秒接收时间，不持有厂商指针，不做 SQLite I/O。主线程定期物化、写事务；共享状态只在短临界区复制/更新。
- 默认每 15000ms 采样一次每 `(TradingDay, InstrumentID)` 最新的未物化更新，仍可通过 `SnapshotIntervalMs` 配置 1–60000ms；同窗口多次更新合并，无新 callback 不重复制造新鲜行情。间隔不改变 callback 接收频率；沿用单调时钟调度，不对齐自然时钟，正常停机提前提交尾部。保留源时间、接收时间、物化时间及进程内序号；不承诺逐 callback 无损或断线补采。
- 原始有效字段全部保存（五档、成交量额、持仓、结算、涨跌停等），不存 SDK padding/reserve 字节。CTP 无效极大浮点值和非有限数写 NULL；源字符串保持原值。不由合约代码猜测交易所或合约元数据。
- **分区仅取每条行情的合法 `TradingDay`**；不使用本地日期、`ActionDay` 或登录日替代。非法/空交易日拒收并计数。登录日仅用于诊断。
- 状态按 `(TradingDay, InstrumentID)` 隔离；保留相邻两天的状态，乱序旧日不覆盖新日；第三个交易日到来前未物化状态不得静默丢弃，超容量终止并报错。很旧数据拒收并计数。
- 一日一个 `YYYYMMDD.sqlite`，元数据明确 schema 版本和交易日；写入约束阻止混日。允许同日重启追加；每次进程运行有独立 run ID，事务与唯一键防止同次物化重复写入。

## 生命周期与失败语义

- SDK 头文件说明断线自动重连；应用在每次连接后登录，登录成功后重新订阅。请求返回 0 只表示本地受理，订阅响应单独跟踪，区分 pending/成功/失败/已订阅但无行情。
- 主线程负责有间隔的登录重试、订阅批次和超时检测；callback 不 sleep。重新连接后清除本次 session 的健康状态，保留待持久化事实。
- 每数据目录用进程锁排除第二个 Collector。SQLite 单连接单 writer，WAL + `synchronous=FULL`，有界 busy timeout，逐日事务；不要求跨日原子提交。
- 写入失败必须明确日志且非零退出，不能继续报告健康。成功 commit 后才累计 durable 行数。SIGINT/SIGTERM 先释放 SDK（SPI 仍存活），再物化尾部状态并关闭数据库。强制杀进程可能丢最后尚未提交窗口。
- 日志包含 run ID、连接/登录/断线/重连、逐合约订阅及接收状态、最近接收/成功写入时间、拒收计数与持久化错误；无凭据输出。

## 验收约束

- 核心状态、日切、事务、失败及 SDK 生命周期可离线通过 C++/CTest 验证；模拟输入必须明确标识，不能当作真实行情证据。
- 实盘连接、真实订阅和真实持续行情分别记录证据。前置不可达或非交易时段只能报告已验证的部分，不以空库、登录成功或模拟行情冒充实盘闭环。
- 下游实时读使用短事务，活跃 WAL 数据不得仅复制 `.sqlite` 主文件或设 `immutable=1`。历史文件在正常关闭且无读事务占用时可独立拷贝；否则使用 SQLite backup。

技术依据：[本仓库 SDK](../../collector/third_party/ctp/v6.7.13_20260225/linux64/mdapi/ThostFtdcMdApi.h)、[SQLite WAL](https://www.sqlite.org/wal.html)、[同步级别](https://www.sqlite.org/pragma.html#pragma_synchronous)、[只读 URI](https://www.sqlite.org/uri.html)。
