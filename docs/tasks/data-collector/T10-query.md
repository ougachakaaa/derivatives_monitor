# T10 — Python 最小只读 HTTP 服务

- 前置：T9 已提交。
- 目标：独立 Python 服务接受基本查询，读取既有 Collector 数据和状态。
- 范围：标准库 HTTP/SQLite，healthz、health、days、summary、snapshots；参数绑定/limit/日期校验；读事务与有界查询；独立 Dockerfile。
- 验证：真实 SQLite 的全部接口和错误码、活跃 WAL 最新提交、停止后历史读取、写操作拒绝、无数据/错日/schema/损坏/心跳过期、服务独立运行；不修改持久文件。
- 完成记录：待执行。
