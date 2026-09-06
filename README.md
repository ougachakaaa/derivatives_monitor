# derivatives_monitor

衍生品监控项目。第一阶段提供独立的 Linux C++ 行情采集器：

```text
CTP → C++ Data Collector → YYYYMMDD.sqlite
```

采集、内存状态、snapshot 与按交易日写入均在 C++ 进程内完成，无需启动 Python 或 Browser。下游通过 SQLite 只读访问市场事实。

- [构建、运行与只读查询](collector/README.md)
- [FastAPI / Poetry 只读后端](query/README.md) · [独立 React 看板](dashboard/README.md)
- [读路径约束](docs/Read_Path_Constraints_CN.md) · [读路径验收](docs/Read_Path_Acceptance_CN.md)
- [设计约束](docs/Data_Collector_Constraints_CN.md)
- [分步 Task Specs 与验证记录](docs/tasks/data-collector/README.md)
- [第一阶段验收结果](docs/Data_Collector_Acceptance_CN.md)：离线闭环已验证；本次真实前置连接被拒，实盘持续行情仍待交易时段复验。

另一台 Linux x86-64 / WSL 机器已有 Docker Engine + Compose v2 时，可直接部署：

```bash
./collector/scripts/deploy.sh up
```

首次交互填写前置、必要账号和精确合约，随后自动构建、测试并后台启动 Collector、FastAPI 与 React/Nginx 三个独立容器；后续复用本地配置。数据保存在宿主 `collector/data/`，重建容器不会清除。打开 **http://localhost:8080** 查看状态和数据量，**http://localhost:8000/docs** 查看 API。SQLite 同一宿主目录以 RW 挂载给 C++、RO 挂载给 Python；前端没有数据挂载。查看日志用 `./collector/scripts/deploy.sh logs`，正常停止用 `./collector/scripts/deploy.sh stop`。详见 [Docker / WSL 手册](collector/README.md#docker--wsl-一条命令部署) 和 [Docker 验证边界](docs/Data_Collector_Docker_Acceptance_CN.md)。

在仓库根目录构建（需要 CMake、G++、SQLite 开发包）：

```bash
cmake -S collector -B collector/build/Release -DCMAKE_BUILD_TYPE=Release
cmake --build collector/build/Release -j
ctest --test-dir collector/build/Release --output-on-failure
cp collector/config.example.ini collector/config.ini
```

填写 `collector/config.ini` 中的前置、必要凭据和精确合约列表后运行：

```bash
collector/build/Release/bin/data_collector --config collector/config.ini
```

## Experiments

- [Market Data Coverage Harness](experiments/data_coverage/README.md)：按“数据类型 → 数据源”验证行情覆盖并保存原始证据。
- [CTP Linux C++ 行情客户端](experiments/ctp/README.md)：使用官方 Linux x64 SDK 原生构建、连接行情前置并手工订阅合约。
