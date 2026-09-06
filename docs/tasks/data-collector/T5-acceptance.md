# T5 — 可复现验收与操作文档

- 前置：T4 已提交。
- 目标：用户可从 README 独立构建、启动、观察采集、只读检查每日数据。
- 范围：全量 CTest/必要集成验证，真实 CTP 短时探测，README、schema/采样/故障/只读查询手册与验收记录。
- 验证：Debug/Release 构建测试；无 Python/Browser 的 Collector 启动、定时/信号退出；实际前置连接与订阅探测（记录日期/网络/市场状态）；离线持续写入、重启、跨日与历史只读检查；`git diff --check` 与提交顺序审查。
- 实盘限制：如非交易时段或网络阻断，记录缺失证据与交易时段复验命令，不把模拟测试记为实盘验收。
- 完成记录：工程验收完成；实盘验收受外部连接阻断，详见 [验收报告](../../Data_Collector_Acceptance_CN.md)。
  - 最终 Debug 与 Release 全部五项 CTest 通过（config/state/storage/runtime/process）。
  - `BUILD_TESTING=OFF` 生产构建通过，ldd 无缺失依赖；原 demo Debug/Release 构建通过。
  - 真实 CLI + 明确标识的合成 SDK 验证持续写入、两日分区、重连、SIGTERM、定时退出、重复进程拒绝、SIGKILL 后恢复与追加。测试来源同时写入日志和 runs.source。
  - Python 标准库只读连接看到持续提交（2 → 6 行），写入被 SQLITE_READONLY 拒绝；Python 未进入采集链路。
  - 真实 SDK 前置连接/登录 20 秒超时，六个已记录地址的 TCP 探测均被拒绝；不宣称取得真实订阅/行情证据。
  - 完成 README、数据契约、故障说明与交易时段补验命令；文档链接、git diff --check 和 T0–T5 提交顺序审查通过。
  - 验收审查修正：主循环读取轻量登录标志，避免每 20ms 复制完整 universe；正常结束元数据写入失败也输出 persistence_failed。
