# T3 — Daily SQLite

- 前置：T2 已提交。
- 目标：离线 snapshot 能写入正确交易日并独立只读消费，同日重启安全追加。
- 范围：schema v1、日元数据、run 记录、事实表与查询索引；单 writer 锁、WAL/FULL、prepared statements、逐日事务、失败传播。
- 非目标：不增加 Python 服务、不做 schema 自动迁移。
- 验证：两日文件分离、全部事实字段、NULL、同日重开追加、同批重放去重、错日/未知 schema 拒绝；事务中途失败不部分提交、写锁冲突、只读连接看到连续提交且不能写、关闭后完整性检查。
- 完成记录：待执行。
