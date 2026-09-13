<a id="analytics-reference-bundle-contract"></a>

# Skew ReferenceBundle 与只读适配契约

Analytics 所需参考字段、来源、单位、日期、范围与折现约定由 [Skew v1](analytics-skew.md#4-参考参数与可重放性)定义；本文件拥有审核包布局、导入、选择、哈希核对与读取上下文。

参考包位于独立只读 `references/analytics/<day>/<bundle_id>/bundle.json`。不可变包由外部审核/导入流程维护，修订产生新 bundle ID 和哈希，旧包不得覆盖；Production 与 TEST DOUBLE 分开，`SYNTHETIC` 只准用于明确 TEST DOUBLE 的验收。原响应在受限本地归档，Git 只保存非敏感来源说明与版本清单。

运维导入包至少包含 `manifest.json`、`bundle.json`、`universe.json`、`calendar.json`、`listing.source`、`rules.source` 和 `rate.source`。`skew_references.py` 验证来源字节、manifest 及 bundle 身份后复制到 `<directory>/<trading_day>/<bundle_id>/`，已有 bundle ID 不覆盖；审核者再原子发布 `<day>/<month>.json` 选择文件。导入器不联网抓取、不替代人工审核、不修改 Raw。

请求入口只读取一次选择文件中的 bundle ID，再核对不可变包所有实际原文件 SHA-256；显式 bundle ID 可回放旧包。历史查询不使用 `universe/current`。Market Frame 只携带 Universe/Calendar version，适配器从明确不可变的 Universe/Calendar 输入生成 frame、核对参考包哈希并固定读取上下文，不得伪造 frame 中不存在的 hash 字段。Calendar 从已核对哈希的原字节初始化并固定传给 reader；Universe 使用保存的历史 manifest。

数值核心仍只消费 frame 与参考对象，不读取 Raw 或参考文件。重放身份至少包含 `(contract_id, algorithm_version, actual_trading_day, month, minute, raw_revision, universe_version+hash, calendar_version+hash, reference_bundle_id+hash)`；后补参考的 `retrieved_at` 可以晚于历史估值时刻，但必须标记 `reconstructed=true`，不得声称当时系统已拥有该参考或已提交行情。

实际离线导入命令见 [Analytics README](../README.md#审核参考包的离线导入)，来源档案见 [Analytics / Skew sources](../references/analytics-skew-sources.md)。
