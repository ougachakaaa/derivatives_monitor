# Collector 默认 15 秒 Snapshot 验收记录

> 历史验收快照：仅证明文中日期/版本/环境下的观察。旧端口、临时路径、待验状态和操作命令可能已过时；当前设计见[文档入口](../../README.md)，当前门槛见[验收矩阵](../../acceptance.md)，运行见[操作说明](../../operations.md)。原始日志缺失时仅作为历史摘要。


日期：2026-09-07（Asia/Shanghai）。本记录只描述此次默认持久化间隔演进，不替代此前真实 CTP 验收记录。

## 变更与兼容性

- C++ 配置默认值、示例 INI、首次部署生成值统一为 `SnapshotIntervalMs=15000`。显式配置仍优先，范围仍为 1–60000ms；已有配置不会被部署脚本覆盖。
- callback、内存状态、runtime 调度、CTP session、SQLite 存储算法均未修改。每个有效 callback 持续覆盖对应 `(TradingDay, InstrumentID)` 的最新状态；物化只复制 dirty 状态，在释放状态锁后执行 SQLite I/O。
- 启动单调时间加间隔决定首次截止；每次物化与写入完成后重新等待配置间隔。约 15 秒窗口不对齐自然时钟，不补发错过的窗口，不平均价格，不 forward-fill。跨交易日分别保存；正常停止提前提交最后一个不完整窗口。
- schema 仍为 v1。源时间、`received_us`、`snapshot_us`、`sequence` 保持原语义；每个 run 记录实际 `snapshot_interval_ms`。同日 1 秒与 15 秒 run 可以追加共存，不迁移或重采旧数据。
- 单 writer、TradingDay 分区、WAL、FULL 同步提交、故障明确失败及已提交数据恢复语义保持不变。窗口延长意味着崩溃时可能丢失更长时间的未提交状态；慢写入还可能延长该时间。

## 离线验证

Release 构建成功；以下使用临时合成数据，不连接真实 CTP，不写入实际采集数据目录。

| 验证 | 结果与证据 |
|---|---|
| CTest | 七项均通过：config、state、storage、runtime、snapshot_interval、health、process。首次 config 夹具缺少必填 FrontMdAddr，补齐后单独重跑通过；其余六项在全套运行中通过。 |
| 配置 | 默认构造、缺省 INI、示例为 15000；1、50、1000、15000、60000 显式值保留；0、负数、超范围、非整数拒绝。 |
| 状态 | 多合约、多个 15 秒逻辑窗口；逐一比较最新 snapshot 的全部 46 个源字段；连续空窗口无记录；内容相同的新 callback 仍有新 sequence；源时间回退不覆盖接收顺序语义；原有并发 10000 次更新和日切保护通过。 |
| 实际 15 秒调度 | 独立测试 API 驱动真实 runtime 约 33 秒。3 秒时 accepted=1；4、8 秒各接收新更新；12 秒时 accepted=3 且尚无日库；18 秒时只有 sequence=3、Volume=42 的最新状态；32 秒时仍只有一行；停止前测试 API 发出 Volume=99，尾部提交后共两行且 run 正常结束。 |
| 存储兼容 | 同日从 1000 改为 15000 重启追加，两个 run 的间隔元数据准确、四条旧新 snapshot 均保留原时间字段、schema v1；WAL、只读消费、事务失败、writer 锁和完整性回归通过。 |
| 生命周期 | 原有短间隔 runtime/process 测试通过：连接、登录、重连及重新订阅、超时与失败、SIGTERM 尾部、SIGKILL 已提交数据恢复与重启追加。 |
| 部署脚本 | 9 项通过，包括首次配置生成 15000、显式旧 1000 配置原样复用。使用 Docker CLI double，不代表真实容器。 |
| 只读验收器 | 4 项通过，实际 SQLite CLI 读取运行中 WAL、停止后数据库及错误场景。 |
| Query | 8 项通过，包括只读 WAL、后续提交可见、心跳及无行情状态。 |
| Dashboard | 4 项通过，生产构建通过。 |
| 原生读路径与浏览器 | `read_path_smoke.py --browser` 通过：实际 C++ → SQLite → FastAPI HTTP、各进程独立停止与重启、持久计数、SIGKILL 后心跳过期；Chromium 页面渲染、实际行数、网络失败与恢复、移动布局均通过。现有集成脚本显式使用 100ms 以缩短生命周期场景，默认 15 秒由独立 runtime 测试覆盖。 |

