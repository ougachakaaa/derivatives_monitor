# 运行、维护与恢复

本文件只提供运行、维护、故障处理与恢复规程，不定义系统结构或业务行为。当前结构见 [Architecture](architecture.md)，精确部署和读写边界见 [Contracts](contracts/)。

实际命令以 [Collector 手册](../collector/README.md)、[Query 手册](../query/README.md)和[Dashboard 手册](../dashboard/README.md)为准。默认看板 `http://localhost:8101`，API `http://localhost:8000/docs`。示例日期必须换成已有源 TradingDay；启动成功不代表收到行情。

## 部署与日常检查

| 方式 | 前提 | 管理入口 |
|---|---|---|
| 原生 | Linux/WSL x86-64、Release 构建、query Python 3.12/.venv、Node 22.12+、前端依赖、用户 systemd、有效配置 | `./collector/scripts/native.sh up`；`status` / `logs` / `update` / `stop` |
| Docker | Docker Engine + Compose v2、Git/Bash、有效配置或首次交互输入 | `./scripts/deploy.sh up`；`status` / `logs` / `stop` / `verify YYYYMMDD` |

同一数据目录只能有一个 Collector。离线测试无需启动真实服务；文档整理无需执行 up/update/stop。宿主安装步骤见各模块 README，不依赖历史报告中 `/tmp` 下的工具路径。

日常分别检查主循环心跳、连接/登录、逐合约订阅、最后接收/提交、源交易日和清单/日历版本。市场 CLOSED/BREAK、不活跃合约无推送、订阅失败不是同一状态。查看 `snapshot_commit` 与两次只读行数/最近时间确认推进；不要把 accepted、written 和跨 run 日行数相互比较为同一指标。

## 更新参考与软件

- 原生 `update` 获取公开清单；来源失败保留旧清单并明确 stale。清单变化可能正常重启 Collector；不把维护命令当成只读检查。Docker/手工入口不自动提供相同的 universe 定时器。
- 日历当前覆盖 2026，跨年前按[年历维护规则](../query/calendars/README.md)审核新版本。JSON 原子发布后下次查询生效；profile 代码修改需重启 Query。UNKNOWN 不能用工作日推断兜底。
- 软件更新前保留版本、日志和数据。构建与配置预检成功后部署，使用正常 SIGTERM 尾部提交。已有采样配置不自动改写；显式 `1000` 仍为一秒，需要改成 `15000` 时由操作人明确配置。
- 不删除运行依赖的 `collector/build/` 工具、不清理配置/data/flow；Raw、universe 原响应与 generations 暂不自动轮转，观察剩余磁盘并制定保留策略。磁盘故障时优先保留证据，不能删库换取“健康”。

## 故障处理

API 失败先检查 `/healthz` 与数据读取错误；Collector 可能仍正常采集。心跳缺失/过期显示 unknown/stale，不能用旧 JSON 判定健康。CTP 断线后的重连由 SDK 处理，应用重新登录订阅；不可声称补回断线期间行情。

持久化错误非零退出；检查空间、权限、writer 冲突及日志。保留未提交 WAL，避免删除 sidecar。崩溃后由正常 Collector/SQLite 恢复，再正常停止验证；不直接改库或伪造 run 结束状态。

Collector 活跃但所查历史日已关闭且缺 sidecar 时，当前 Query 按契约返回 503。需要读取该日时安排正常停止 Collector 并保留 Query。不得为了绕过错误改成 RW 或直接设置 immutable。若此限制阻断 MVP 的日常回看，记录为未满足 G4，而非隐藏错误。

## 备份与隔离恢复演练

推荐 MVP 使用计划停机备份，步骤可审查且不引入第二个 Raw writer：

1. 记录版本、数据目录、实际日文件、采样参数、run ID 和清单/Calendar 版本；选定不覆盖已有文件的备份目的目录。
2. 正常停止 Collector；关闭读连接。确认服务已终止且目录 writer 锁已释放。若是异常退出先完成正常恢复，不删除 WAL；存在非空 WAL 时不能只复制主文件。
3. 对已正常关闭、无非空 WAL 的日库逐个执行只读 `integrity_check` 和 `foreign_key_check`，记录 dataset 身份、行数、run 来源、最大 id、文件 SHA-256。复制日库及需要重放的不可变 Universe generation；保存对应 Calendar/算法/参数版本。配置备份单独以受限权限保存，不进 Git。
4. 把备份复制到全新的隔离恢复目录。比较 SHA-256 和只读完整性、dataset、行数/最大 id；不要覆盖实际 `collector/data/`。按[Query CLI](../query/README.md)使用 `--data-dir` 指向恢复目录，读取样本分钟并比较固定 revision 输出；参考导入/API 完成后，对同一 frame、ReferenceBundle 和算法版本增加指标重放对账。
5. 记录备份/恢复耗时、哈希、检查结果和输出路径。恢复原 Collector 后确认同日追加和新心跳，已提交记录未减少；演练日志与真实数据证据单独保存。

在线备份需 SQLite backup API 或其他已验证的一致性方案，不允许直接复制活跃主文件。当前没有自动在线备份工具；不要把上述人工规程记成已完成演练。运行时 SQLite 的只读锁规则仍适用。
