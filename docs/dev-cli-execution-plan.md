# 行情接入与启动命令语义调整

本次为已有 runner 的有限接口调整。设计/harness 准备完成后，按 A → B → C 各提交一个 commit。当前状态唯一见 [Acceptance](acceptance.md#行情接入与启动命令语义调整)，不复用上一轮完成结论。本计划不规定执行模型或工具模式。

## 阅读与 authority

先读 [AGENTS](../AGENTS.md)、[文档入口](README.md)，运行 `python3 harness/run.py docs`。再读 [MVP](mvp.md#行情接入能力边界)、[Collector Contract](contracts/collector.md#行情接入与可选账号字段)、[Deployment Contract](contracts/deployment.md)及 [Acceptance](acceptance.md)。操作文档在迁移完成前展示旧入口，不能用旧示例覆盖新契约。

MVP 决定只接 MdApi、不接 TradeApi/TraderApi 的能力范围；Collector Contract 决定可选字段和协议行为；Deployment 决定 doctor 与 CLI。保留行情登录、已有字段长度校验、Raw ownership、信号/停止/故障隔离以及 native/Docker 语义。不修改真实 config.ini，不添加交易 API，不自动认证或联网诊断。

## 锁定接口

| 命令 | 行为 |
|---|---|
| `./dev up` | 联合启动；保留 --config、--query-port、--dashboard-port 及环境冲突规则 |
| `./dev up collector` | 单 Collector；仅 --config |
| `./dev up query` | 单 Query；--data-dir、--query-port |
| `./dev up dashboard` | 单 Dashboard；--dashboard-port，代理通过 QUERY_URL |
| `./dev doctor [component]` | 原接口保持；不诊断 UserID/Password 是否填写 |

选项放在组件之后；联合选项跟在 up 后。旧顶层三个启动命令拒绝并返回 2，输出对应 `./dev up <component>` 提示；即使附带 --help 也给迁移提示。新各层 --help 无副作用。不给旧命令兼容别名，不增加 up all、多组件列表、后台 stop/restart。执行默认 up 联合启动的既有实现，不改变它的含义。复用现有监督器，不为命令迁移重构进程管理。

## Commit 与验收

| 任务 | 工作 | 完成条件 |
|---|---|---|
| A `test(dev): enforce optional market-data credentials` | 核对现有 doctor 与配置校验，补必要回归；只在确有偏差时最小修正。测试缺省、空值、普通已填 TEST DOUBLE 值均无账号诊断项；保留过长字段整体校验失败及脱敏 | `--scope credentials` 通过；必要定向回归通过；无 TradeApi、无网络、无真实配置写入。当前已允许空值，不为了产生 production diff 重写代码 |
| B `feat(dev): group component starts under up` | 迁移 CLI parser/dispatch，更新现有参数测试、监督器测试调用和实际 smoke 调用；复用数据/代理与进程逻辑。将显式新语义验收接入现有 offline | `--scope all` 通过，旧命令返回 2 且不启动；各层 help、参数边界、单组件和联合行为测试通过；offline 的隔离实际闭环通过 |
| C `docs: publish grouped startup commands` | 更新根/模块 README、Operations、Harness 的真实命令示例；Acceptance 记录新证据；完成后移除本活动计划及导航 | 文档、help、实际调用一致；docs 与 diff 检查通过；不重做业务或 Docker runtime 验收，不签收 MVP |

每任务完成提交后停止；不合并跨任务变更。A 的测试应覆盖实际配置校验而不只模拟“校验成功”。B 修改 harness smoke 中旧调用是必要范围，不能遗留让 offline 仍只验证旧接口。C 允许修正 CLI 帮助文案及对应既有测试这一小类收尾缺陷；若改变参数/运行行为则停止并交回 B，避免纯文档任务因一行文案再次阻断。

## Harness 与证据

本次新增 [显式语义验收](../harness/check_dev_semantics.py)：`python3 harness/check_dev_semantics.py --scope credentials|cli|all`。凭据检查使用临时 TEST DOUBLE 配置运行 doctor，不启动采集；CLI 检查仅 help 和旧入口拒绝，不启动服务。缺 Collector 构建、入口无法执行或命令超时返回 NOT_RUN（2），断言不满足返回 FAIL（1），执行通过返回 0。当前 CLI 尚未迁移，cli/all 失败必须登记为待实现，不能跳过后声称通过；在 B 完成前不接入默认 offline，不破坏已有基线。此检查是基础验收，不能替代 A 的非空/过长字段测试或 B 的实际启动 smoke。

准备阶段运行 docs、显式检查两种 scope、git diff --check；记录实际结果。A 跑凭据及定向测试，B 跑全部显式检查、runner 测试及 offline，C 跑文档与必要 help 检查。所有行情均 TEST DOUBLE；不操作正式 systemd/Docker，不读取真实配置、不对真实前置验收。未执行不得计通过。

## 停止条件

若需要移除 MdApi 登录、改变已有凭据传递或字段安全校验、修改 Raw/分析、接管部署或扩展进程管理，则停止相关实现并回到对应 authority 决策。匿名行情是否被某个真实前置允许不由 doctor 判断，不将网络拒绝转换成必填账号提示。本轮不改变产品业务闭环，也不扩展真实市场验收范围。
