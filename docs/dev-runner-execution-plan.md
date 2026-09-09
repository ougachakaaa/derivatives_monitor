# 统一 Linux 本地开发入口：Execution plan

日期：2026-09-09。适用基线：`e17f787` 的运行代码及随本计划提交的文档设计。本文是本次实施交接；当前实现/证据状态唯一登记在 [Acceptance](acceptance.md#本地开发入口交付状态)。计划不要求 implementation session 读取先前 conversation，也不授权通过真实行情运行来验证。

本次文档提交完成下面的 commit 1。后续 session 从 commit 2 开始；先核对 Git 历史及 Acceptance，避免重复已完成工作。每项实现连同其必要测试形成一个可独立 review 的 commit，最后只登记实际执行的证据。本文中的拟新增路径用代码标记，已有来源用链接。

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
| `--data-dir PATH` / `DATA_DIR` | Query / up 及相应 doctor；CLI 高于环境变量。Query 单独默认仓库 `collector/data`；up 未显式指定时使用所选 Collector 配置的有效 DataDirectory；显式值必须与其指向同一目录，否则拒绝启动 |
| `--query-port N` / `QUERY_PORT` | Query / up 及相应 doctor；CLI → 环境 → 8000 |
| `--dashboard-port N` / `DASHBOARD_PORT` | Dashboard / up 及相应 doctor；CLI → 环境 → 8101 |
| `--query-url URL` / `QUERY_URL` | Dashboard 单独启动及其 doctor：CLI → 环境 → `http://127.0.0.1:8000`；up 自动由有效 Query 端口构造，显式值仅在与本次目标一致时接受，否则拒绝 |
| Query 既有参考环境变量 | 继续传递 `MARKET_CALENDAR_DIR`、`SKEW_REFERENCE_DIR`、`SKEW_TARGET_MONTH` 给 Query；不复制参考业务校验、不自动补值 |

根路径从入口位置定位，不依赖调用者 cwd；用户传入的相对路径（包括路径环境变量）基于调用时 cwd 转为绝对路径，再进入组件工作目录。Collector INI 内部相对路径按原解析器处理，不提前解引用配置文件符号链接而改变其目录语义。比较数据目录时识别等价路径/符号链接别名，不能以字符串不同误报冲突；无法确认时报告原因。省略参数不修改源配置。空或非法显式端口、越界端口及 up 中两服务端口相同均报错；HTTP 服务绑定 loopback，并严格使用指定端口。

为组件构造所需环境，不把 Collector INI 或凭据提取后传给下游。打印组件名、非敏感有效路径、端口、代理目标及修复指引，不 dump 整个环境或配置；URL 中的认证信息也不能回显。

### 诊断与启动报告

`doctor` 不联网访问行情/Universe，不启动 HTTP 服务；检查 Linux x86-64/WSL 环境、目标组件可执行文件及版本/运行依赖、Collector SDK 动态依赖、配置/订阅文件、数据/flow 路径权限、端口。只读探测已有锁文件且立即释放，不创建锁文件，不阻塞活跃 writer。目录不存在时只检查最近已有父目录的创建条件，不用写探针；启动时仍由组件自身创建其拥有的目录。

结果分为阻断错误、警告、未知与通过。缺二进制、缺有效配置、目标监听端口占用阻断对应启动；业务数据/审核参考缺失只报告业务缺口，不能阻断独立进程启动。特别地：配置显式引用的 `InstrumentsFile` 缺失是 Collector 配置错误，而 Query 缺 Universe/参考包不应阻断 HTTP 进程。单独 Dashboard 的已有 Query 目标不是端口冲突，也不必在线才能启动 Vite。

启动后对自有进程和 HTTP 分开报告。Query 可探测 `/healthz`，Vite 可探测 `/`，代理链可用 `/api/health` 验证；Vite 不假定存在 Docker Nginx 的 `/healthz`。探测必须有有限超时，不等待实盘登录/行情；超时报告 HTTP 尚不可达，不杀 Collector、不自动重启。不能将其他进程对 URL 的响应归为本次组件成功。

### 会话状态与错误收尾

长期所有权、信号和 60 秒宽限沿用 [Deployment Contract](contracts/deployment.md#developer-runner-的生命周期边界)。本次状态机还应明确：

- up 的所有本地预检通过后才创建服务子进程；有阻断错误时一个也不启动。
- 预检之后仍可能发生 spawn/bind 失败：记录失败，不自动回滚已经启动的同伴，不把部分成功报告为完整启动。普通组件启动失败可继续尝试其余已通过预检的组件；runner 自身无法继续监督时进入契约要求的自有进程清理路径。
- 正常有限时长 Collector 退出不停止其他组件；有存活子进程时 runner 继续前台等待。所有子进程退出才自然结束会话，或由用户主动结束会话。每组件记录退出码；已失败状态不能因后来 Ctrl-C 清除。
- 建议退出码：无失败自然结束为 0；使用错误为 2；预检、spawn、子进程非零退出、探测超时或强制结束产生的会话失败为 1；没有先前失败的用户信号结束为 `128 + signal`。用户结束会话导致的预期 SIGTERM 不算组件异常。
- 日志标识来源并及时输出；读取/写入日志不能死锁或无限缓冲。EOF、终端输出关闭、重复信号及启动/清理间竞态都应有确定行为。信号发送只针对仍属于本次的受控进程组，不误伤终端 shell 或已被复用的 PID/PGID。

## 4. Task / commit decomposition

依赖链：**commit 1 → 2 → 3 → 4 → 5 → 6**。按顺序 review；不为了并行让不同 agent 同时改同一监督器。推荐模型是本次风险判断，不是仓库长期工具要求；不要求开启多 agent。

| Commit / 推荐标题 | 依赖 | 交付与 acceptance criteria | 推荐 model / effort |
|---|---|---|---|
| 1 `docs: define developer runner boundaries and execution plan` | 已确认设计 | 本次文档提交：authority 分层、reconciliation、独立交接计划、状态与导航；docs 检查通过；无源码、tests、runtime scripts 变更 | `gpt-6-astra` / medium |
| 2 `feat(dev): add component-scoped diagnostics` | 1 | help、参数/路径/配置解析、doctor；标准库测试覆盖 cwd/空格/符号链接、配置解析差异、依赖隔离、脱敏、端口、同目录冲突；诊断前后配置/data/flow 内容不变；不启动服务或调用管理器 | `gpt-6-astra` / high |
| 3 `feat(dev): run individual components in foreground` | 2 | 三个独立启动命令及公共监督器；TEST DOUBLE 子/孙进程验证正常退出、非零退出、INT/TERM/HUP、重复信号、超时强杀、外部进程不受影响；不产生持久 PID 状态；启动命令与既有组件兼容 | `gpt-6-astra` / high |
| 4 `feat(dev): orchestrate the local development session` | 3 | up 全量预检、数据/端口/代理联动、组件日志与状态汇总；测试预检零启动、部分 spawn/bind 失败、同伴不连带停止、所有退出、信号与启动竞态、HTTP 超时/业务不可用不杀进程；失败退出码可复查 | `gpt-6-astra` / xhigh |
| 5 `test(dev): verify isolated lifecycle and deployment boundaries` | 4 | 通过实际 `./dev` 做临时配置/数据、随机端口、TEST DOUBLE SDK 的 Collector→Query→Vite smoke；检查代理、只读、下游独立失败、正常停止/再次追加、目录互斥；harness 接入、入口依赖方向与镜像排除回归；测试超时清理不遗留受控孙进程 | `gpt-6-astra` / high |
| 6 `docs: publish local development usage and evidence` | 5 | 根 README/Operations 的实际使用入口、模块链接、公共 CLI 规则最终落位、harness 用法；Acceptance 记录版本/命令/结果/证据限制；无缺证据却写通过；计划完成标记和活动导航收尾 | `gpt-6-astra` / medium |

模型建议核对于 2026-09-09：[OpenAI 官方 GPT-6 Astra 文档](https://developers.openai.com/api/docs/models/gpt-6-astra)列出上述 effort 支持。具体任务分配是本计划根据配置风险、信号竞态和跨进程验证复杂度作出的判断，不是官方基准结论。后续环境若不提供该模型，可使用可用的同级 coding model 并记录选择；模型不可用本身不需要回到 design。遇到难以定位的竞态可先提高 effort，不能靠更换模型放宽验收。

## 5. 验证与完成边界

每个实现 commit 带相关测试，不把基础覆盖推迟到 commit 5。测试只使用临时目录、随机本地端口和标明 TEST DOUBLE 的数据/SDK；不读取真实 INI，不连接真实 CTP，不触碰正式部署。用禁止调用的 systemctl/docker 替身以及外部无关进程验证控制边界，不能通过实际启动/停止管理器验证“不接管”。

| 范围 | 验证入口/证据 |
|---|---|
| 本次文档提交 | `python3 harness/run.py docs`、`git diff --check`、人工 authority 与文档/实现核对；不执行 native/docker 管理命令 |
| Commit 2–4 | 新 runner 的定向标准库/子进程测试；不要求全栈依赖才能运行纯诊断和监督器替身测试 |
| Commit 5 完整离线 | `python3 harness/run.py offline`，将定向 runner 测试纳入合理步骤；保留原 deploy 替身等既有验证 |
| Commit 5 实际进程链 | 新隔离 smoke 通过 `./dev` 运行真实 C++/SQLite、Uvicorn、Vite 及代理，行情源为 TEST DOUBLE。选择 native profile 接入或独立明确的 harness profile；若增加 Node 前提，同步 Harness 用法和 NOT_RUN 判定 |
| 构建与依赖边界 | 扩展 [入口检查](../harness/check_docs.py)覆盖实际新增入口；原 Dockerfile/allowlist 不变，新开发文件不得进入镜像。`packaging` 可提供真实 scratch context 证据 |
| Docker 生命周期 | 本任务不改部署实现。只有声称本版本 Docker runtime 已验证时才需完整隔离 `docker` profile；静态检查、deploy 替身、packaging 均不能代替它。不可用则明确未执行，不通过操作正式项目补证据 |

父 harness 当前会给命令建立进程组；runner 若再建立组件组，测试必须验证超时/中断时这些组也被清理，不能假设杀最外层组就足够。正常收尾的 60 秒宽限与 harness 超时预算要相容；缩短测试时间可使用受控测试机制，但不得缩短生产要求或把未运行的宽限行为写成通过。

最终验收至少包括：单组件缺少同伴依赖仍可启动；up 使用同一 Raw 路径及正确代理；诊断无持久写入/凭据泄漏；端口与 writer 冲突不影响已有进程；下游退出 Collector 继续提交；会话正常结束无自有进程残留；重新启动保留已提交记录；无 systemd/Docker 生命周期操作；文档与可用 CLI 一致。

结果保存按 Harness 约定执行，未执行/缺依赖/跳过不能记 PASS。可交付 runner 工程功能不等于关闭 MVP G1–G6 或实盘 Skew 门槛。完成后在 Acceptance 登记实际结论，将本文标记完成并移除活动导航；不拆成 `docs/tasks/` 或另积累每个 commit 的过程 spec。长期新规则及时归对应 authority，历史可从 Git 追溯。

## 6. Out of scope

- 改 Collector/Query/Dashboard 业务实现、Raw schema/ownership、SQLite 锁/只读语义、Analytics 模型/参数/质量标准。
- 重构或迁移 native manager、legacy PID 清理、systemd units/timer、Compose、Dockerfile/build allowlist；将 native Vite 换成 Nginx。
- 持久 daemon、后台 up、跨终端 stop/restart/status 接管、自动重启、自动安装/构建、自动 Universe 更新、参考包导入、凭据生成。
- 外网暴露、认证、WebSocket、Dev Container、其他操作系统支持；真实采集、备份恢复或实盘性能验收。
- 新增业务 API 健康标准、以 HTTP 200 代替业务可用性、为测试方便修改冻结契约。

## 7. Escalation：何时停止相关实现并回到 design

下列情况应保留工作和失败证据，停止受影响的实现，明确提出冲突的 authority 与最小决策请求；不得静默扩大范围：

1. 满足目标需要接管既有进程、修改 systemd/Docker 生命周期，或使 Query/Dashboard 故障停止/重启 Collector。
2. 需要改配置语义、Raw ownership/schema、writer 锁/只读行为，或要靠复制/改写真实配置与数据消除冲突。
3. 无法在现有组件入口上保证信号只作用于本次进程；出现 PID/PGID 误伤、受控后代逃逸、无法符合 60 秒正常停止，且局部监督器修复不能解决。
4. 配置有效路径无法与现有 C++ 解析一致，必须改 Collector 接口/解析器或凭据处理才能继续；先提出最小接口方案，不顺手重构共用头文件。
5. 需要修改 API、健康/业务 readiness 定义、采样/Analytics 参数或降低验收标准才能让启动显示成功。
6. 新实现基线与本文 reconciliation 或长期契约有实质冲突，且不能通过保持现有语义的局部调整兼容；先定位 authority，不让代码差异静默成为新设计。

普通缺依赖、端口被占、Docker Engine 不可用、模型不可用或替身测试失败不自动构成设计问题：使用已有隔离验证、报告 NOT_RUN 或修复范围内代码。若后续动作必须影响真实服务/数据或扩大任务范围，则停止该动作并取得对应授权；本计划不授权其执行。
