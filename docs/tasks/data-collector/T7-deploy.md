# T7 — 一键部署及运维入口

- 前置：T6 已提交。
- 目标：首次交互后，一条命令完成构建到后台启动；提供 logs/status/stop/verify。
- 产物：Bash 部署脚本与容器只读验收脚本。
- 验证：非交互缺配置失败、首次配置/密码保护、已有配置不覆盖、不执行 INI、路径/RunSeconds 限制、Docker/Compose/架构检查、失败不触碰已有容器、权限检查、重复 up、只读验收失败码。
- 非目标：不改 C++ CLI/schema，不自动重写配置或修复宿主 Docker。
- 完成记录：Bash/POSIX 语法与 ShellCheck 通过；8 项 Docker CLI 替身测试通过（含真实 PTY 密码隐藏、0600、路径空格、配置不执行/不覆盖、更新前预检、失败保留原实例）；4 项真实 SQLite CLI 验收测试通过（活跃 WAL、停机无 sidecar、错日/空库/未知 schema/坏外键/损坏文件）。发现并解决停机 WAL 只读挂载问题：仅取得 Collector 共享目录锁且无非空 WAL 时使用 immutable；活跃写者仍读取 WAL。目标机 Docker 实测留待 T8，当前 status 可明确诊断 WSL Docker 不可用。
