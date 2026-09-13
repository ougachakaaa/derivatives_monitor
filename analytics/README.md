# Analytics

Analytics 是 Query 进程内的 Market Indicator 计算源码模块，当前拥有冻结的 MO Skew 数值核心、业务时间选择和审核参考包适配。它只消费 [Data Provider](../data_provider/README.md)，不是独立服务、镜像或调度器。

精确业务行为见 [Skew v1 Contract](contracts/analytics-skew.md)和 [Reference adapter](contracts/references.md)，当前证据见 [Acceptance](ACCEPTANCE.md)。

## 审核参考包的离线导入

从仓库根运行：

```bash
query/.venv/bin/python -m analytics.skew_references /path/to/audited-package --directory /path/to/references/analytics
```

生产代码不依赖独立 oracle。Analytics owner tests 使用现有 Query Python 环境：

```bash
query/.venv/bin/python -m unittest discover -s analytics/tests -t . -v
```
