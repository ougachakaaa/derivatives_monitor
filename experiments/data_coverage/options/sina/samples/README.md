# Options Sample Storage

保存 expiry discovery 和 whole-chain 的真实响应。每个被测 expiry 的 chain 样板必须保留服务端完整组织，不能只留几个 strike 或人工整理表。

建议命名：

```text
YYYYMMDDTHHMMSS+0800_expiries_<product>.raw
YYYYMMDDTHHMMSS+0800_chain_<product>_<yymm>.json
```

每个响应体应配最小 request/response metadata，记录接收时间、URL/非敏感参数、HTTP 状态、内容类型与编码。页面解析时保留足以离线复核全部 expiry 的原始页面；chain JSON 应保留完整 `result.data` 结构。不要提交 cookie、token 或其他秘密。

