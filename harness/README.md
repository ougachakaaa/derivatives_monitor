# MVP 验收 Harness

这个入口组织现有模块测试和跨进程/容器测试，为[验收矩阵](../docs/acceptance.md)提供可定位证据。它不启动实盘、不修改真实配置/data/flow、不清理 `experiments/`，也不会把工程测试成功标成 MVP 完成。

在仓库根目录执行（只需 Python 标准库运行组织器）：

```bash
python3 harness/run.py docs
python3 harness/run.py analytics-contract
python3 harness/run.py analytics
python3 harness/run.py offline
python3 harness/run.py native
python3 harness/run.py browser
python3 harness/run.py packaging
python3 harness/run.py docker
```

| Profile | 前提与动作 |
|---|---|
| `docs` | 检查维护文档的本地文件链接与 authority 入口、正式构建/运行不得反向依赖 `experiments/`、原件/SDK 哈希和必要 Docker 白名单；不访问外网，不验证 Markdown 锚点 |
| `analytics-contract` | 仅标准库；核对七项冻结状态、策略/生成器哈希，使用float64二分与固定独立oracle核对价格/IV/delta/远期/两翼；不运行生产Analytics |
| `analytics` | 在 `analytics-contract` 基础上，用 `query/.venv` 运行生产 Analytics 及 Skew HTTP 切片正常、异常和边界回归；不读取实盘、不证明官方参考可用 |
| `offline` | CMake/G++/SQLite 开发库、Python 3.12 的 `query/.venv`、Linux Node 22.12+/npm/已安装前端依赖、SQLite CLI；重新 configure/build Release，执行 CTest、developer runner 隔离测试及实际 `./dev` TEST DOUBLE 链路、Query、Universe、deploy 替身、verify 真 SQLite CLI、React 和构建 |
| `native` | 原生编译及 query 依赖；重新构建后运行合成夜盘与真实 HTTP 独立停启测试，临时数据/随机端口 |
| `browser` | native 前提，加 Linux Node/前端依赖、Playwright Chromium 及系统库；合成夜盘与含浏览器的原生闭环 |
| `packaging` | Docker Engine；分别以三个正式 Dockerfile 的 `context-audit` scratch stage 导出实际上下文，逐字节核对每个镜像的精确输入集合；无需拉取基础镜像，不证明 runtime 镜像可运行 |
| `docker` | Docker Engine + Compose v2、Bash；通过仓库根 Compose 构建并隔离测试三容器，再执行 Collector 生命周期测试；可能下载基础镜像/依赖，默认自动清理本次专用容器/镜像 |

除了 `docs` 外均先运行 harness 自测。`docker` 包含 packaging 检查；基础镜像仓库不可达时可单独运行 packaging，不能据此宣称完整容器验收通过。各 profile 独立，选择与修改相关的范围；需要完整工程证据时分别运行 offline、browser、docker。浏览器 profile 的 read-path 已含 native HTTP，不必为同一版本重复运行 native。真实行情和人工使用/对账/恢复/性能门槛用[现场模板](live-acceptance-template.md)记录，不包含在任何自动 profile 中。

`docs` 只执行可确定的结构检查。依赖方向检查限定于正式镜像输入清单及根/原生运行入口；历史 archive、说明文字、测试和 experiment 局部内容不参与判定。实现状态措辞、Design/Architecture 分工和业务语义仍需按文档 authority 人工审查。

所有命令和日志写到被 Git 忽略的 `artifacts/harness/<UTC>-<profile>-<id>/`。`result.json` 保存 HEAD、dirty 状态、平台、命令/工作目录、退出码、时长、日志 SHA-256、工作树补丁及未跟踪源码哈希。只应提交脱敏验收摘要，不提交行情或配置。报告的 `mvp_complete` 始终 false；归档时同时保留对应源码版本/补丁，否则 dirty tree 报告不能复现。

缺依赖返回 NOT_RUN（退出码 2），失败返回 FAIL（退出码 1），全部已执行通过才返回 PASS（0）。命令输出发现跳过测试、unittest/CTest 未发现测试时不能当作通过。先前必要步骤失败后余项明确 NOT_RUN；修复环境后重新运行对应 profile。超时/中断会终止本次命令进程组，日志保留；Docker 脚本自身负责清理隔离项目，失败时按其输出处理本次测试资源，不操作正式项目。

