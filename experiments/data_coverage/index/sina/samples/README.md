# Index Sample Storage

保存 Sina 指数 endpoint 的 raw / near-raw 响应，使读者无需再次联网即可理解真实格式。

每组样板应包含响应体和最小元数据。建议命名：

```text
YYYYMMDDTHHMMSS+0800_<endpoint>_<instrument-or-batch>.raw
YYYYMMDDTHHMMSS+0800_<endpoint>_<instrument-or-batch>.request.json
YYYYMMDDTHHMMSS+0800_<endpoint>_<instrument-or-batch>.response.json
```

元数据至少记录接收时间、URL/非敏感参数、HTTP 状态、内容类型与编码。批量响应不得只截取一条；保存能展示完整批量组织方式的真实响应。不要提交 cookie、token 或其他秘密。

