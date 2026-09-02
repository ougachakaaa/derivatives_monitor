# Sina CFFEX Futures API Reference

本文件从项目收到的 2026-09-02 Market Data Source Probe Reference 中摘取 Sina 股指期货相关内容。所有合约、字段和结构信息都只是非规范性的探测线索，不是本仓库实测结论，也不限定实际响应格式。

## 产品和 quote symbol

| Product | Underlying | Sina quote prefix |
|---|---|---|
| IH | 上证50 | `nf_IH` |
| IF | 沪深300 | `nf_IF` |
| IC | 中证500 | `nf_IC` |
| IM | 中证1000 | `nf_IM` |

quote 需要具体合约月份。Reference 的 `IH2609`、`IF2609`、`IC2609`、`IM2609` 仅为 2026 年 9 月示例，Probe 必须先发现当前有效合约。

## Contract discovery

AKShare 的 Sina 实现包含 `IF`、`IC`、`IM`、`IH`，并引用：

```text
http://vip.stock.finance.sina.com.cn/quotes_service/view/js/qihuohangqing.js
```

其 main-contract/data endpoint 为：

```text
http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQFuturesData
```

Probe 应检查当前 AKShare 实现和实际响应，不能照搬旧的 discovery 假设。

## Realtime quote endpoint

请求形式：

```text
https://hq.sinajs.cn/rn=<cache_buster>&list=nf_IH2609,nf_IF2609,nf_IC2609,nf_IM2609
```

建议测试的 headers：

```http
Referer: https://vip.stock.finance.sina.com.cn/
User-Agent: Mozilla/5.0 ...
```

作为搜索线索，历史或上游 wrapper 曾映射 `name`、`time`、`open`、`high`、`low`、`previous_close`、`bid1`、`ask1`、`last`、`previous_settlement`、`settlement`、`bid_volume1`、`ask_volume1`、`open_interest`、`volume` 等信息。这些名称和位置不是本 Harness 的格式要求，实际可识别内容只能由当前请求确认。

## Minute endpoint

```text
https://stock2.finance.sina.com.cn/futures/api/jsonp.php/=/InnerFuturesNewService.getFewMinLine
```

参数：

```text
symbol=IF2609
type=1
```

Reference 中 AKShare 支持的 interval 值为 `1`、`5`、`15`、`30`、`60`。示例：

```text
https://stock2.finance.sina.com.cn/futures/api/jsonp.php/=/InnerFuturesNewService.getFewMinLine?symbol=IF2609&type=1
```

作为搜索线索，AKShare 上游实现曾把响应映射为 `datetime`、`open`、`high`、`low`、`close`、`volume`、`hold` 等信息。这不要求响应采用 JSONP、固定字段名或任何特定结构，Probe 只记录实际返回。

## 来源链接

- [AKShare futures docs](https://akshare.akfamily.xyz/data/futures/futures.html)
- [AKShare Sina futures implementation](https://github.com/akfamily/akshare/blob/main/akshare/futures/futures_zh_sina.py)
- [AKShare futures constants](https://github.com/akfamily/akshare/blob/main/akshare/futures/cons.py)
- [Sina futures market](https://finance.sina.com.cn/futuremarket/)
- [Sina futures contract/variety resource](http://vip.stock.finance.sina.com.cn/quotes_service/view/js/qihuohangqing.js)
