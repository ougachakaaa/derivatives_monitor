# Futures Sample Storage

保存三类可离线复核的真实证据：contract discovery、snapshot quote、minute response。

建议命名：

```text
YYYYMMDDTHHMMSS+0800_discovery_<product>.raw
YYYYMMDDTHHMMSS+0800_quote_<contract-or-batch>.raw
YYYYMMDDTHHMMSS+0800_minute_<contract>_<interval>.raw
```

每个响应体应配最小 request/response metadata，记录接收时间、URL/非敏感参数、HTTP 状态、内容类型与编码。批量 quote 不要拆到丢失原始组织关系；JSONP 不要只保存去包装后的结果。不要提交 cookie、token 或其他秘密。

