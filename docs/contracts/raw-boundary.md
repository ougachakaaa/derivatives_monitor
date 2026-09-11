<a id="raw-shared-boundary"></a>

# Raw Market Facts 共享边界

本契约只定义 Collector producer 与只读消费者共同遵守的 Raw 所有权、发布、锁、WAL 和运行诊断协议。Collector 如何接收、采样和提交见 [Collector Contract](collector.md)；Query 内部查询及公共 HTTP 见 [Read Path](read-path.md)；挂载、目录生命周期和服务管理见 [Deployment](deployment.md)。

## 所有权与已发布事实

- Collector 是 Raw 数据目录和日库的唯一 writer；Query、Dashboard、Analytics 及后续消费者不得写 Raw、修改 schema 或建立第二份行情事实。下游只能解释实际已提交的采样，不得把未保存的 callback、缺失行情或推测值包装成 Raw。
- Raw schema v1 按源行情中合法的 `TradingDay` 发布为一日一个 `YYYYMMDD.sqlite`，保存 `received_us`、`snapshot_us`、`run_id`、`sequence`、`id` 和 CTP 原字段；元数据明确 schema 版本和交易日，写入约束阻止混日。同日重启可以追加，每次运行以独立 run ID 标识，事务与唯一键阻止同次物化重复写入。具体接收、字段归一化、分区、采样窗口及跨日内存状态仍由 [Collector Contract](collector.md#数据与采样不变量)定义。
- 数据目录、flow、配置和 application state 是不同 owner 的资源。系统挂载与保留规则见 [Deployment Contract](deployment.md#数据与隔离)；移除服务、镜像、构建或项目文件不能作为删除 Raw 的手段。

## Writer 协调与持久性

- 每个 Raw 数据目录使用进程锁排除第二个 Collector writer。SQLite 使用单连接单 writer、WAL、`synchronous=FULL`、有界 busy timeout 和逐日事务；不承诺跨交易日原子提交。
- 只有成功 commit 后的数据和 durable 行数才属于已发布事实。写入失败、正常停止尾部提交和强制终止窗口的 producer 行为见 [Collector Contract](collector.md#生命周期与失败语义)。目录或端口预检不能替代 writer 锁。

## 只读消费与 WAL

- 消费者以 SQLite URI `mode=ro`、`query_only=ON` 和短事务读取同一 Raw，不创建空库、不迁移 schema、不删除或修改 WAL/SHM。
- 活跃日库从只读挂载读取现存 WAL/SHM；不得只复制 `.sqlite` 主文件，也不得使用 `immutable=1`。离线且没有非空 WAL 时，只能在取得 Collector 共享目录锁后使用 immutable，并在连接关闭前持锁；不得根据文件年龄猜测安全性。
- 历史文件在 Collector 正常关闭且没有读事务占用时可以独立复制；其他情况使用 SQLite backup。Collector 正在采集另一天而旧日缺少 sidecar 时，消费者必须明确报告可重试的不可读状态，提示正常停机后查询；不得绕过锁或修改持久目录。

## Collector 运行诊断协议

- Collector 持有 Raw writer 锁期间，每 2 秒原子替换数据目录中的 `.collector-status.json`。内容包括 `schema_version`、`run_id`、`updated_us`、`process_state`、连接/登录状态、订阅状态、accepted/written 计数以及最后接收/成功提交时间；启动、正常停止和异常退出均尽可能发布状态，不输出凭据。
- 心跳由 Collector 主循环产生，独立于行情 callback。超过 10 秒、时钟明显倒退、内容损坏或缺失时，消费者不得判定进程存活；SIGKILL 后遗留文件也不能继续证明健康。
- 进程存活、CTP 已连接、订阅状态、行情最近更新和成功写入是不同证据。休市无新行情不等于进程停止，只有采集连接/登录或已知错误才影响相应指标；状态输出失败由 Collector 记录但不停止采集，消费者故障也不进入采集控制路径。诊断 JSON 不是新的行情 Source of Truth。

## 失败与证据边界

缺失合法日库与日库不可读、不兼容、锁/WAL 条件不成立或查询超时必须区分；公共 HTTP 如何映射为 404/503 由 [Read Path Contract](read-path.md)定义。空目录、空数据、登录成功或模拟输入不能单独证明真实行情闭环。工程和现场证据的归属见 [Acceptance](../acceptance.md)与 [Harness](../../harness/README.md)。

技术依据：[SQLite WAL](https://www.sqlite.org/wal.html)、[同步级别](https://www.sqlite.org/pragma.html#pragma_synchronous)、[只读 URI](https://www.sqlite.org/uri.html)。
