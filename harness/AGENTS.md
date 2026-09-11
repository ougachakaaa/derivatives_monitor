# Harness Agent 工作协议

本目录继承根 [AGENTS](../AGENTS.md) 与 [documentation governance](../docs/README.md#authority-rules)。进入 Harness 工作时先读本文件和 [README](README.md)；修改结果分类、证据字段、执行/跳过传播或 TEST DOUBLE 边界前必须再读 [Harness Contract](CONTRACT.md)。涉及某个业务模块的测试时，只沿该模块入口读取相应 Contract 与 Acceptance，不把 Harness 实现当作产品行为来源。

## 修改纪律

- `run.py`、检查器与 `harness/tests/` 的变更必须保持 [Contract](CONTRACT.md) 的结果和证据语义；行为确需改变时，同一变更更新 Contract、定向回归及受影响 Acceptance。
- 测试留在其责任模块；不要为了统一入口移动模块测试、改变 import/CMake/Docker 输入或扩大生产依赖。Harness 可以组织测试和记录证据，不能冻结新的业务默认值、容差、错误语义或完成状态。
- `fixtures/analytics-skew-v1.json` 是 Query Skew claim 的受控投影。修改 Analytics 检查前读取 [冻结 Skew Contract](../query/contracts/analytics-skew.md)及[机器策略](../query/contracts/analytics-skew-v1.json)；不得因实现失败重生成 expected、改 oracle、放宽容差或改变 provenance。SDK、originals、golden 和 Docker allowlist 同样保持既有保护。
- 每个合成输入、临时配置和替身服务都显式标记 `TEST DOUBLE`。不得把 TEST DOUBLE、结构检查或单一 profile 的结果登记成真实行情、人工使用、性能、恢复或 MVP 通过。
- 不提交 `artifacts/`、行情、凭据或配置。若提交脱敏证据摘要，只在对应 scope Acceptance 记录版本、环境、数据来源、原始报告身份和仍未覆盖的边界；根 Acceptance 只记录系统级或跨模块门槛。

## 安全验证

- 从 `python3 harness/run.py docs` 开始，再按 [README 的 profile 表](README.md#profiles)选择与改动相称的定向检查；检查日志中的实际测试数、退出码和 skip，不只看命令是否结束。
- 文档与离线回归不读取真实配置或 `collector/data/`，不运行真实 `up`/update/stop，不发送 webhook，不做现场恢复，也不安装或升级依赖。需要依赖的 profile 缺条件时按 Contract 保留 `NOT_RUN`，修复环境后重跑。
- 集成测试只用临时目录、随机 loopback 端口和隔离的 TEST DOUBLE 环境；超时或中断后确认 runner 控制的进程组已退出。Docker 只操作本次专用项目，并按脚本输出核对清理结果。
- 至少运行受影响的 `harness/tests`，并执行 `git diff --check`。authority/checker 改动运行 `python3 -m unittest harness.tests.test_authority -v`；runner/result 改动运行 `python3 -m unittest harness.tests.test_runner -v`；Analytics 基线改动还需按 [README](README.md#analytics-skew-baseline)运行固定的独立 oracle 流程并遵守 Query Skew Contract。
