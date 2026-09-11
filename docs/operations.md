<a id="repository-operations"></a>

# 运行、维护与恢复

本文件只提供运行、维护、故障处理与恢复规程，不定义系统结构或业务行为。当前结构见 [Architecture](../ARCHITECTURE.md)，精确部署和读写边界见 [Contracts](README.md)。

实际命令以 [Collector 手册](../collector/README.md)、[Query 手册](../query/README.md)和[Dashboard 手册](../dashboard/README.md)为准。默认看板 `http://localhost:8101`，API `http://localhost:8000/docs`。示例日期必须换成已有源 TradingDay；启动成功不代表收到行情。

## 选择运行方式与日常检查

| 方式 | 前提 | 管理入口 |
|---|---|---|
| 前台开发 | Linux/WSL x86-64、Release 构建、query Python 3.12/.venv、Linux Node 22.12+、前端依赖、已有有效配置 | `./dev doctor`；`./dev up` 或 `./dev up <component>`；当前终端 Ctrl-C 结束 |
| Native systemd | 同上并需要用户 systemd | `./collector/scripts/native.sh up`；`status` / `logs` / `update` / `stop` |
| Docker Compose | Docker Engine + Compose v2、Git/Bash、有效配置或首次交互输入 | `./scripts/deploy.sh up`；`status` / `logs` / `stop` / `verify YYYYMMDD` |

同一数据目录只能有一个 Collector。离线测试无需启动真实服务；文档整理无需执行 up/update/stop。宿主安装步骤见各模块 README，不依赖历史报告中 `/tmp` 下的工具路径。

原生 `up` 包含订阅文件配置准备、服务 enable/restart 和 timer 启动，具体备份及配置替换步骤见 [Collector 手册](../collector/README.md#原生-wsl-管理)。它与 Docker `up` 复用已有配置的行为不同；原生 `stop` 不取消服务 enable，长期禁用仍按该手册操作。本地前台入口的实现与验证状态见 [Acceptance](acceptance.md#本地开发入口交付状态)。

日常分别检查主循环心跳、连接/登录、逐合约订阅、最后接收/提交、源交易日和清单/日历版本。市场 CLOSED/BREAK、不活跃合约无推送、订阅失败不是同一状态。查看 `snapshot_commit` 与两次只读行数/最近时间确认推进；不要把 accepted、written 和跨 run 日行数相互比较为同一指标。

## 前台开发会话

先按三个组件 README 完成 [Collector 构建与配置](../collector/README.md#构建与测试)、[Query 安装](../query/README.md#安装启动与测试)及 [Dashboard 依赖安装](../dashboard/README.md#本地开发)。Runner 只使用已有产物和配置；不会创建配置、刷新 Universe、安装、构建或调用持久部署管理器。

从仓库根目录先检查全部运行条件，再启动本次终端拥有的三个组件：

```bash
./dev doctor --config collector/config.ini
./dev up --config collector/config.ini --query-port 8000 --dashboard-port 8101
```

也可只检查或运行一个组件；单组件不要求另外两个组件的依赖存在：

```bash
./dev doctor collector --config collector/config.ini
./dev up collector --config collector/config.ini

./dev doctor query --data-dir collector/data --query-port 8000
./dev up query --data-dir collector/data --query-port 8000

QUERY_URL=http://127.0.0.1:8000 ./dev doctor dashboard --dashboard-port 8101
QUERY_URL=http://127.0.0.1:8000 ./dev up dashboard --dashboard-port 8101
```

启动选项放在 `up` 或所选组件之后；旧顶层 `./dev collector/query/dashboard` 已退役。相对路径、环境变量优先级和联合派生规则以 [Deployment Contract](contracts/deployment.md#developer-runner-的生命周期边界) 为准。`up` 从 Collector 配置取得 Query 的 Raw 目录，并从 Query 端口生成 Dashboard 代理；不要为联合会话设置冲突的 `DATA_DIR` 或 `QUERY_URL`。诊断只检查本地运行条件，不证明 CTP 登录、行情推进、Raw 可读或 Skew 可计算。

保持 `./dev` 在前台；Ctrl-C、SIGTERM 或终端 SIGHUP 会触发本次自有进程的正常收尾。Query/Dashboard 退出或一次性 HTTP 检查失败不会停止 Collector；已有端口或 writer 冲突应通过其原管理入口处理。需要跨终端自动启动、重启、状态和日志管理时，改用上表的 native systemd 或 Docker Compose 入口，不要同时写同一 Raw 目录。

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
3. 对已正常关闭、无非空 WAL 的日库逐个执行只读 `integrity_check` 和 `foreign_key_check`，记录 dataset 身份、行数、run 来源、最大 id、文件 SHA-256。复制日库及重放所需的不可变 Universe generation、Calendar、已审核 ReferenceBundle 和来源原件，记录对应算法版本。配置备份单独以受限权限保存，不进 Git。
4. 把备份复制到全新的隔离恢复目录。比较 SHA-256 和只读完整性、dataset、行数/最大 id；不要覆盖实际 `collector/data/`。按[Query 手册](../query/README.md)使用 `--data-dir` 指向恢复目录，读取样本分钟并比较固定 revision 输出；通过现有离线参考包导入与 Skew API，对相同 Raw revision、ReferenceBundle 和算法版本执行指标重放对账，业务判定仍以 [Analytics / Skew Contract](contracts/analytics-skew.md)为准。若没有已审核的生产参考包，将指标重放记为未执行，不得用 TEST DOUBLE 代替 live recovery evidence。
5. 记录备份/恢复耗时、哈希、检查结果和输出路径。恢复原 Collector 后确认同日追加和新心跳，已提交记录未减少；演练日志与真实数据证据单独保存。

在线备份需 SQLite backup API 或其他已验证的一致性方案，不允许直接复制活跃主文件。当前没有自动在线备份工具；不要把上述人工规程记成已完成演练。运行时 SQLite 的只读锁规则仍适用。
