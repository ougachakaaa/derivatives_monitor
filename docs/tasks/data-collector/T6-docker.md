# T6 — Docker 镜像与 Compose

- 前置：部署约束及 T6–T8 Specs 已提交。
- 目标：Collector 可通过多阶段镜像构建，Compose 定义数据持久化和独立运行边界。
- 产物：Dockerfile、构建上下文忽略规则、单服务 Compose。
- 验证：构建阶段强制运行五项 CTest；最终依赖/产物检查；Compose 配置、UID/GID、只读配置/数据目录挂载、restart/信号/日志设置审查；上下文不包含本地秘密或运行数据。
- 容器限制：本机 Docker 若仍不可用，记录未实测，T8 提供目标机测试入口；不得伪称镜像构建通过。
- 完成记录：待执行。
