# Sina Index API Reference

本文件从项目收到的 2026-09-02 Market Data Source Probe Reference 中摘取 Sina 指数相关内容。所有 symbol、字段和结构信息都只是非规范性的探测线索，不代表已经在本仓库实测确认，也不限定实际响应格式。

## 候选 symbol

| 指数 | Candidate |
|---|---|
| 上证50 | `sh000016` |
| 沪深300 | `sh000300` |
| 中证500 | `sh000905` |
| 中证1000 | `sh000852` |
| 中证2000 | `sh932000`（必须实测） |
| 科创50 | `sh000688` |
| 创业板指 | `sz399006` |

中证2000 的官方代码是 `932000`，但 Reference 仅把 `sh932000` 作为合理候选。如果单 symbol endpoint 不接受它，应尝试 Market Center 发现 Sina 当前表示，并在 report 中区分实测结果与 fallback 建议。

## Lightweight quote endpoint

```text
https://hq.sinajs.cn/list=sh000016,sh000300,sh000905,sh000852,sh932000,sh000688,sz399006
```

Reference 还观察到以下形式：

```text
https://hq.sinajs.cn/etag.php?list=sh000016,sh000300,sh000905,sh000852,sh932000,sh000688,sz399006
```

建议测试的请求头：

```http
Referer: https://finance.sina.com.cn/
User-Agent: Mozilla/5.0 ...
```

如被拒绝，可记录并测试：

```http
Referer: https://vip.stock.finance.sina.com.cn/
```

## All-index Market Center

数据 endpoint：

```text
http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeDataSimple
```

Reference 中的典型参数：

```text
page=1
num=80
sort=symbol
asc=1
node=hs_s
_s_r_a=page
```

Count endpoint：

```text
http://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeStockCountSimple?node=hs_s
```

此 endpoint 可用于发现 symbol 或处理 lightweight endpoint 变化。作为搜索线索，AKShare 上游实现曾映射 `code`、`name`、`latest`、`change`、`change_percent`、`previous_close`、`open`、`high`、`low`、`volume`、`amount` 等信息；这些名称不是本 Harness 的字段要求，Probe 只以实际响应为准。

## 来源链接

- [AKShare index docs](https://akshare.akfamily.xyz/data/index/index.html)
- [AKShare Sina index implementation](https://github.com/akfamily/akshare/blob/main/akshare/index/index_stock_zh.py)
- [AKShare Sina index constants](https://github.com/akfamily/akshare/blob/main/akshare/index/cons.py)
- [Sina 上证50](https://finance.sina.com.cn/realstock/company/sh000016/nc.shtml)
- [Sina 沪深300](https://finance.sina.com.cn/realstock/company/sh000300/nc.shtml)
- [Sina 中证500](https://finance.sina.com.cn/realstock/company/sh000905/nc.shtml)
- [Sina 中证1000](https://finance.sina.com.cn/realstock/company/sh000852/nc.shtml)
- [Sina 科创50](https://finance.sina.com.cn/realstock/company/sh000688/nc.shtml)
- [Sina 创业板指](https://finance.sina.com.cn/realstock/company/sz399006/nc.shtml)
- [CSI 中证2000 official page](https://www.csindex.com.cn/#/indices/family/detail?indexCode=932000)
