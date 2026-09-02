# Sina Index Probe

本目录是 Sina 指数覆盖实验的局部入口。

## 开始 Probe

1. 阅读上级 `SPEC.md` 获取 7 个必测指数。
2. 阅读 [REFERENCE.md](REFERENCE.md) 获取候选 endpoint、参数和来源链接。
3. 编写可重复运行的 `probe.py`（或等价的小型脚本）。
4. 按 [samples/README.md](samples/README.md) 保存真实响应。
5. 更新 [coverage.md](coverage.md) 和 [report.md](report.md)。

不要把 Reference 中的 candidate symbol 或 expected fields 写成实验结论。实验完成前，覆盖状态保持 `NOT_TESTED`。

## 预期产物

```text
sina/
├── probe.py            # 实际 Probe 任务创建
├── samples/            # raw / near-raw response 与最小元数据
├── coverage.md         # 按指数和能力记录状态
└── report.md           # 本次实验摘要
```

