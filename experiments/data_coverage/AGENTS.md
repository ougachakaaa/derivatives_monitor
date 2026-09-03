# Data Coverage Experiment Rules

本文件适用于 `experiments/data_coverage/` 及所有子目录。

## 工作顺序

1. Coverage first：先确认目标数据能否发现和获取，再讨论生产设计。
2. 修改某类数据前，只读取根文档、该数据类型的 `SPEC.md` 和目标数据源的 `REFERENCE.md`、`coverage.md`。
3. 不要为单类 Probe 加载其他数据类型或其他数据源的 Reference，除非正在调查明确的交叉问题。
4. 先保存 raw / near-raw evidence，再解析、总结或规范化。
5. 已有成功 Probe 时，检查本地最新成功 sample 与当前 response template 是否匹配。

## 证据规则

- 按请求实际返回的内容保存真实响应体，不预设文本、JSON、JSONP、字段层级、文件扩展名或目录组织。
- raw response 保留来源字节和来源编码；如果 raw 不是 UTF-8，应另存 UTF-8 可读副本，且不得用副本替换原始证据。
- 同时记录足以复核请求的 endpoint、非敏感参数、接收时间、HTTP 状态，以及实际分析需要的传输信息；记录方式不作统一格式要求。
- 不要提交 cookie、token、账号、完整本机路径或其他秘密。
- 不要用手工字段表代替原始样板；字段表只能作为补充说明。
- 一次请求失败不能判定 `UNSUPPORTED`。记录失败条件，并在合理的不同时间或经确认的替代 endpoint 上复试。
- 不得把 HTTP 200 等同于数据完整，也不得把 Reference 中记录的字段、结构或 wrapper 行为当作实测事实或验收格式。

## Sample 与 Template 生命周期

- 时间戳 `samples/<run>/` 是本地原始证据。Probe 已证明可运行后，这些 run 目录应由 `.gitignore` 排除；不得为了提交而删除仍需复核的本地样本。
- 普通审阅或文档任务发现本地 sample 缺失时，只报告 `NO_SAMPLE`，不得自行发起网络请求。只有明确的 Probe 或 refresh 任务可以按局部 Reference 重新生成 sample。
- 成功样本应生成或验证可提交的版本化 response template。模板是带占位符、语义解释和置信度的离线说明，不是 production schema，也不能替代 raw evidence。
- 每个模板版本必须带来源 run ID、raw hash、结构指纹和语义指纹。无法确认的位置标记为 `UNKNOWN` 或低置信度，不得从历史惯例推断为实测事实。
- 行情数值、日期、时间、响应长度或 raw hash 的正常变化不升级模板版本，只追加 validation 记录。
- wrapper、分隔方式、逻辑字段结构、位置类型模式或目标 identifier 映射发生变化时，创建下一版本，并在 changelog 中说明与上一版的差异。
- 已发布版本目录保持不可变；当前版本由独立指针标识。不得用新样本静默覆盖旧版本。

## 范围边界

- 本区域可以包含实验性 Probe Code、原始样板、覆盖矩阵和简短报告。
- 不在这里设计或实现 production provider abstraction、数据库、实时采集循环、监控规则或告警。
- 实时延迟、稳定性、轮询频率、反爬策略、broker 对比和 CloudBase 网络验证属于后续实验，不是本轮 Coverage 完成条件。
- 尊重数据源访问限制；不得绕过认证、访问控制、验证码或反自动化措施。

## 修改完成条件

每次完成一个数据源 Probe 后，检查：Probe 可重跑、本地 raw 与 metadata 一致、当前 template 与最新成功样本匹配、coverage 链接持久化模板、report 说明限制，且没有把参考线索或实验性解析写成来源格式承诺。
