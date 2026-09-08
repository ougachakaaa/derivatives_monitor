# MVP 验收 Harness

这个入口组织现有模块测试和跨进程/容器测试，为[验收矩阵](../docs/acceptance.md)提供可定位证据。它不启动实盘、不修改真实配置/data/flow、不清理 `experiments/`，也不会把工程测试成功标成 MVP 完成。

在仓库根目录执行（只需 Python 标准库运行组织器）：

```bash
python3 harness/run.py docs
python3 harness/run.py offline
python3 harness/run.py native
python3 harness/run.py browser
python3 harness/run.py packaging
python3 harness/run.py docker
```

| Profile | 前提与动作 |
|---|---|
| `docs` | 检查维护文档的本地文件链接、设计入口、原件/SDK 哈希和必要 Docker 白名单；不访问外网，不验证 Markdown 锚点 |
| `offline` | CMake/G++/SQLite 开发库、Python 3.12 的 `query/.venv`、Linux Node 22.12+/npm/已安装前端依赖、SQLite CLI；重新 configure/build Release，执行 CTest、Query、Universe、deploy 替身、verify 真 SQLite CLI、React 和构建 |
| `native` | 原生编译及 query 依赖；重新构建后运行合成夜盘与真实 HTTP 独立停启测试，临时数据/随机端口 |
| `browser` | native 前提，加 Linux Node/前端依赖、Playwright Chromium 及系统库；合成夜盘与含浏览器的原生闭环 |
| `packaging` | Docker Engine；实际 scratch COPY 检查构建输入字节与运行目录排除，无需拉取基础镜像，不证明 runtime 镜像可运行 |
| `docker` | Docker Engine + Compose v2、Bash；隔离三容器和 Collector 生命周期测试，构建镜像，可能下载基础镜像/依赖；默认自动清理本次专用容器/镜像 |

除了 `docs` 外均先运行 harness 自测。`docker` 包含 packaging 检查；基础镜像仓库不可达时可单独运行 packaging，不能据此宣称完整容器验收通过。各 profile 独立，选择与修改相关的范围；需要完整工程证据时分别运行 offline、browser、docker。浏览器 profile 的 read-path 已含 native HTTP，不必为同一版本重复运行 native。真实行情和人工使用/对账/恢复/性能门槛用[现场模板](live-acceptance-template.md)记录，不包含在任何自动 profile 中。

所有命令和日志写到被 Git 忽略的 `artifacts/harness/<UTC>-<profile>-<id>/`。`result.json` 保存 HEAD、dirty 状态、平台、命令/工作目录、退出码、时长、日志 SHA-256、工作树补丁及未跟踪源码哈希。只应提交脱敏验收摘要，不提交行情或配置。报告的 `mvp_complete` 始终 false；归档时同时保留对应源码版本/补丁，否则 dirty tree 报告不能复现。

缺依赖返回 NOT_RUN（退出码 2），失败返回 FAIL（退出码 1），全部已执行通过才返回 PASS（0）。命令输出发现跳过测试、unittest/CTest 未发现测试时不能当作通过。先前必要步骤失败后余项明确 NOT_RUN；修复环境后重新运行对应 profile。超时/中断会终止本次命令进程组，日志保留；Docker 脚本自身负责清理隔离项目，失败时按其输出处理本次测试资源，不操作正式项目。

宿主原生环境准备见 [Collector](../collector/README.md)、[Query](../query/README.md)、[Dashboard](../dashboard/README.md)。若开发包解压在用户目录，先按手册配置 CMake 的 SQLite include/library；harness 复用同一 Release 缓存。将所选 Linux Node、sqlite3 所在目录加入本次 shell 的 PATH；不使用 Windows npm 混合 Linux 依赖，不自动安装或升级工具。

测试文件维持模块归属，避免为了统一命令移动测试导致 Docker/CMake/import 路径变化：

- `collector/tests/`：采集/存储/生命周期、配置、清单、部署/验收器与 Collector 容器。
- `query/tests/`：真实 SQLite 只读、API、Calendar、Universe coverage、Market State。
- `dashboard/tests/`：React 组件和实际浏览器交互。
- `tests/`：跨 C++/SQLite/HTTP/容器的集成场景。
- `harness/tests/`：结果分类、缺依赖/超时、模拟环境隔离、打包白名单回归。

TEST DOUBLE 不等于真实 CTP；100ms 合成场景不等于生产 15 秒调度，后者由专门 CTest 验证。历史成功次数不写死在 runner 中；正式验收仍要审查每项测试覆盖的契约。
