# Sina CFFEX Options API Reference

本文件从项目收到的 2026-09-02 Market Data Source Probe Reference 中摘取 Sina 股指期权相关内容。它是 Probe 起点，不是本仓库实测结论。

## 产品参数

| Product | Underlying | Request value |
|---|---|---|
| HO | 上证50股指期权 | `ho` |
| IO | 沪深300股指期权 | `io` |
| MO | 中证1000股指期权 | `mo` |

## Expiry discovery

HO 页面：

```text
https://stock.finance.sina.com.cn/futures/view/optionsCffexDP.php/ho/cffex
```

CFFEX overview / IO / MO 页面：

```text
https://stock.finance.sina.com.cn/futures/view/optionsCffexDP.php
```

Reference 指出 AKShare 会从这些页面元素解析当前期权月份。Probe 应将 expiry discovery 与 chain retrieval 分开，并保存足以复核月份解析的原始页面或近原始片段。

## Whole-chain endpoint

```text
https://stock.finance.sina.com.cn/futures/api/openapi.php/OptionService.getOptionData
```

参数：

```text
type=futures
product=<ho|io|mo>
exchange=cffex
pinzhong=<product+YYMM>
```

2026 年 9 月示例：

```text
...?type=futures&product=ho&exchange=cffex&pinzhong=ho2609
...?type=futures&product=io&exchange=cffex&pinzhong=io2609
...?type=futures&product=mo&exchange=cffex&pinzhong=mo2609
```

`2609` 只是示例，不得假定始终挂牌。

## Reference 中的响应结构

AKShare 当前实现读取：

```text
result.data.up
result.data.down
```

这两侧对应 T 型期权行情表。Reference 预期包含：

- Call：instrument、bid volume、bid、last、ask、ask volume、open interest、change；
- Strike；
- Put：instrument、bid volume、bid、last、ask、ask volume、open interest、change。

Probe 必须先保存完整 raw JSON，再确定 `up`/`down` 的实际方向、字段名/顺序、instrument 编码和缺失值。不得因 wrapper 的命名而预先认定 Call/Put 映射。

## 来源链接

- [AKShare option docs](https://akshare.akfamily.xyz/data/option/option.html)
- [AKShare Sina CFFEX option implementation](https://github.com/akfamily/akshare/blob/main/akshare/option/option_finance_sina.py)
- [Sina CFFEX HO page](https://stock.finance.sina.com.cn/futures/view/optionsCffexDP.php/ho/cffex)
- [Sina CFFEX options page](https://stock.finance.sina.com.cn/futures/view/optionsCffexDP.php)
- [Sina CFFEX option-chain endpoint](https://stock.finance.sina.com.cn/futures/api/openapi.php/OptionService.getOptionData)

