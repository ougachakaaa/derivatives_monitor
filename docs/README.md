# 文档入口

- 系统：[Architecture](../ARCHITECTURE.md) · [Design](../DESIGN.md) · [产品边界](mvp.md) · [当前状态](acceptance.md)
- 运行：[Operations](operations.md) · [安全回归](../tests/README.md) · [证据语义](verification.md)
- 共享 Contracts：[Raw](contracts/raw-boundary.md) · [HTTP](contracts/read-path.md) · [Calendar / Universe](contracts/market-session.md) · [Market Indicator](contracts/indicators.md) · [Deployment](contracts/deployment.md) · [Developer runner](contracts/developer-runner.md)

| 模块 | 使用入口 | 修改时读取 |
|---|---|---|
| Collector | [README](../collector/README.md) | [Contract](../collector/CONTRACT.md)、[工具 Contract](../collector/scripts/CONTRACT.md) |
| Data Provider | [README](../data_provider/README.md) | [Contract](../data_provider/CONTRACT.md)、[Market Frame](../data_provider/contracts/market-frame.md)、[Market Session](contracts/market-session.md) |
| Analytics | [README](../analytics/README.md) | [Contract](../analytics/CONTRACT.md)、[Skew](../analytics/contracts/analytics-skew.md)、[参考适配](../analytics/contracts/references.md) |
| Query | [README](../query/README.md) | [Contract](../query/CONTRACT.md) |
| Dashboard | [README](../dashboard/README.md) | [Contract](../dashboard/CONTRACT.md) |
