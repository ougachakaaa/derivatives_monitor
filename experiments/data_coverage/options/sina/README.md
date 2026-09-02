# Sina Options Probe

本目录是 Sina CFFEX 股指期权覆盖实验的局部入口。

## 开始 Probe

1. 阅读上级 `SPEC.md` 获取产品和 chain completeness 要求。
2. 阅读 [REFERENCE.md](REFERENCE.md) 获取 expiry discovery 页面和 whole-chain endpoint 起点。
3. 编写可重复运行的 `probe.py`（或等价小型脚本），明确分离 expiry discovery 与 chain retrieval。
4. 按 [samples/README.md](samples/README.md) 保存完整真实响应。
5. 更新 [coverage.md](coverage.md) 和 [report.md](report.md)。

不要硬编码 Reference 中的 `2609`，不要只保存人工整理后的 strike 表，也不要以少数已知合约代替完整链验证。

## 预期产物

```text
sina/
├── probe.py            # 实际 Probe 任务创建
├── samples/            # expiry 页面/响应与每个被测 expiry 的完整链
├── coverage.md
└── report.md
```