宿主原生环境准备见 [Collector](../collector/README.md)、[Query](../query/README.md)、[Dashboard](../dashboard/README.md)。若开发包解压在用户目录，先按手册配置 CMake 的 SQLite include/library；harness 复用同一 Release 缓存。将所选 Linux Node、sqlite3 所在目录加入本次 shell 的 PATH；不使用 Windows npm 混合 Linux 依赖，不自动安装或升级工具。

测试文件维持模块归属，避免为了统一命令移动测试导致 Docker/CMake/import 路径变化：

- `collector/tests/`：采集/存储/生命周期、配置、清单、部署/验收器与 Collector 容器。
- `query/tests/`：真实 SQLite 只读、API、Calendar、Universe coverage、Market State、生产 Analytics 核心、Skew HTTP 及只读参考包适配。
- `dashboard/tests/`：React 组件与实际浏览器交互；Skew 场景明确为 TEST DOUBLE，覆盖当前值、当日变化、历史分钟、PARTIAL/STALE/UNAVAILABLE 及 API 断线清值。
- `tests/`：跨 C++/SQLite/HTTP/容器的集成场景，包括临时目录和随机端口上的实际 `./dev` TEST DOUBLE 链路。
- `harness/tests/`：结果分类、缺依赖/超时、模拟环境隔离、打包白名单回归。

TEST DOUBLE 不等于真实 CTP；100ms 合成场景不等于生产 15 秒调度，后者由专门 CTest 验证。历史成功次数不写死在 runner 中；正式验收仍要审查每项测试覆盖的契约。

## Developer runner 验证

正式证据入口是现有 `offline` profile：

```bash
python3 harness/run.py offline
```

它要求 Collector Release build 所需工具、`query/.venv`、Linux Node/npm 与前端依赖，以及 `sqlite3` CLI；本地工具不在默认 `PATH` 时，按上文说明只为本次 shell 加入相应 `bin`。profile 会重新构建后运行 runner 标准库隔离测试和实际 `./dev` TEST DOUBLE 链路，并继续执行原有 Query、Universe、deploy、verify、React 与前端构建；任一前置缺失都按全 profile 的 PASS/FAIL/NOT_RUN 规则处理。

开发 runner 的快速定向检查可单独运行，但不能代替完整 profile 报告：

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p 'test_dev*.py' -v
PYTHONDONTWRITEBYTECODE=1 python3 tests/dev_runner_smoke.py
```

第二条还要求已构建的共享模式 Collector 与 TEST DOUBLE SDK、`query/.venv`、Linux Node 和已安装 Vite；它只在临时配置/data/flow 与随机 loopback 端口运行。实际开发启动前的本机条件检查使用 `./dev doctor`，不是工程验收报告。

## Analytics / Skew 契约数值基线

规范：[mo-skew-25d-v1](../docs/contracts/analytics-skew.md)，常量：[策略JSON](../docs/contracts/analytics-skew-v1.json)，固定期望：[SYNTHETIC数值样本](fixtures/analytics-skew-v1.json)。样本包括12组价格/IV/delta和高精度价格、两条按tick舍入的完整合成链（两种Skew符号）、插值/单位例子。`analytics-contract` 用独立的标准库实现检查这些例子和失败/误用回归，不读取生产模块。`analytics` 再让生产模块消费合成 Market State minute frame 与显式 ReferenceBundle，核对固定期望及失败状态；`analytics` 还运行真实临时 SQLite → Market State → Analytics → HTTP 的 TEST DOUBLE 回归，覆盖分钟选择、历史/当前、固定revision序列/迟到写入、失败缺口、哈希与错误；两者都不读取实盘。

重新核对外部 oracle（单独验证环境，不改Query依赖）：

```bash
python3 -m venv artifacts/analytics-oracle-env
artifacts/analytics-oracle-env/bin/python -m pip install -r harness/analytics-oracle-requirements.txt
artifacts/analytics-oracle-env/bin/python harness/analytics_oracle.py
```

生成器使用固定 QuantLib 1.40 与80位 mpmath 1.3.0，不导入生产或harness数值实现；默认只比较，不覆盖入库样本。需要审核新版本时用 `--output <新的文件路径>` 写新文件，生成器拒绝覆盖已有文件。生成器/策略的SHA-256随样本保存；不要因为实现失败就重新生成expected。

`analytics-contract` 中的选择和二分函数仅供设计样本自洽核对，**不是生产实现或完整质量/时段测试**。生产实现不import这些函数或oracle；`analytics` profile 另行覆盖固定oracle和契约§8.4生产行为。至少10个真实时点的§8.5对账仍是现场门槛；通过任一自动profile都不会关闭G3。
