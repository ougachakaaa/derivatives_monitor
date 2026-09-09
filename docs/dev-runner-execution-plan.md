# 统一 Linux 本地开发入口：Execution plan

日期：2026-09-09。适用基线：`e17f787` 的运行代码及随本计划提交的文档设计。本文是本次实施交接；当前实现/证据状态唯一登记在 [Acceptance](acceptance.md#本地开发入口交付状态)。计划不要求 implementation session 读取先前 conversation，也不授权通过真实行情运行来验证。

任务 1 已由 `a249ece` 完成。本次仅修订执行计划、收紧交付范围，不改变长期生命周期、部署隔离和 Raw ownership 契约，不新增 MVP 完成门槛。后续 session 从任务 2 开始，按 **2 → 3 → 4 → 5 → 6** 执行；先核对 Git 历史及 Acceptance，避免重复已完成工作。每项实现连同其必要测试形成一个可独立 review 的 commit，最后只登记实际执行的证据。本文中的拟新增路径用代码标记，已有来源用链接。

## 1. Authority 与阅读顺序

1. 阅读 [AGENTS.md](../AGENTS.md) 和[文档入口](README.md)，运行 `python3 harness/run.py docs`，检查工作树，不覆盖用户现场。
2. 阅读 [MVP](mvp.md)、[Design](design.md) §2/§6/§7、[Architecture](architecture.md)，确认产品范围、独立故障域和现有数据流。本任务不新增业务组件。
3. 阅读 [Deployment Contract](contracts/deployment.md) 的 developer runner、开发配置与数据不变量、健康证据语义；这是本任务长期行为 authority。再读 [Collector Contract](contracts/collector.md) 的配置/停止/锁规则和 [Read Path Contract](contracts/read-path.md) 的只读/健康边界。
4. 阅读 [Acceptance](acceptance.md)、[Operations](operations.md)、[Collector](../collector/README.md)、[Query](../query/README.md)、[Dashboard](../dashboard/README.md) 和 [Harness](../harness/README.md)。本任务不改 Analytics，无需扩大到算法实现。
5. 按下表核对实际入口，再读本文 §3–§7，按 commit 依赖实施。

| 信息 | 唯一落位 |
|---|---|
| 为什么开发会话和持久部署分开 | Design |
| 组件结构、runtime 方式与工具所在层 | Architecture |
| 生命周期所有权、部署隔离、配置/数据不变量、健康证据含义 | Deployment Contract；业务细节链接 Collector/Read Path，不在计划重定义 |
| 已实现、已验证、缺证据 | Acceptance |
| 当前可执行命令与排障 | Operations / 模块 README |
| 本次 CLI 交付、实现选择、任务/commit、验收和升级条件 | 本 execution plan；不覆盖以上 authority |

## 2. 已核对的当前入口

| 入口/证据 | 当前实现及复用点 |
|---|---|
| [Collector main](../collector/src/main.cpp)、[配置](../collector/src/config.hpp)、[共用解析器](../collector/include/client_support.hpp) | Release 二进制接受 `--config` / `--check-config`；配置内部路径相对所选配置目录；原有 `RunSeconds` 保留。`--check-config` 在运行和写数据前返回，可复用完整校验 |
| [Collector storage](../collector/src/storage.cpp) | `.collector.lock` 排除同目录第二个 writer；runner 不替换或长期持有此锁 |
| [Query app](../query/app.py)、[依赖](../query/pyproject.toml) | `query/` 工作目录，项目 Python 3.12 `.venv`，Uvicorn；应用默认 `DATA_DIR=/data`，本地必须显式指定；`/healthz` 不验证数据可用性 |
| [Dashboard Vite](../dashboard/vite.config.js)、[npm scripts](../dashboard/package.json) | 默认 `127.0.0.1:8101`，strictPort；`QUERY_URL` 代理 `/api`；既有 Vite CLI 可以覆盖端口 |
| [native manager](../collector/scripts/native.py) | 安装用户 units、刷新 Universe、备份/替换 `InstrumentsFile`、处理 legacy PID、enable/restart 三服务、启动 timer；不是开发入口可调用的进程适配器 |
| [Docker entrypoint](../scripts/deploy.sh)、[Compose](../compose.yaml) | 固定项目和 checkout 保护；先构建/测试/预检再后台更新；三服务日志、stop 保留数据；不作为 runner 底层 |
| [跨进程 smoke](../tests/read_path_smoke.py)、[harness runner](../harness/run.py) | 可参考临时目录、随机端口、TEST DOUBLE SDK、真实 HTTP、独立停启；现有 smoke 直接启动组件，不能当成新 `./dev` 已验收 |

文档 reconciliation 已随 commit 1 完成：配置不覆盖限定到 Docker，原生配置准备写入 Collector README；Architecture 区分 native Vite 与 Docker Nginx；Docker `logs` 描述改为三服务；Dashboard 端口说明改为可通过现有 CLI 显式覆盖。Deployment 区分手工 up 的重启与清单更新器按需重启活跃服务的行为；后者还处理运行订阅集不一致或已有诊断解析失败，证据见 [Universe publish](../collector/scripts/universe.py)。没有调整部署脚本或引入 native Nginx 迁移。

解析器注意事项：C++ `[config]` / key 区分大小写、首个 `=` 分隔、重复 key 最后值生效、整行注释、无插值；不要直接用默认 ConfigParser 引入不同语义。路径提取只服务编排，完整合法性仍由现有二进制检查。C++ 错误可能包含错误原行；校验输出应捕获并做允许列表式的脱敏报告，不直接回显原始 stderr，不保存凭据日志。本任务不借此修改 C++ parser。

## 3. 本次交付目标与实施选择

### CLI 与依赖

交付仓库根可执行 `./dev`，支持：

```bash
./dev --help
./dev collector
./dev query
./dev dashboard
./dev up
./dev doctor
./dev doctor collector
./dev doctor query
./dev doctor dashboard
```

`doctor` 默认检查联合启动所需本地条件；指定组件只检查该组件。单组件启动不要求另外两个组件的依赖、配置或服务存在。未知/不适用参数必须报错，不静默忽略。

推荐薄入口加 Python 标准库监督器，例如 `scripts/dev.py`；文件拆分、同步/异步方案、日志实现及测试文件位置由 implementation agent 自主决定，不是 Architecture constraint。不增加第三方 runner 框架。直接复用 Collector 二进制、`query/.venv/bin/python -m uvicorn`、Node/Vite；避免额外 shell/npm 父进程使信号归属变复杂。不将 `.venv/bin/python` 的符号链接 resolve 成系统 Python。Node 使用当前 Linux PATH 的可执行文件，不硬编码本机历史下载路径。

安装与构建继续走模块手册；runner 不自动运行 CMake、Poetry sync、npm ci 或安装系统包。环境诊断区分运行依赖与构建依赖，缺运行产物时给出构建/安装命令。无需 systemd、Docker daemon、SQLite CLI 或全局 Poetry 才能运行已准备好的对应组件。Query 不新增自动 reload；Dashboard 沿用现有 Vite 开发行为。

### 配置解析与有效运行参数

以下是本次 CLI 交付规则；实现完成时操作用法归 Operations，稳定的公共接口约束归 Deployment Contract，不能仅留在已结束计划中。

| 参数 | 适用命令与优先级 |
|---|---|
| `--config PATH` | Collector / up 及相应 doctor；默认仓库 `collector/config.ini`，不增加隐式配置环境变量 |
| `--data-dir PATH` / `DATA_DIR` | 仅 Query 单独启动及其 doctor 接受 CLI 覆盖；CLI → 环境 → 仓库 `collector/data`。up 的数据目录从 Collector 配置派生，不接受 `--data-dir` |
| `--query-port N` / `QUERY_PORT` | Query / up 及相应 doctor；CLI → 环境 → 8000 |
| `--dashboard-port N` / `DASHBOARD_PORT` | Dashboard / up 及相应 doctor；CLI → 环境 → 8101 |
| `QUERY_URL` | Dashboard 单独启动及其 doctor：环境 → `http://127.0.0.1:8000`；不新增 `--query-url`。up 的代理从有效 Query 端口派生，不接受代理覆盖参数 |
| Query 既有参考环境变量 | 继续传递 `MARKET_CALENDAR_DIR`、`SKEW_REFERENCE_DIR`、`SKEW_TARGET_MONTH` 给 Query；不复制参考业务校验、不自动补值 |

up（及默认联合诊断 doctor）从 Collector 配置派生 Query 数据路径，从有效 Query 端口派生 Dashboard 代理；已有 `DATA_DIR` / `QUERY_URL` 与派生值冲突时，在启动前报错并提示清除冲突变量，不静默忽略。

根路径从入口位置定位，不依赖调用者 cwd；用户传入的相对路径（包括路径环境变量）基于调用时 cwd 转为绝对路径，再进入组件工作目录。Collector INI 内部相对路径按原解析器处理，不提前解引用配置文件符号链接而改变其目录语义。比较数据目录使用标准路径规范化，不建设通用路径识别框架；无法确认时报告原因。省略参数不修改源配置。空或非法显式端口、越界端口及 up 中两服务端口相同均报错；HTTP 服务绑定 loopback，并严格使用指定端口。

为组件构造所需环境，不把 Collector INI 或凭据提取后传给下游。打印组件名、非敏感有效路径、端口、代理目标及修复指引，不 dump 整个环境或配置；URL 中的认证信息也不能回显。

### 诊断与启动报告

`doctor` 只检查所选组件的运行依赖及版本、Collector 现有配置校验、有效路径和监听端口；不联网访问行情/Universe，不启动 HTTP 服务，不写持久文件。配置合法性复用 `--check-config`，二进制无法执行也必须明确报告。

不要求锁探测、目录写入探针、递归权限审计、独立 SDK 审计或 Universe/参考包业务诊断。目录创建仍由组件自身负责；Collector 自身目录锁承担最终互斥，运行时冲突明确报告，不停止既有 writer。

结果区分阻断错误、警告、未知与通过。缺运行依赖、缺有效配置、目标监听端口占用阻断对应启动；不可检查不能记通过。配置引用的 `InstrumentsFile` 缺失由 Collector 配置校验报错；Query 缺业务数据或参考包不阻断 HTTP 进程，也不新增相应业务诊断。单独 Dashboard 的 Query 目标不是其监听端口冲突，不必在线才能启动 Vite。

启动时仅进行一次有界 HTTP 检查阶段，分别检查 Query `/healthz` 和 Dashboard `/`；不假定 Vite 有 Docker Nginx 的 `/healthz`。HTTP 超时只报告警告，不永久污染会话退出码，不持续监控、不停止 Collector、不自动重启。进程存活、HTTP 可达和业务可用分别表达，不能将其他进程对 URL 的响应归为本次组件成功，也不根据 HTTP 成功推断业务可用。代理正确性放在隔离集成测试中验证。

### 会话状态与错误收尾

只管理现有三个组件及其正常受控后代，不处理任意 daemon、主动逃逸进程组或通用进程树接管。长期所有权、信号和 60 秒宽限沿用 [Deployment Contract](contracts/deployment.md#developer-runner-的生命周期边界)。本次状态机还应明确：

- up 的所有本地预检通过后才创建服务子进程；有阻断错误时一个也不启动。
- 预检之后仍可能发生 spawn/bind 失败：记录失败，不自动回滚已经启动的同伴，不把部分成功报告为完整启动。普通组件启动失败可继续尝试其余已通过预检的组件；runner 自身无法继续监督时进入契约要求的自有进程清理路径。
- 正常有限时长 Collector 退出不停止其他组件；有存活子进程时 runner 继续前台等待。所有子进程退出才自然结束会话，或由用户主动结束会话。每组件记录退出码；已失败状态不能因后来 Ctrl-C 清除。
- 建议退出码：无失败自然结束为 0；使用错误为 2；预检、spawn、子进程非零退出或强制结束产生的会话失败为 1；没有先前失败的用户信号结束为 `128 + signal`。用户结束会话导致的预期 SIGTERM 不算组件异常。
- 日志标识来源并及时输出；读取/写入日志不能死锁或无限缓冲。EOF、终端输出关闭、重复信号及启动/清理间竞态都应有确定行为。信号发送只针对仍属于本次的受控进程组，不误伤终端 shell 或已被复用的 PID/PGID。

## 4. Task / commit decomposition

任务 1 已完成，后续依赖链为 **2 → 3 → 4 → 5 → 6**。每项包含必要测试并形成一个可独立 review 的 commit，按顺序实施，不扩展为通用进程管理框架。

| Commit / 推荐标题 | 依赖 | 交付与 acceptance criteria |
|---|---|---|
| 1 `docs: define developer runner boundaries and execution plan` | 已确认设计 | 已由 `a249ece` 完成 authority 分层、reconciliation、交接计划、状态与导航；本次仅修订执行计划 |
| 2 `feat(dev): add component-scoped diagnostics` | 1 与本次计划修订 | help、必要参数解析、组件级 doctor；验证依赖隔离、配置脱敏、路径和端口错误、诊断无持久写入；不启动服务或调用管理器 |
| 3 `feat(dev): run individual components in foreground` | 2 | 直接调用现有三个组件入口；验证正常/异常退出、INT/TERM/HUP、60 秒停止宽限、超时清理、自有正常后代清理及外部进程不受影响 |
| 4 `feat(dev): orchestrate the local development session` | 3 | 复用组件监督逻辑，派生数据路径与代理；验证环境冲突、预检失败零启动、部分启动失败、同伴继续运行、启动期间信号及 HTTP 超时仅警告；进程失败退出码可复查 |
| 5 `test(dev): verify isolated lifecycle and deployment boundaries` | 4 | 一个实际通过 `./dev` 的 Collector→Query→Vite 隔离闭环；验证代理、同一 Raw、下游退出后继续提交、正常停止与再次追加、运行时目录互斥；定向测试与闭环接入现有 offline，保留入口依赖方向和镜像排除检查；测试超时清理自有进程 |
| 6 `docs: publish local development usage and evidence` | 5 | 发布实际用法、登记真实工程证据、同步必要公共接口说明；确认完成后结束计划并移除活动导航；未执行或缺证据不写通过 |

## 5. 验证与完成边界

每个实现 commit 带相关测试，不把基础覆盖推迟到 commit 5。测试只使用临时目录、随机本地端口和标明 TEST DOUBLE 的数据/SDK；不读取真实 INI，不连接真实 CTP，不触碰正式部署。用禁止调用的 systemctl/docker 替身以及外部无关进程验证控制边界，不能通过实际启动/停止管理器验证“不接管”。

| 范围 | 验证入口/证据 |
|---|---|
| 本次文档修订 | `python3 harness/run.py docs`、`git diff --check`；人工核对建议已删除、任务验收与收紧边界一致、长期契约未被削弱；只提交本文件修订，然后停止，不开始实现 |
| Commit 2–4 | 新 runner 的定向标准库/子进程测试；不要求全栈依赖才能运行纯诊断和监督器替身测试 |
| Commit 5 完整离线 | `python3 harness/run.py offline`，将定向 runner 测试及一个隔离闭环纳入现有 profile；保留原 deploy 替身等既有验证 |
| Commit 5 实际进程链 | 新隔离 smoke 通过 `./dev` 运行真实 C++/SQLite、Uvicorn、Vite 及代理，行情源为 TEST DOUBLE。接入现有 offline profile，不新增 profile，不改变 native profile 的依赖要求；同步 Harness 用法和 NOT_RUN 判定 |
| 构建与依赖边界 | 扩展 [入口检查](../harness/check_docs.py)覆盖实际新增入口；原 Dockerfile/allowlist 不变，新开发文件不得进入镜像。`packaging` 可提供真实 scratch context 证据 |
| Docker 生命周期 | 不新增完整 Docker runtime 或浏览器验收门槛。本任务不改部署实现。只有声称本版本 Docker runtime 已验证时才需完整隔离 `docker` profile；静态检查、deploy 替身、packaging 均不能代替它。不可用则明确未执行，不通过操作正式项目补证据 |

父 harness 当前会给命令建立进程组；runner 若再建立组件组，测试必须验证超时/中断时这些组也被清理，不能假设杀最外层组就足够。正常收尾的 60 秒宽限与 harness 超时预算要相容；缩短测试时间可使用受控测试机制，但不得缩短生产要求或把未运行的宽限行为写成通过。

最终验收至少包括：单组件缺少同伴依赖仍可启动；up 使用同一 Raw 路径及正确代理；诊断无持久写入/凭据泄漏；端口与 writer 冲突不影响已有进程；下游退出 Collector 继续提交；会话正常结束无自有进程残留；重新启动保留已提交记录；无 systemd/Docker 生命周期操作；文档与可用 CLI 一致。

结果保存按 Harness 约定执行，未执行/缺依赖/跳过不能记 PASS。本次计划修订不新增 MVP 完成门槛；runner 工程完成不能替代真实行情、指标对账、日常使用和恢复证据，也不等于关闭 MVP G1–G6 或实盘 Skew 门槛。完成后在 Acceptance 登记实际结论，将本文标记完成并移除活动导航；不拆成 `docs/tasks/` 或另积累每个 commit 的过程 spec。长期新规则及时归对应 authority，历史可从 Git 追溯。

## 6. Out of scope

- 改 Collector/Query/Dashboard 业务实现、Raw schema/ownership、SQLite 锁/只读语义、Analytics 模型/参数/质量标准。
- 重构或迁移 native manager、legacy PID 清理、systemd units/timer、Compose、Dockerfile/build allowlist；将 native Vite 换成 Nginx。
- 持久 daemon、后台 up、跨终端 stop/restart/status 接管、自动重启、自动安装/构建、自动 Universe 更新、参考包导入、凭据生成。
- 通用进程树发现/接管、任意 daemon 或主动逃逸进程组的管理、持续健康监控。
- 锁探测、目录写入探针、递归权限审计、独立 SDK 审计、Universe/参考包业务诊断、第二套完整 INI 校验器。
- 外网暴露、认证、WebSocket、Dev Container、其他操作系统支持；真实采集、备份恢复或实盘性能验收。
- 新增业务 API 健康标准、以 HTTP 200 代替业务可用性、为测试方便修改冻结契约。

## 7. Escalation：何时停止相关实现并回到 design

下列情况应保留工作和失败证据，停止受影响的实现，明确提出冲突的 authority 与最小决策请求；不得静默扩大范围：

1. 满足目标需要接管既有进程、修改 systemd/Docker 生命周期，或使 Query/Dashboard 故障停止/重启 Collector。
2. 需要改配置语义、Raw ownership/schema、writer 锁/只读行为，或要靠复制/改写真实配置与数据消除冲突。
3. 无法在现有组件入口上保证信号只作用于本次进程；出现 PID/PGID 误伤、正常受控后代残留、无法符合 60 秒正常停止，且局部监督器修复不能解决；或需要引入通用进程管理能力。
4. 配置有效路径无法与现有 C++ 解析一致，必须改 Collector 接口/解析器或凭据处理才能继续；先提出最小接口方案，不顺手重构共用头文件。
5. 需要修改 API、健康/业务 readiness 定义、采样/Analytics 参数或降低验收标准才能让启动显示成功。
6. 新实现基线与本文 reconciliation 或长期契约有实质冲突，且不能通过保持现有语义的局部调整兼容；先定位 authority，不让代码差异静默成为新设计。

普通缺依赖、端口被占、Docker Engine 不可用或范围内测试失败不自动构成设计问题：使用已有隔离验证、报告 NOT_RUN 或修复范围内代码。若后续动作必须影响真实服务/数据或扩大任务范围，则停止该动作并取得对应授权；本计划不授权其执行。
