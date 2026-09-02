# Market Data Coverage Experiments

本目录用于验证市场数据源是否覆盖 Derivatives Monitor 所需的数据，并保存可复查的原始证据。这里的产物服务于数据源探索，不是生产实现。

## 目录规则

目录固定按“需要的数据 → 数据源”组织：

```text
data_coverage/
├── README.md / AGENTS.md / DESIGN.md / SPEC.md
├── index/
│   ├── SPEC.md
│   └── sina/
│       ├── REFERENCE.md
│       ├── coverage.md
│       └── samples/
├── futures/
│   ├── SPEC.md
│   └── sina/
│       ├── REFERENCE.md
│       ├── coverage.md
│       └── samples/
└── options/
    ├── SPEC.md
    └── sina/
        ├── REFERENCE.md
        ├── coverage.md
        └── samples/
```

这样做可以让执行某一类 Probe 的 Agent 只读取该类数据及目标数据源的局部文档，不必把全部数据源资料加载进上下文。

## 从哪里开始

1. 先读取本目录的 [AGENTS.md](AGENTS.md) 和 [SPEC.md](SPEC.md)。
2. 读取目标数据类型的 `SPEC.md`。
3. 进入目标数据源目录，只读取 `REFERENCE.md` 和现有 `coverage.md`。
4. 编写并运行可重复执行的 Probe，将原始或近原始响应放入 `samples/`。
5. 更新 `coverage.md`，并按根 `SPEC.md` 的大纲创建本次实验的 `report.md`。

当前第一批数据源是 Sina Finance direct HTTP。

## 每次实验必须留下的产物

- **Probe Code**：可重复执行，并记录请求参数与必要环境信息。
- **Raw / Near-Raw Samples**：按实际收到的内容保存，不先转换成未来系统的 canonical schema，也不预设文件格式或组织方式。
- **Coverage Result**：按 `SUPPORTED`、`PARTIAL`、`UNSUPPORTED`、`NOT_TESTED` 标记。
- **Experiment Report**：简述验证范围、成功与缺失、样板位置和未解决问题。

提交前应确保后续 Agent 可以仅凭 Probe Code、samples、coverage 和 report 复核结论，并能在不重新请求数据源的情况下理解返回格式。

## 添加新数据源

在对应数据类型下新增小写数据源目录，例如 `index/eastmoney/`，并建立局部 `REFERENCE.md`、`coverage.md` 和 `samples/`。Probe Code 与 report 在实际实验开始时创建，不放空实现或细粒度模板。如果多个数据类型需要该数据源，分别建立局部 Reference，避免一次加载全部资料。
