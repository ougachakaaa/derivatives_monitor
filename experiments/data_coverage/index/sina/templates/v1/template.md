# Sina Index Snapshot Response Template v1

本文件是根据实测响应归纳的解释性样例，帮助人和后续 Agent 离线理解返回内容。它不是来源承诺、生产 schema 或解析器接口；真实返回内容始终以实际请求证据为准。

## Provenance

- Source run：`20260902T232947+0800`
- Raw body：`01_hq_batch.body`
- Raw SHA-256：`8a48586d0dc33b139de621bca248fa5a6ade7dfb32cd02d9c726df833e7696e0`
- Response：`application/javascript; charset=GB18030`
- Full machine-readable provenance and fingerprints：[manifest.json](manifest.json)

## Interpreted shape

```text
var hq_str_<source_identifier>="<name>,<open>,<previous_close>,<last>,<high>,<low>,<bid>,<ask>,<volume>,<amount>,<position_10>,...,<position_29>,<date>,<time>,<status>[,]";
```

每条 declaration 的 payload 有 33 个逻辑位置。实测中六条记录在末尾带额外分隔符，`sz399006` 不带；尾部分隔符不增加逻辑字段数。

| Position | Observed type | Interpretation | Confidence |
|---:|---|---|---|
| 0 | text | 指数名称 | high |
| 1 | number | 开盘值 | medium |
| 2 | number | 前收值 | medium |
| 3 | number | 当前/最新值 | medium |
| 4 | number | 最高值 | medium |
| 5 | number | 最低值 | medium |
| 6 | number | 买价或来源占位值 | low |
| 7 | number | 卖价或来源占位值 | low |
| 8 | number | 成交量 | medium |
| 9 | number | 成交额 | medium |
| 10–29 | number | 传统行情协议中的盘口位置；本样本均为零，不能独立确认各位置语义 | low |
| 30 | date | 行情日期，`YYYY-MM-DD` | high |
| 31 | time | 行情时间，`HH:MM:SS` | high |
| 32 | number | 来源状态位置，精确语义未确认 | low |

`UNKNOWN` 或低置信度位置应保持未确认状态，不得仅凭本模板提升为生产字段语义。

## Target mapping

| Target | Official code | Source identifier |
|---|---|---|
| 上证50 | `000016` | `sh000016` |
| 沪深300 | `000300` | `sh000300` |
| 中证500 | `000905` | `sh000905` |
| 中证1000 | `000852` | `sh000852` |
| 中证2000 | `932000` | `si932000` |
| 科创50 | `000688` | `sh000688` |
| 创业板指 | `399006` | `sz399006` |

## Limits

- 样本在收盘后取得，不能证明盘中实时性或延迟。
- 数值、日期、时间、body 长度和 raw hash 会随请求变化，不构成模板版本升级依据。
- wrapper、逻辑字段结构、类型模式或目标 identifier 映射变化时，应生成下一版模板并说明差异。
