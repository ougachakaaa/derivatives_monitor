# 外部参考档案

这里保存外部事实来源与历史接入记录。项目设计决定见[MVP](../mvp.md)和[架构](../architecture.md)；外部资料不自动变成当前运行保证。`experiments/` 中现有原件、SDK 和实验 harness 均未移动或修改。

## 中信建投咨询与回复

| 材料 | 位置与用途 |
|---|---|
| 原始咨询问题和券商回复 DOCX | [原件](originals/csc-ctp-mvp-questions-and-replies.docx)，从 Git `fb25dc9` 恢复，包含接入参数、覆盖、频率、现货缺失、费用/限额合并回复和交易接入事项 |
| 可阅读的原文转录 | [咨询与回复](csc-questions-and-replies.md)，从 DOCX 段落提取，不补写或扩大答复 |
| 已有接入摘要 | [中信建投接入信息](../../experiments/ctp/docs/csc-futures-ctp-market-data-access.md)，原位保留，含六个前置、明确未逐项答复的事项 |
| 历史厂商 API 帮助 | [6.7.9P1 CHM](originals/ctp-6.7.9P1-api-manual.chm)，从同一历史提交恢复；仅作资料档案，不替代当前 6.7.13 SDK |
| 原件来源和校验 | [manifest.json](originals/manifest.json)，记录完整 commit、原路径和 SHA-256；harness 校验文件哈希 |

原咨询中提到 `6.7.9P1API_chm.zip`、`futureapi_6.6.8_demo.zip`，只有文件名，没有下载 URL。CHM 可恢复；两个原始 ZIP 不在当前工作树，不能伪造下载链接。旧 Windows demo 可在同一 Git 提交追溯，不恢复为当前工程。咨询文件没有足够证据确定回复日期，归档恢复日为 2026-09-08。

“每秒两次”“无限制”“无费用/门槛”等是历史回复原文，不据此承诺当前服务。CTP 无现货指数能力是本项目已有设计输入；模型若需要现货，需另行明确来源。

## 当前 SDK 来源与下载入口

当前固定版本 **v6.7.13_20260225 / Linux x86-64 Market Data**，不在整理过程中升级或重新下载替换。

- [仓库 SDK 清单](../../experiments/ctp/sdk/v6.7.13_20260225/MANIFEST.txt)：原包 `v6.7.13_20260225_trader.zip`，SHA-256 `a15958da251fe8d375fc66f56721ef067b2f300bc7979572e4eaf95d53ca8ae5`；包含三份头文件转码前后和动态库哈希。包名含 trader 不代表项目使用 Trader API。
- [SDK 目录](../../experiments/ctp/sdk/v6.7.13_20260225/linux64/mdapi/)、[接入/构建说明](../../experiments/ctp/README.md)、[行情字段表](../../experiments/ctp/docs/ctp-depth-market-data-fields.csv)。仅注释从 GB18030 转为 UTF-8；二进制未改。
- [上期技术官方下载入口](https://www.sfit.com.cn/5_2_DocumentDown_2.htm)、[SimNow API 下载入口](https://www.simnow.com.cn/static/apiDownload.action)。上期技术入口亦可从[中信建投外部接入指引](https://m.cfc108sh.com/uploads/czzy.pdf)的官网地址追溯。

2026-09-08 补录上述下载入口：上期技术访问出现 TLS/网关错误；SimNow 返回 202 验证页面，未取得下载清单。原 MANIFEST 没有记录该版本 ZIP 的原始直链，当前不能确认精确下载 URL 或入口可用性。保留可定位入口、固定版本和哈希，不将未经验证的拼接 URL 当成来源。未来重新取得原包时核对原包哈希并补充真实 URL/抓取时间；构建目前使用已入库最小 SDK，无需联网下载。

## 市场参考与技术依据

[Analytics / Skew 来源记录](analytics-skew-sources.md)区分官方MO/IM/Shibor事实、独立QuantLib oracle与项目自行冻结的近似和阈值。

- [日历/时段契约及官方来源](../contracts/market-session.md)、[版本化年历与更新](../../query/calendars/README.md)；年历文件自身保存来源、版本和覆盖范围，整理未改变交易规则。
- [CFFEX 官方清单历史验证](../archive/acceptance/CFFEX_Coverage_Acceptance_CN.md)、[SHFE 官方清单和夜盘历史验证](../archive/acceptance/Market_Session_SHFE_Acceptance_CN.md)保留日期 URL/哈希与证据路径。运行时原响应保存在 `collector/data/universe/raw/`，清单 generation 与来源一同发布；不把公开参考价格作为 Raw 行情。
- [SQLite WAL](https://www.sqlite.org/wal.html)、[只读 URI](https://www.sqlite.org/uri.html)、[同步级别](https://www.sqlite.org/pragma.html#pragma_synchronous)；部署和前端技术链接保留在[只读契约](../contracts/read-path.md)及模块手册。

新增参考应记录发布者、用途、版本/日期、真实 URL、当地可保留的原件、SHA-256、可用性/缺失限制。原始文件保持原样，解释另写；不提交账户密码或个人配置。
