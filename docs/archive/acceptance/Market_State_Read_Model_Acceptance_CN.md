# Market State Read Model 验收

> 历史验收快照：仅证明文中日期/版本/环境下的观察。旧端口、临时路径、待验状态和操作命令可能已过时；当前设计见[文档入口](../../README.md)，当前门槛见[验收矩阵](../../acceptance.md)，运行见[操作说明](../../operations.md)。原始日志缺失时仅作为历史摘要。


2026-09-08。状态：本阶段代码与离线验收完成。设计与任务先于代码提交；没有修改 Collector、runtime、Raw schema、持久行情或日历规则。

## 实施提交

- `20aca61`：设计基线和 T1–T4 specs。
- `e1149b7`：Universe / Scope 契约。
- `af8f45b`：as-of / minute、质量、完整性、revision 重建。
- `aa2ccb5`：Latest、JSON CLI、Query 文档和 Docker 模块复制。
- T4 验收提交：补充 WAL 帧内提交、实际 SQL 计划、异常质量、时区等验证及本文。

## 实测结果

在仓库根目录执行：

```bash
(cd query && .venv/bin/python -m unittest discover -s tests -v)
git diff --check
```

46项全部通过（24项新 Market State 测试 + 22项既有 Query 测试），约5.3秒。现有 Starlette/httpx deprecation warning 不影响通过；未变更依赖。测试使用临时目录中的实际 schema-v1 SQLite/WAL、真实 Store 和日历，不连接实盘，不使用 mock 行情查询。WAL帧内提交测试只在首条 observation 的质量处理处插入受控 writer commit，读查询仍为真实SQLite事务。

| 用户验收项 | 已取得的证据 |
|---|---|
| 1 指定交易日/分钟 instrument frame | 20260908 MO2609-C-5000，09:30分钟选择09:30:45，排除09:31:00；point09:31:00包含边界行。 |
| 2 完整 MO 月链 | 显式合成 MO2609 清单含40个strike × C/P = 80个成员；Python与独立CLI均输出80/80/80、COMPLETE。该清单是测试定义的完整链，不声称是交易所当日真实上市清单。 |
| 3 每 instrument 一个 observation | 多行/跨run同received_us按id裁决；80个输出instrument无重复，按代码稳定排序。 |
| 4 真实时间和age | received_us、snapshot_us、ActionDay、UpdateTime、UpdateMillisec保持；分钟示例age15秒；UTC等价输入输出一致。 |
| 5 missing/stale/partial | 缺失成员保留null；80成员场景产生missing=1、invalid=1、stale=78，明确PARTIAL；age恰等阈值不过期；不完整参考清单不能COMPLETE；无观察为EMPTY。 |
| 6 无隐式forward-fill | 后续分钟引用原id/received_us且age增长，库中仍仅原始一行；无新callback的时段不生成observation。 |
| 7 session隔离 | CFFEX午休、14:57竞价切换，SHFE10:15休息、夜盘→日盘均不继承；SHFE跨午夜同一个night period可读且归属20260908。 |
| 8 sealed确定性 | 相同条件结果相等，CLI输出逐字相等；晚物化被保留；sealed后追加会改变默认revision，固定原revision结果完全相同；未封口分钟排除evaluated_at后的行。 |
| 9 Latest状态 | OPEN当前段；BREAK午休历史段且age增长；CLOSED保留收盘竞价、区分下一calendar day与实际frame day；周末保留周五；UNKNOWN无frame。重新开盘缺失返回EMPTY。 |
| 10 Python只读 | 复用mode=ro/query_only；离线文件SHA256及目录集合不变，DELETE被拒绝；活跃WAL两次查询看到后续commit但单帧不混合，未创建reader文件。 |
| 11 无Analytics | 新生产代码仅scope、选择、质量、frame和CLI；未引入定价、IV、Skew、Basis、Derived SQLite或采集控制。 |
| 12 下一阶段稳定输入 | schema_version=1输出scope、session、原始事实、quality、完整性、raw_revision；Python入口与CLI、默认可用质量标准和时间契约均已文档化。 |

实际 frame SQL 的 `EXPLAIN QUERY PLAN` 确认 `USING INDEX snapshots_instrument_time`，没有排序临时B-tree；没有为读取新增索引。缺库仍404，缺字段的不兼容库503，不被当成EMPTY。

## 交接与限制

- 本模型只能重建15秒采样保留的真实接收observation，无法恢复丢弃的tick，也不代表当时SQLite已经提交可见的内容。
- sealed是时间封口；需要重复读取不受append影响时保留raw_revision，且使用同一append-only日库、同一显式Universe和Calendar版本。文件被外部覆写/删行后不保证重放。
- 全链成员是显式历史参考清单的契约。Universe.from_manifest只在产品day匹配、verified且非stale时声明完整；当前清单不会被自动套用历史日。
- 默认质量是一级双边价/量有效且不过期，不保证每个observation已经满足未来IV的所有条件。下一阶段应显式筛选usable/quality，并自行决定PARTIAL的处理策略。
- 不在无行情period/缺文件时搜索更早“有数据”的period。Latest休市历史frame不是当前报价，age包含休市时间。产品日历继承既有单合约到期日例外限制。
- Dockerfile已包含模块，但本阶段未执行Docker构建或部署、未进行真实CTP/真实上市链验收、未对大规模生产库做负载基准；离线证据不替代这些现场结论。
