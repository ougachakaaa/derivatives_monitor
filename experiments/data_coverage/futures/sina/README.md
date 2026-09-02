# Sina Futures Probe

本目录是 Sina CFFEX 股指期货覆盖实验的局部入口。

## 开始 Probe

1. 阅读上级 `SPEC.md` 获取产品和证据要求。
2. 阅读 [REFERENCE.md](REFERENCE.md) 获取 contract discovery、quote 和 minute endpoint 起点。
3. 编写可重复运行的 `probe.py`（或等价小型脚本），把合约发现与行情请求分开记录。
4. 按 [samples/README.md](samples/README.md) 保存真实响应。
5. 更新 [coverage.md](coverage.md) 和 [report.md](report.md)。

Reference 中的合约月份和字段只是示例。实验完成前状态保持 `NOT_TESTED`。

## 预期产物

```text
sina/
├── probe.py            # 实际 Probe 任务创建
├── samples/            # discovery、quote、minute 原始证据
├── coverage.md
└── report.md
```

