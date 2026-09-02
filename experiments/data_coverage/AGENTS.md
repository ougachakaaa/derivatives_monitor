# Data Coverage Experiment Rules

本文件适用于 `experiments/data_coverage/` 及所有子目录。

## 工作顺序

1. Coverage first：先确认目标数据能否发现和获取，再讨论生产设计。
2. 修改某类数据前，只读取根文档、该数据类型文档和目标数据源文档。
3. 不要为单类 Probe 加载其他数据类型或其他数据源的 Reference，除非正在调查明确的交叉问题。
4. 先保存 raw / near-raw evidence，再解析、总结或规范化。

## 证据规则

- 保存真实响应体；文本响应应保留原编码信息，JSON 响应应优先保留原始 JSON。
- 同时记录足以复现请求的 endpoint、非敏感参数、接收时间、HTTP 状态和必要响应头。
- 不要提交 cookie、token、账号、完整本机路径或其他秘密。
- 不要用手工字段表代替原始样板；字段表只能作为补充说明。
- 一次请求失败不能判定 `UNSUPPORTED`。记录失败条件，并在合理的不同时间或经确认的替代 endpoint 上复试。
- 不得把 HTTP 200 等同于数据完整，也不得把 Reference 中的预期字段当作实测事实。

## 范围边界

- 本区域可以包含实验性 Probe Code、原始样板、覆盖矩阵和简短报告。
- 不在这里设计或实现 production provider abstraction、数据库、实时采集循环、监控规则或告警。
- 实时延迟、稳定性、轮询频率、反爬策略、broker 对比和 CloudBase 网络验证属于后续实验，不是本轮 Coverage 完成条件。
- 尊重数据源访问限制；不得绕过认证、访问控制、验证码或反自动化措施。

## 修改完成条件

每次完成一个数据源 Probe 后，检查：Probe 可重跑、样板可离线阅读、coverage 有证据链接、report 说明限制，且没有把实验性解析泄漏为生产接口承诺。

