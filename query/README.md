# 只读查询后端

FastAPI + Uvicorn；Python 3.12，Poetry 2.2.1 管理独立环境与 `poetry.lock`。只提供 JSON/OpenAPI，不提供 React 或其他静态资源。

从本目录开发运行（先安装 Python 3.12 和 Poetry）：

```bash
poetry config virtualenvs.in-project true --local
poetry sync
DATA_DIR=../collector/data poetry run uvicorn app:app --host 127.0.0.1 --port 8000
```

验证：`poetry run python -m unittest discover -s tests -v`。Docker 构建使用相同锁文件、执行测试，最终镜像仅安装 main 依赖；Docker 部署无需宿主安装 Python/Poetry。

| 请求 | 内容 |
|---|---|
| `/healthz` | API 自身存活，不取决于行情 |
| `/api/health` | 共享目录、Collector 主循环心跳和 CTP 状态 |
| `/api/days` | 日文件列表；size_bytes = 主文件 + WAL，非逻辑数据大小 |
| `/api/summary?day=20260904` | 精确行数、逐合约数量与最近接收时间、最近 100 个 run 来源 |
| `/api/snapshots?day=20260904&instrument=IF2609&limit=50` | 最近 snapshot，instrument 可省略，limit 1–200 |
| `/docs` | FastAPI 交互接口文档 |

时间字段是 Unix 微秒。采样行数不等于原始 tick 数；`accepted` 是本次 Collector 接收计数，`written` 是本次写入计数，日行数跨 run 累计。查询错误返回 JSON `error`：400 参数错误、404 日文件缺失、503 数据暂不可读/不兼容/超时。查询有 1 秒 busy timeout、3 秒执行预算；大库精确统计若超时，页面应显示错误，不把旧值当新值。

持久目录沿用宿主 `collector/data/`。后端容器同 UID **只读**挂载 `/data`；SQLite URI `mode=ro` 和 `query_only=ON`。活跃 WAL 数据库使用已有 WAL/SHM。离线数据库无 WAL 时，只有获得 `.collector.lock` 共享锁才使用 immutable；持锁到查询结束。Collector 活跃但历史日缺 sidecar 时返回 503，可正常停止 Collector 后读取，不删除 WAL，也不允许后端写入目录。

Collector 无依赖本服务。心跳缺失、过期或损坏为 unknown/stale；休市无行情不会单独让健康状态变红。页面观察应用状态，Docker 进程状态由部署脚本 `status` 查看。
