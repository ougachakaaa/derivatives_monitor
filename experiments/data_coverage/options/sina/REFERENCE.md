# Sina CFFEX Options API Reference

本文件从项目收到的 2026-09-02 Market Data Source Probe Reference 中摘取 Sina 股指期权相关内容。所有月份、字段和结构信息都只是非规范性的探测线索，不是本仓库实测结论，也不限定实际响应格式。

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

Reference 指出 AKShare 会从这些页面解析当前期权月份。Probe 应将 expiry discovery 与 chain retrieval 分开，并按请求实际返回的内容保存足以复核发现结果的样板。

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

## 上游实现线索

AKShare 当前实现读取：

```text
result.data.up
result.data.down
```

上游实现将这两部分解释为 T 型期权行情表，并曾映射以下信息：

- Call：instrument、bid volume、bid、last、ask、ask volume、open interest、change；
- Strike；
- Put：instrument、bid volume、bid、last、ask、ask volume、open interest、change。

这些节点、名称和组织不是本 Harness 的格式要求。Probe 应先保存请求实际返回的内容，再判断其中能否识别 Call/Put、strike、instrument 等语义；不得因上游 wrapper 的命名预先认定映射。

## 来源链接

- [AKShare option docs](https://akshare.akfamily.xyz/data/option/option.html)
- [AKShare Sina CFFEX option implementation](https://github.com/akfamily/akshare/blob/main/akshare/option/option_finance_sina.py)
- [Sina CFFEX HO page](https://stock.finance.sina.com.cn/futures/view/optionsCffexDP.php/ho/cffex)
- [Sina CFFEX options page](https://stock.finance.sina.com.cn/futures/view/optionsCffexDP.php)
- [Sina CFFEX option-chain endpoint](https://stock.finance.sina.com.cn/futures/api/openapi.php/OptionService.getOptionData)
