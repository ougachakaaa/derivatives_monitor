# derivatives_monitor

本地衍生品监控项目：独立 C++ 采集并保存市场事实，Python 只读解释，React 展示。MVP 目标是一个 MO 到期月的可信 Skew 观察与分钟回看。

**当前已实现采集、只读诊断、市场日历和 Market State；[Analytics / Skew 七项契约](docs/contracts/analytics-skew.md)已冻结，计算与汇报首页待实现，MVP 尚未收尾。**

```text
CTP → C++ Collector → 按源 TradingDay 的 SQLite
                                  ↓ 只读
                          Python Market State
                                  ↓ 待实现
                             IV / Skew → JSON → React 汇报页
```

Collector 无需 Python 或浏览器运行；现有 FastAPI 和 React 已能展示采集诊断。默认每15秒物化有更新的合约，保存 sampled snapshot，不声称逐 tick 无损。

从[文档入口](docs/README.md)阅读 [MVP 范围](docs/mvp.md)、[系统架构](docs/architecture.md)、[长期契约](docs/contracts/collector.md)和[验收矩阵](docs/acceptance.md)。AI agent 的工作入口是 [AGENTS.md](AGENTS.md)。

- [运行与恢复](docs/operations.md)：部署、检查、清单/日历更新、备份恢复。
- [Collector](collector/README.md)、[Query](query/README.md)、[Dashboard](dashboard/README.md)：模块用法与构建命令。
- [Harness](harness/README.md)：`python3 harness/run.py docs` 检查文档/来源/打包输入；按改动选择工程 profile。测试证据不替代真实运行验收。
- [外部参考档案](docs/references/README.md)：中信建投咨询和回复原件、SDK 下载入口/版本/哈希、交易所来源。
- [历史验收](docs/archive/README.md)：日期化证据，不作为当前状态保证。

完成各模块依赖准备并保留有效配置后，原生 WSL 入口为 `./collector/scripts/native.sh up`；Docker Engine + Compose v2 环境为 `./collector/scripts/deploy.sh up`，该兼容入口读取仓库根的 `compose.yaml`。默认看板 **http://localhost:8101**。两种方式不要同时写同一目录。数据保持在宿主 `collector/data/`，升级镜像不删除历史数据。

`experiments/` 原位保留：[CTP 接入实验](experiments/ctp/README.md)、[数据覆盖实验](experiments/data_coverage/README.md)。正式 Collector 的 SDK、公共头和构建适配归 `collector/` 所有，不依赖实验目录；实验客户端可以依赖正式模块。
