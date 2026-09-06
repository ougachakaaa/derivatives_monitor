# T10 — Python 最小只读 HTTP 服务

- 前置：T9 已提交。
- 目标：独立 Python 服务接受基本查询，读取既有 Collector 数据和状态。
- 范围：FastAPI/Uvicorn HTTP、标准库 SQLite、Poetry pyproject/lock，healthz、health、days、summary、snapshots；参数绑定/limit/日期校验；读事务与有界查询；独立 Dockerfile；不托管前端资源。
- 验证：真实 SQLite 的全部接口和错误码、活跃 WAL 最新提交、停止后历史读取、写操作拒绝、无数据/错日/schema/损坏/心跳过期、服务独立运行；不修改持久文件。
- 完成记录：FastAPI/Poetry 独立项目和 JSON 接口完成；8 项真实 SQLite/API 测试通过，包括只读权限目录、活跃 WAL 的追加提交、离线共享锁、坏参数/错日/损坏/空库、心跳过期和独立存活。Poetry lock/sync 成功；镜像内同样执行该测试集。当前 Docker Engine 不可用，镜像实测留待目标机，未记为通过。
