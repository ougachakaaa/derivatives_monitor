# Response Template Validations

`MATCH` 表示本地成功样本的结构与语义指纹仍与当前模板一致；行情数值、时间、raw 大小和 raw hash 不参与匹配。

| Date | Template | Source run | Raw SHA-256 | Format fingerprint | Semantic fingerprint | Result |
|---|---|---|---|---|---|---|
| 2026-09-03 | `v1` | `20260902T232947+0800` | `8a48586d0dc33b139de621bca248fa5a6ade7dfb32cd02d9c726df833e7696e0` | `566b70930ef2d5bbeeb5b507e2ae03b862840ac7fb430bd6d870ffeea615e4cb` | `459427ea0fdcc3191d121aadd51051b107e6b0fcd1680a3d199ea179d958c618` | `MATCH` |
