<a id="verification-evidence-semantics"></a>

# Verification Evidence Semantics

本文只定义 repository verification 的执行结果、证据身份和边界。产品完成条件由 [MVP](mvp.md)定义，当前缺口由 Acceptance 记录，业务行为由相应 Contract 拥有；根 runner 只组织检查并记录证据，不定义或改写这些行为。

## 结果分类与传播

Verification step 和 profile 使用 `PASS`、`FAIL`、`NOT_RUN` 三种终态：

- `PASS`：命令实际执行、退出码为 0，且输出没有报告 skipped、`NOT RUN`、零项 unittest/CTest 或未发现测试。只有 profile 内全部 step 都满足这一条件，profile 才是 `PASS`，进程退出码为 0。
- `FAIL`：已启动命令返回非零，或发生启动/读取错误、断言失败、超时或中断。profile 只要包含一个 `FAIL` 即为 `FAIL`，进程退出码为 1；不得用其他通过项抵消。
- `NOT_RUN`：命令或显式 prerequisite 缺失，或退出 0 的命令仍报告跳过、零项或未执行检查。没有 `FAIL` 但至少一个 `NOT_RUN` 的 profile 为 `NOT_RUN`，进程退出码为 2。

step 未达到 `PASS` 后，依赖其结果的后续 step 不再启动并明确记录 `NOT_RUN`。各 profile 彼此独立：一个 profile 的 `PASS` 不推导其他 profile 已运行或通过；修复依赖或环境后必须重跑需要证明的 profile。Docker 基础镜像不可达时，单独通过 `packaging` 也不能替代 `docker`。

超时和中断是 `FAIL`，runner 终止其启动的进程组并保留已有日志；这只保证 runner 控制范围内的清理。Docker 场景由相应脚本负责本次隔离项目资源，失败时按日志核对，不得操作正式项目。

## TEST DOUBLE 与证据强度

合成行情、fixture、替身 SDK/服务、临时配置和模拟仓库必须在数据或场景中明确标记 `TEST DOUBLE` 或 `SYNTHETIC`。这类结果只能证明其明确覆盖的工程机制，不等同于真实 CTP、官方参考包、完整 MO 月链、生产调度周期、人工可用性、性能或恢复。

`docs` 结果属于 `STRUCTURAL`，只证明当次确定性结构检查；其他自动 profile 记为 `OFFLINE_OR_SYNTHETIC`。自动报告的 `mvp_complete` 固定为 `false`。任何自动 `PASS` 都不能关闭现场门槛，也不能把模块局部证据提升成系统完成；实际覆盖与缺口由对应 scope Acceptance 记录，系统 G1–G6/P1/P2 只由[根 Acceptance](acceptance.md)汇总。

## 证据身份与可复现性边界

每次 profile 创建独立的 `artifacts/verification/<UTC>-<profile>-<id>/`。`result.json` 以 profile、UTC 开始时间、Git `HEAD`、工作树状态、平台、Python 版本、证据种类和 step 列表标识该次运行；已执行 step 记录命令、工作目录、超时、退出码、时长、日志文件及日志 SHA-256。报告持续写入，最终才成为上述三种终态之一。

同目录的 `worktree.patch` 与 SHA-256 保存除 `experiments/` 外的 tracked working-tree diff，`result.json` 另记录未跟踪且未被 Git ignore 的文件哈希。Runner 不复制配置、运行数据或凭据。报告只证明该身份所指版本、dirty state、环境和实际 step；历史报告不自动证明当前 HEAD 或另一环境。

`result.json` 不是完整环境快照。归档 dirty-tree 结果时必须同时保留可取得的对应源码 revision、patch 和未跟踪输入；缺少这些输入就不能宣称可复现。对外提供的证据摘要须脱敏，保留数据来源、版本（Git revision 与工作树状态）、profile/命令、结论及未覆盖边界；不提交 verification artifacts、行情或配置。`artifacts/` 不随仓库分发，长期文档只保留当前状态与缺口，不累计上述运行身份或文件系统路径；需要原始报告时在保存该报告的机器上按身份定位。

## 现场证据边界

真实行情、人工使用、独立对账、性能与恢复证据不属于自动 profile。它们使用[现场记录模板](live-acceptance-template.md)保存在持久证据目录，由相应 Acceptance 按产品门槛审查。未执行、跳过、缺依赖、缺原始报告身份或缺少仍可复查的输入，均不得写成已验证或 `PASS`。
