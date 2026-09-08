# 2026-09-08 文档、架构与 Harness 整理验收

本记录只验收本轮仓库整理，不代表产品 MVP 完成。基线为 `56dcb4b`，最终变更尚未提交。

## 交付与边界

现行入口为 README → docs/README → MVP/架构/长期契约/验收矩阵/操作手册；新增 AGENTS.md 提供人和 agent 相同阅读路径。过程 specs 已删除，原阶段约束的稳定部分合并为五份长期契约；历史验收单独归档并标注版本和限制。

中信建投 DOCX（包含回复）与历史 API CHM 从 Git 原字节恢复，来源和 SHA-256 入库；保留原有接入摘要、字段表、SDK 清单与下载入口。无法确认的 SDK 原包直链明确标缺，不编造地址。

测试保留模块归属，harness 统一入口记录命令/版本/结果与日志哈希，实盘门槛使用单独模板。修复 Docker 白名单遗漏的 Query Calendar/Market State/年历输入，并修复放行父目录后隐式带入 data/build/.venv 等后代目录的问题；实际 Docker COPY 发现并验证这一修复。未改变 Collector/Query/Dashboard 业务逻辑或 Raw schema。忽略本地 artifacts、工具缓存与 Vite 缓存，不删除原有运行目录或证据。

## 本轮验证

本机 Linux/WSL，Python 3.12 Query 环境、Node 22.16.0、真实 Docker Engine 29.7.1。SQLite CLI 与浏览器缺少的 NSPR/NSS/ALSA 库通过 Ubuntu 包解压到被忽略的 `collector/build/deps/`；未更改系统包、真实服务或配置。Playwright Chromium 下载到用户缓存。源码仍为基线 HEAD 加本轮未提交改动，各报告记录实际工作树补丁/哈希。

| 检查 | 实际结果 | 本机证据目录（均在 `artifacts/harness/`） |
|---|---|---|
| 离线完整 profile | PASS；7项 CTest、46项 Query、9项 Universe、9项 deploy、4项 SQLite CLI、7项 React、5项 harness 自测，以及前端生产构建 | `20260908T051219Z-offline-0503f7ca/` |
| 原生跨进程 | PASS；合成夜盘、真实 C++/SQLite/FastAPI、独立停启/恢复和心跳过期 | `20260908T051123Z-native-b4f23d6e/` |
| 浏览器 profile | PASS；补齐本地依赖后，Chromium 实际页面/断网恢复/移动布局及原生闭环 | `20260908T051544Z-browser-1e5f40c3/` |
| 实际 Docker 上下文 | PASS；scratch COPY 后逐字节比较必要源文件/SDK/年历并检查运行目录排除；约6.14MB | `20260908T051318Z-packaging-d24e397e/` |
| 完整容器 profile | FAIL；Docker Hub 基础镜像元数据请求超时，未完成镜像构建/容器闭环，不宣称通过 | `20260908T034915Z-docker-4ff8282c/` |
| 档案与边界审计 | PASS；7份报告正文保留（仅迁移链接/增加归档提示）、所有原 docs 外链保留、两份恢复原件与 Git 字节相同、业务源码和 experiments 无 diff、docs/tasks 不再存在 | 本节审计记录与原件 manifest |

最初 offline 因缺 sqlite3 明确 NOT_RUN，最初 browser 因缺 libnspr4 等失败，均在补齐本机依赖后复验通过。首次实际 Docker 上下文检查发现父目录放行导致运行目录进入上下文，修复后复验通过；失败报告保留。完整 Docker 网络失败未通过修改 daemon/WSL 设置绕过；其 smoke 默认清理隔离项目，未残留本次测试容器。

结构检查由 `python3 harness/run.py docs` 执行：维护文档文件链接、入口、原件/SDK 哈希与打包输入静态检查通过；`git diff --check` 通过。结构检查不验证外网 URL 当前可达性或业务数学语义。

本机报告不入 Git；换机只可阅读上述验收摘要，不能假设原始日志仍可用。以下 SHA-256 可用于核对已归档的 result.json（不是整套测试源码的哈希）：

- `20260908T051219Z-offline-0503f7ca/result.json`：`275f782be89a7085cbe98ef361554e3fb0ace42a516d2c25b1b213acc617548e`（PASS）。
- `20260908T051123Z-native-b4f23d6e/result.json`：`5a48b893cd4eab30a307349674dd29f7b5625e55ddda53751da1d6a5a50d968a`（PASS）。
- `20260908T051544Z-browser-1e5f40c3/result.json`：`2218305d2c0fa47ab4a7adbc8abc2fda43b1b49ad9d32e7a2ee32ef5b23ad34e`（PASS）。
- `20260908T051318Z-packaging-d24e397e/result.json`：`2795b464b98ac7111b4462e7c3046e44afa2b7242d15f3e75ff2ca037484aadb`（PASS）。
- `20260908T034915Z-docker-4ff8282c/result.json`：`087e471ad15afaf3fe664e50cdf3791954400cca2a620f09105968ee5864f22f`（FAIL）。

## 原始约束迁移审计

原架构第18节的12项不变量映射如下：独立 CTP/C++/Daily Dataset 闭环及独立测试验收 → 当前架构职责表与边界1；Python/Browser 无采集依赖 → 边界1；C++ 唯一 writer/Python只读 → 边界2/5及 Collector/Read Path 契约；事实与 UI 派生分离 → 职责表及边界2；内存更新再物化 → 边界4及 Collector 契约；TradingDay 生命周期 → 边界3；下游消费不改变 ingestion → 架构数据流；避免预建复杂基础设施/平行架构 → 复用既有模块、SDK/common、按请求计算与无 Derived SQLite 的 MVP 范围。

原短期“先提交 specs、逐 Task commit”流程已去掉；旧单服务/无 Python-JS 部署说明与现有三服务冲突，以已实现的隔离三服务契约替代，没有把 Python 放进 C++ 采集链。MVP 的 Analytics、汇报页、三日实盘、指标对账/性能/真实备份恢复仍明确待实现或待验，见[验收矩阵](../acceptance.md)。
