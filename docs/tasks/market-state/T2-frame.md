# T2 Frame 重建

Spec：单事务、已有索引、received_us/id 排序、revision 上限；point inclusive、minute end exclusive、同 period 隔离；保留全部事实与真实 age，独立 missing/stale/invalid；COMPLETE/PARTIAL/EMPTY；显式 evaluated_at 定义 sealed。错误不返回假空帧。

验证：临时真实 SQLite 单合约与全链、多个 run 平局、最新 invalid 不回退、陈旧/缺失、午休/夜盘、分钟边界、晚物化、固定 revision 追加重放和只读文件不变。
