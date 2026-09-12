<a id="repository-developer-runner-contract"></a>

# Developer runner 长期契约

本契约定义仓库根 `./dev` 前台开发会话的命令面、输入解析、进程所有权与收尾边界，不改变两种持久部署方式。部署、挂载与端口见 [Deployment Contract](deployment.md)，实际操作见[运行与恢复](../operations.md#前台开发会话)，实现与验证状态见 [Acceptance](../acceptance.md)。

## 命令面与诊断

仓库根公共入口为 `./dev`：`doctor [collector|query|dashboard]` 检查全部或指定组件，`up collector`、`up query`、`up dashboard` 分别前台运行一个组件，`up`（不带组件）前台运行三个组件。顶层 `collector/query/dashboard` 不再作为启动命令或兼容别名；误用返回使用错误及新命令提示，不启动进程。`up all`、多组件列表不纳入本次接口。所有启动命令先执行相同范围的诊断；阻断错误不得启动对应进程，联合诊断有阻断错误时不得启动任何组件。Runner 不自动安装或构建依赖。

## 输入解析

| 有效输入 | 解析规则 |
|---|---|
| Collector `--config PATH` | 适用于 Collector、`up` 及对应诊断；默认 `collector/config.ini`，不读取配置路径环境变量 |
| Query `--data-dir PATH` / `DATA_DIR` | 仅单独 Query 接受；CLI → 环境 → `collector/data`。`up` 必须从所选 Collector 配置派生，不接受覆盖 |
| `--query-port N` / `QUERY_PORT` | CLI → 环境 → 8000；适用于 Query、`up` 及对应诊断 |
| `--dashboard-port N` / `DASHBOARD_PORT` | CLI → 环境 → 8101；适用于 Dashboard、`up` 及对应诊断 |
| Dashboard `QUERY_URL` | 仅单独 Dashboard 使用；默认 `http://127.0.0.1:8000`。`up` 必须从有效 Query 端口派生，不接受覆盖 |

用户输入和路径环境变量中的相对路径以调用 `./dev` 时的目录为基准；仓库入口及组件工作目录不依赖调用目录。联合启动遇到已有 `DATA_DIR` 或 `QUERY_URL` 与派生值冲突时必须在创建进程前拒绝。Query 的 `MARKET_CALENDAR_DIR`、`SKEW_REFERENCE_DIR` 若已设置，按调用目录转换为绝对路径后传给 Query；缺省保持缺省，显式空字符串映射为调用目录。不展开 `~` 或环境变量占位符、不解引用符号链接、不检查或创建参考目录。`SKEW_TARGET_MONTH` 等其他值保持原样；Runner 只修改 Query 的环境副本，不解释或补写参考业务内容。未知参数、不适用于所选命令的参数、空或越界端口及联合启动的相同端口均为使用错误；HTTP 服务只绑定 loopback 并严格使用有效端口。

## 进程所有权与收尾

- Runner 的 lifecycle ownership 仅覆盖本次调用创建的组件子进程及其受控后代；它随当前 terminal session 工作，不接管其他终端、其他 checkout 或已经存在的进程。不得按进程名、端口或历史 PID 文件取得控制权。
- Runner 不调用 native/systemd 或 Docker/Compose 管理器来启动、停止、安装、启用、更新或替换部署；不创建持久服务、定时器或可跨会话接管的运行状态，不后台驻留、不自动重启。已有部署占用端口或数据目录时报告冲突，由操作者通过原部署入口处理。
- Collector、Query、Dashboard 可分别启动。联合启动只协调本次开发会话，不建立组件间启动或健康依赖。启动后的 Query/Dashboard 退出、HTTP 不可达或业务不可用，不触发 Collector 停止或重启；其他组件也不因同伴退出而被自动停止。Runner 保持管理仍存活的子进程并明确记录失败。
- 用户结束会话，或 runner 收到 SIGINT、SIGTERM、终端 SIGHUP 时，只收尾本次拥有的进程，先发送 SIGTERM 并给予 60 秒正常退出宽限；超时仅可强制结束本次残留进程并明确报告。Collector 正常停止的 SDK 释放与尾部提交仍由 [Collector Contract](../../collector/CONTRACT.md#生命周期与失败语义)定义。SIGKILL、宿主退出或无法送达终端信号不具备正常收尾保证；不得报告尾部已提交。
- Runner 的异常退出路径应尽力收尾自己已创建的进程；不能因清理失败扩大控制范围或隐瞒残留。非零子进程退出、启动失败和强制终止不得被汇总为会话成功。

## 开发配置与数据不变量

- Collector 配置、flow、Raw 仍归 Collector；Runner 只消费已有配置，不创建或改写凭据、采样参数、运行时长、订阅配置，不自动刷新 Universe 或导入参考包。原生管理器的配置准备行为不因此改变，其操作见 [Collector 手册](../../collector/README.md)。
- 开发入口遵守 [Raw Boundary](raw-boundary.md)：不建立第二套事实、迁移 schema、放宽只读规则，或为启动/停止清理数据、flow、日志及现场证据。跨开发会话、native 和 Docker 的同目录互斥仍由 Raw writer 锁最终保证；预检不能代替该锁。
- 联合启动时 Query 必须读取本次 Collector 配置指向的同一数据目录；显式输入冲突应在启动前拒绝，不能静默选择不同目录。单独启动 Query 不需要读取 Collector 凭据配置，也不要求 Collector 运行。
- 配置内相对路径继续以所选配置文件目录为基准，不因统一入口改变含义。Runner 不将 Collector 凭据或 INI 内容传给 Query/Dashboard；诊断不回显凭据或包含凭据的错误原行。
- 环境、配置和端口诊断不启动服务、不改写持久文件、不自动修复配置或释放端口。端口或锁的预检结果只是当时观察；权限不足、不可检查和缺证据必须明确标为未知，不能视为通过。

## Doctor 的账号字段边界

`doctor` 不将 `UserID` / `Password` 的存在、缺省、空值或非空列为诊断项，不提示填写，不因两者缺省或为空产生 warning/error/unknown，也不探测账号有效性或网络登录。不显示其名称对应的值或配置原行。Collector 整体 `--check-config` 校验继续保留；非空值超过 SDK 字段容量等实际配置错误可以整体校验失败并脱敏报告，不得为隐藏账号诊断而绕过安全校验。字段和 MdApi 协议语义见 [Collector Contract](../../collector/CONTRACT.md#行情接入与可选账号字段)。

## 启动与健康的证据语义

| 证据 | 能证明什么 | 不能据此推断什么 |
|---|---|---|
| Process liveness | 本次拥有的进程尚未退出；Collector 心跳另按 Read Path 判定 | HTTP 已监听、CTP 登录/订阅成功、行情在推进 |
| HTTP reachability | 指定地址的 HTTP 请求成功；Query `/healthz` 表达服务自身存活 | 请求一定来自本次新进程、Raw 可读、指标可计算 |
| Business readiness | 按领域 API/Contract 返回的行情、质量、参考输入及可计算状态 | 仅凭进程存在或 HTTP 200 不能建立该结论 |

上述证据分别报告，不合并成“系统就绪”。已有进程可能响应相同 URL，HTTP 检查必须与本次子进程状态分开；业务响应可以是 HTTP 200 且 UNAVAILABLE。休市、缺行情、缺参考包不等于进程失败，也不成为 Collector 启动条件。具体心跳、HTTP 错误和业务质量语义沿用 [Read Path](read-path.md)及其领域契约链接，Runner 不另设业务健康标准。
