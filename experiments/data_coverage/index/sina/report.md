# Sina Index Snapshot Probe Report

## Scope

- 2026-09-02 23:29:47（Asia/Shanghai）从本地开发环境执行最终复跑。
- 命令：`python -B experiments/data_coverage/index/sina/probe.py`。
- 验证上证50、沪深300、中证500、中证1000、中证2000、科创50、创业板指的 Sina snapshot 获取能力和实际 identifier。
- 本轮未执行 Minute Probe；所有 Minute 状态保持 `NOT_TESTED`。
- 本轮不评价实时延迟、稳定性、轮询频率、broker 对比或 CloudBase 可用性。

## Evidence

- 可重复执行的 Probe：[probe.py](probe.py)。脚本使用 Python 标准库，按运行时间创建本地 sample 目录，保存响应原始字节、非敏感请求结果和不解释字段的 declaration inventory；非 UTF-8 响应另存可读副本，不替换 raw evidence。
- 持久化解释材料：[template v1](templates/v1/template.md)、[provenance manifest](templates/v1/manifest.json)、[validation history](templates/VALIDATIONS.md) 和离线 [template checker](template_check.py)。Template 是实测响应的带置信度说明，不是生产 schema。
- 最终 7/7 batch run 为本地 `samples/20260902T232947+0800/`。HTTP 200，响应声明 `charset=GB18030`，原始 body 为 1251 bytes，SHA-256 为 `8a48586d0dc33b139de621bca248fa5a6ade7dfb32cd02d9c726df833e7696e0`；其 provenance 已固化在 manifest。
- 中证2000 identifier discovery 来自本地 run `20260902T232656+0800`；该 run 还记录 Market Center fallback 返回 562 条记录但没有代码 `932000`。
- timestamped sample runs 被 Git 忽略并保留在执行者本地。Clean clone 通过 template 与 manifest 理解既有证据；需要复核 raw 时，应在明确的 Probe/refresh 任务中重新生成样本。

## Findings

- 最终 batch endpoint 对 7 个实测 identifier 均返回非空声明，声明内名称分别与七个目标指数一致，因此七项 Snapshot 状态均为 `SUPPORTED`。
- 实测 identifier 为：`sh000016`、`sh000300`、`sh000905`、`sh000852`、`si932000`、`sh000688`、`sz399006`。
- Reference candidate `sh932000` 在普通 batch 和 `etag.php` 两种请求中均返回空声明；`s_si932000` 与 `s_sh932000` 也为空。`si932000` 返回名称为“中证2000”的非空声明，因此 coverage 已改用 `si932000`。
- 实际 quote response 是按 symbol 命名的 JavaScript declarations，payload 为逗号分隔内容，包含指数名称、数值以及日期时间文本。本轮保存完整响应，但不为各位置预设或声明字段语义。
- 最终请求接收时间在收盘后，payload 内日期为 `2026-09-02` 且包含不同的盘后时间文本；这些事实不能用于证明实时性或延迟。

## Open Questions

- payload 中各数值位置的准确语义尚未验证；如后续解析需要，应基于独立证据确认，而不是直接采用历史字段位置。
- `si932000` 是否在不同交易日持续稳定，需要后续运行继续观察；当前结论只证明本次请求可获取。
- Sina 的 Index Minute 能力未测试。
- 活跃交易时段的数据新鲜度、网络稳定性、保守轮询频率、broker 对比和 CloudBase 可用性均留待后续独立实验。
