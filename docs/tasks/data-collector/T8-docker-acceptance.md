# T8 — 部署验收与 WSL 手册

- 前置：T7 已提交。
- 目标：脚本行为有自动化证据，目标机器可执行容器验收和真实采集。
- 产物：隔离 Docker smoke test、补充脚本测试、README 与验收记录。
- 验证：镜像内五项 CTest；合成 SDK 驱动容器持续写入/日切；SIGTERM 尾部提交、重建/重启追加、只读验收；启动超时自动恢复与手动 stop；最终镜像无测试库或秘密；脚本无 Docker 时明确诊断。
- 限制：真实前置不可用不阻止脚本交付；Docker 不可用时明确标注容器测试待目标机运行，不记为已通过。
- 完成记录：已交付隔离 Docker smoke test、WSL 一键操作手册和 [部署验收记录](../../Data_Collector_Docker_Acceptance_CN.md)。三份 shell 脚本语法/ShellCheck 通过，真实 Compose v2.24.6 配置解析及关键设置断言通过；8 项部署脚本测试、4 项真实 SQLite CLI 测试和既有 5 项 Release CTest 全部通过。Docker Engine 仍因 WSL 集成未启用而不可用，smoke test 明确输出 NOT RUN 并非零退出；镜像内构建/测试、真实挂载及容器重启实测尚待目标机器执行，未记为通过。新增 LF 属性保证 WSL shell 脚本 checkout 可执行，并检查文档链接和 diff 格式。
