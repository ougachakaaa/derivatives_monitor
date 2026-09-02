# Options Coverage Specification

## 产品全集

必须覆盖 CFFEX 股指期权：

| Product | Underlying |
|---|---|
| HO | 上证50股指期权 |
| IO | 沪深300股指期权 |
| MO | 中证1000股指期权 |

## 必须证明的发现路径

```text
Product
  -> Expiry
      -> Strike
          -> Call
          -> Put
```

## Probe 验收

对 HO、IO、MO 分别确认并留证：

- 当前 listed expiries 可由来源发现，而非只使用预先知道的月份；
- 对发现的 expiry 逐一尝试 whole-chain 请求，并分别记录结果；
- 成功链保留完整 raw response，而非只截取 ATM 或几个已知合约；
- 可从返回中识别 expiry、strike、Call/Put、instrument code；
- 同一 strike 的 Call 和 Put 侧是否完整，ATM 与 OTM strikes 是否包含；
- chain 的批量/T 型表组织、字段名或字段顺序、timestamp 与 null/missing 表达。

如果 expiry discovery 成功但部分 expiry 或部分 Call/Put/strike 缺失，应按能力维度标记 `PARTIAL`，不能把少数合约成功写成 whole-chain `SUPPORTED`。

