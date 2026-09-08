# Data Collector 第一阶段验收记录

> 历史验收快照：仅证明文中日期/版本/环境下的观察。旧端口、临时路径、待验状态和操作命令可能已过时；当前设计见[文档入口](../../README.md)，当前门槛见[验收矩阵](../../acceptance.md)，运行见[操作说明](../../operations.md)。原始日志缺失时仅作为历史摘要。


验收日期：2026-09-06（Asia/Shanghai，周日）。约束：[设计约束](../../contracts/collector.md)。

## 结果边界

独立 C++ Collector 与离线端到端闭环已实现并验证；**真实 CTP 连接、订阅及持续行情入库尚未在本次环境验收通过**。不可用网络是明确的外部验证限制，不以测试合成行情代替实盘结果。

## 环境与自动化验证

- Linux x86-64；G++ 13.3；官方 CTP `v6.7.13_20260225 14:16:30.12079`；系统 SQLite 3.45.1。
- SQLite 开发包没有系统安装权限；使用 `apt-get download libsqlite3-dev` 并 `dpkg-deb -x` 到 `/tmp/dm-sqlite-dev/root`，CMake 指定该 include 目录并链接系统 `/usr/lib/x86_64-linux-gnu/libsqlite3.so.0`。依赖及测试数据未加入仓库。
- Debug/Release 的 config、state、storage、runtime、process CTest；生产关闭测试构建；原 demo 构建回归。最终结果见 T5 完成记录。

| 验证 | 证据/通过条件 |
|---|---|
| INI/CLI 与复用 | 路径、合约去重、空列表/过长字段拒绝；原 demo 保持可构建 |
| 状态与采样 | 源结构复制、46 字段映射、窗口合并、空窗口、10000 次并发更新 |
| 交易日 | 两日乱序隔离、非法日拒收、第三日容量保护；ActionDay 不影响分区 |
| SQLite | 两日文件、同日多 run 追加、批次去重、NULL、日身份/schema 校验、事务回滚、writer 锁 |
| 只读消费 | C++ `SQLITE_OPEN_READONLY` 连接看到后续提交、写入返回 SQLITE_READONLY、停机后 integrity_check |
| CTP 生命周期 | fake 调用真实 SPI，覆盖断线/重连、请求拒绝、登录错误、响应超时、订阅失败和无行情 |
| 进程闭环 | 真实 CLI + 测试 SDK 每 50ms 推送，100ms 采样，日切、重连、只读查询、SIGTERM 尾部提交、定时退出、同日重启 |
| 崩溃恢复 | SIGKILL 后已提交数据仍可读，restart 追加，历史异常 run 保持 stopped_us=NULL |
| 故障处理 | 注入 SQL trigger 中途失败/写锁冲突/目标文件不可打开，验证不部分提交、非零错误及 SDK 释放 |

自动化测试使用 C++/CMake；Collector 子进程不启动 Python 或 Browser。另以 Python 标准库 `mode=ro` 对独立运行的合成行情 Collector 做消费验证：同一读连接先后看到 2 → 6 条已提交记录，DELETE 返回 `attempt to write a readonly database`。Python 只在采集已经运行后作为读者启动。`libfake_md.so` 只在 CTest 子进程中预加载，日志版本为 `TEST DOUBLE - synthetic market data`，不会连接网络。最终实现也将测试来源明确写入 `runs.source`，与官方 SDK 来源区分。它证明内部闭环与生命周期，不证明厂商前置可用或真实行情质量。

## 真实前置探测

2026-09-06 19:32 CST：使用仓库配置中的 `tcp://61.186.254.135:42213`、BrokerID 9080、空行情账号，候选订阅 `IF2609,IO2609-C-4000`，运行官方 SDK，启动连接/登录窗口 20 秒。因未连接，这些合约本次没有获得订阅确认，不能作为上市/权限验证。

脱敏日志摘要：

```text
event=start run_id=e4aad767d7532354f1cdce565c70e14a
api_version="v6.7.13_20260225 14:16:30.12079" sqlite_version=3.45.1
front=tcp://61.186.254.135:42213
event=health connected=0 logged_in=0 connections=0 subscribed=0 accepted=0 written=0
event=collector_failed written=0
event=fatal message="startup connection/login timeout"
exit_code=1
```

数据目录只有 `.collector.lock`，没有伪造空日数据库。本机日志位于 `/tmp/dm-collector-live/run.log`，临时文件不是长期证据，以上摘要随文档版本化。

随后对仓库记录的六个节点 `61.186.254.135`、`101.230.125.167`、`101.230.125.168`、`140.207.150.241`、`113.204.105.118`、`202.130.235.165` 的 42213 端口各做一次三秒有界 TCP 连接尝试，全部返回 `ConnectionRefusedError: [Errno 111] Connection refused`。只能确认本环境当时无法建立连接；无法据此区分券商休市维护、访问控制或网络设备拒绝。

## 交易时段补验

前置恢复后，更新 `collector/config.ini` 为已确认有效的前置/账号与在市合约，再从仓库根目录运行：

```bash
collector/build/Release/bin/data_collector --config collector/config.ini --check-config
collector/build/Release/bin/data_collector --config collector/config.ini --run-seconds 120 > collector/live-acceptance.log 2>&1
```

必须逐项获得：

1. `front_connected` 与 `login_response logged_in=1`。
2. 每个目标合约 `subscription_response error_id=0`，并在行情活跃时 `session_received` 持续增加。
3. 多次 `snapshot_commit`，`written` 和 `last_commit_us` 增长。
4. 日文件名等于其 `dataset.trading_day`，`SELECT DISTINCT TradingDay FROM snapshots` 仅有该交易日；比较源 `UpdateTime/UpdateMillisec`、接收和物化时间。
5. Collector 运行时以 SQLite CLI/Python `mode=ro` 看到新数据；Collector 不需要启动这些读程序。
6. SIGTERM/定时退出后 `PRAGMA integrity_check` 为 `ok`；同日重启得到新 run，旧行仍在。

完整操作与只读 SQL 见 [Collector README](../../../collector/README.md)。跨日及强制终止恢复已有离线覆盖；真实日切/长时间网络稳定性仍需后续现场运行记录。