本机原 CMake 缓存指向的 SQLite 开发包临时目录已缺失，重新下载并解压至 `/tmp/dm-sqlite-dev/root` 后完成构建及 SQLite CLI 验证。Chromium 缺少的 NSPR/NSS/ALSA 库解压至该临时目录的 `browser` 子目录，仅对集成测试设置 `LD_LIBRARY_PATH`；没有增加 Collector 运行依赖。

可复现命令（在仓库根目录，Query、Dashboard 依赖已安装）：

```bash
cmake -S collector -B collector/build/Release -DCMAKE_BUILD_TYPE=Release
cmake --build collector/build/Release -j 4
ctest --test-dir collector/build/Release --output-on-failure -j 4
python3 collector/tests/deploy_test.py
PATH=/tmp/dm-sqlite-dev/root/usr/bin:$PATH python3 collector/tests/verify_test.py
(cd query && .venv/bin/python -m unittest discover -s tests -v)
(cd dashboard && npm test && npm run build)
LD_LIBRARY_PATH=/tmp/dm-sqlite-dev/browser/usr/lib/x86_64-linux-gnu python3 tests/read_path_smoke.py --browser
```

系统已安装 SQLite 开发包/CLI、Chromium 所需库时无需上述临时路径；新配置 CMake 时根据本机安装位置指定 SQLite include/library。

## 未完成的现场验收

- Docker：当前 WSL 无法使用 Engine/Compose；`collector/tests/docker_smoke.sh` 和 `tests/read_path_docker_smoke.sh` 均在环境预检阶段明确报告 NOT RUN。未更新或重启实际容器。
- 真实 CTP：工作区没有 `collector/config.ini`，此次执行时间约 23:00，未进行实盘订阅、日切、重连或数据库增长对比。离线结果不证明当前真实接收速率或真实磁盘增长比。

## 已有部署切换及增长对比

1. 在有效的现有部署上，先选择相同活跃合约及至少 10 分钟稳定区间记录 1 秒基线。保存 run ID、起止 UTC 微秒、逐合约接收计数和 snapshot 数、主 SQLite 加 WAL 大小及运行日志；排除启动、停机、断线及无行情区间。
2. 将实际配置显式改为 `SnapshotIntervalMs=15000`，正常停止旧 Collector 后更新启动，沿用原数据目录。Docker 部署可使用原 checkout 的 `deploy.sh stop`、`deploy.sh up`；显式旧 1000 不会因升级自动切换。
3. 检查新启动日志 `snapshot_interval_ms=15000` 和新 `runs.snapshot_interval_ms`，逐合约订阅成功、`session_received/accepted` 及最近接收时间持续推进；约每 15 秒出现提交，2 秒主循环心跳保持新鲜。切换不会改变 CTP 推送频率。
4. 再取至少 10 分钟可比稳定区间，以相同口径记录。下列只读查询分别绑定对应 run 和起止时间，按物化时间统计，避免把旧行情接收时间混入窗口：

   ```sql
   SELECT InstrumentID, COUNT(*) AS rows,
          COUNT(*) * 60000000.0 / (:end_us - :start_us) AS rows_per_minute
   FROM snapshots
   WHERE run_id = :run_id AND snapshot_us >= :start_us AND snapshot_us < :end_us
   GROUP BY InstrumentID;
   ```

5. 持续活跃合约理论上从约 60 行/分钟降至约 4 行/分钟；按相同合约比较行数比及每秒接收数。稀疏行情不要求达到 1/15。主文件与 WAL 的字节增长同时记录，受页面分配、checkpoint 和固定元数据影响，不要求精确 1/15，也不能用 WAL 回收导致的瞬时缩小证明采样效果。
6. 抽查源 `UpdateTime/UpdateMillisec`、`ActionDay`、`received_us`、`snapshot_us`；没有新 callback 的区间不得产生新记录。确认 Query/Dashboard 可见新提交，正常停止后历史数据可读、重启同日追加。写入测试结论时区分已实测、理论预期和待验项目。
