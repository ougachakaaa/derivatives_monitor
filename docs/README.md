# 文档入口

- 系统：[Architecture](../ARCHITECTURE.md) · [Design](../DESIGN.md) · [产品边界](mvp.md) · [当前状态](acceptance.md)
- 运行：[Operations](operations.md) · [安全回归](../harness/README.md)
- 共享 Contracts：[Raw](contracts/raw-boundary.md) · [HTTP](contracts/read-path.md) · [Calendar / Universe](contracts/market-session.md) · [Feature](contracts/features.md) · [Deployment](contracts/deployment.md) · [Developer runner](contracts/developer-runner.md)

| 模块 | 使用入口 | 修改时读取 |
|---|---|---|
| Collector | [README](../collector/README.md) | [Contract](../collector/CONTRACT.md)、[工具 Contract](../collector/scripts/CONTRACT.md) |
| Query | [README](../query/README.md) | [Contract](../query/CONTRACT.md)、[Market State](../query/contracts/market-state.md)、[Skew](../query/contracts/analytics-skew.md)、[参考适配](../query/contracts/references.md) |
| Dashboard | [README](../dashboard/README.md) | [Contract](../dashboard/CONTRACT.md) |
| Monitoring（尚未实现） | [README](../monitoring/README.md) | [Contract](../monitoring/CONTRACT.md) |
