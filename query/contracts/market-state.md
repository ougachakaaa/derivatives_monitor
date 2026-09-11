<a id="query-market-state-contract"></a>

# Minute Market Frame / Latest Market State


Python 契约 v1；已实现，历史离线证据见[归档](../../docs/archive/acceptance/Market_State_Read_Model_Acceptance_CN.md)，当前状态见[本级 Acceptance](../ACCEPTANCE.md)，系统收尾门槛见[根验收矩阵](../../docs/acceptance.md)。

## 架构位置

Collector 的 callback、采样和物化行为见 [Collector Contract](../../collector/CONTRACT.md#数据与采样不变量)；Raw 所有权、分区身份、只读和 WAL/锁协议见 [Raw Boundary](../../docs/contracts/raw-boundary.md)。Python `Store.connect` 在该共享边界内提供事务和执行预算。`Calendar` 提供版本化产品时段（含竞价），native runtime 管理进程；这些机制不需要改写。

纯 Python `query/market_state.py`，复用 Store 和 Calendar，提供可导入的 scope / frame / latest 契约及 JSON CLI。无需新增 HTTP、调度任务或常驻缓存。Analytics 只依赖这个模块的输出，不理解文件路径、表名或 SQL。

## Scope 与完整性

一个 scope 只含一个 exchange/product，可为 instrument、product、month 或 option_chain。代码解析复用现有 coverage 标识规则。instrument 显式指定一个代码；其他 scope 必须传入带 trading_day、version、完整性声明的显式 Universe，按产品/月筛选并固定排序、去重。可从调用者保存的 manifest 加载清单，但绝不默认读取 universe/current，也不从行情行推断全部上市合约。完整性声明是参考数据来源声明，不声称 Raw 或本模块独立验证了交易所全量上市清单。

Universe 不完整时即使已知代码都有行情，frame 也不能 COMPLETE。输出 expected_count、observed_count、usable_count、missing/stale/invalid 计数；无 observation 为 EMPTY；清单完整且全部成员有有效且不过期 observation 为 COMPLETE；其余 PARTIAL。missing 成员仍占一个输出位置，observation=null。空 scope 也明确 EMPTY。完整链仅指所提供的完整清单中的所有 call/put/strike，不合成缺失行权价。

## 时间和选择规则（契约 v1）

- 输入为带时区 datetime，解释时区 Asia/Shanghai；微秒计算使用整数。主 observation 时钟是 Collector 的 received_us，而非不可可靠拼成时间戳的源 UpdateTime。保留 ActionDay、TradingDay、UpdateTime、UpdateMillisec、snapshot_us 和全部报价事实，不伪造交易所时间。
- point as-of 包含 received_us == as_of；分钟标签必须整分钟，代表 [minute, minute+1min)，在 minute 结束处取严格小于 end 的最后 observation。允许同一个连续区间内使用更早分钟的真实 observation，但必须保留原时间及 age；这是显式 as-of 选择，不是新报价或插值。
- 每个成员按 received_us DESC, id DESC 选一条。id 是该日唯一且跨 run 稳定的平局裁决，不比较跨 run sequence。最新行 invalid 时保留该行并报告问题，绝不退回较老的有效行。
- 必须限制在同一个 Calendar period 的 [start,end)，竞价/连续切换、午休、日夜切换均隔离。请求 day 必须匹配该 period 的逻辑交易日；分钟必须全部位于一个 period 中。休市/休息分钟和未知日历不可当作可重建的交易分钟。
- snapshot_us 可能晚于 minute end：本模型重建当前 Raw 中已保存的接收事实，不声称重现当时可见的数据库，不恢复未被15秒采样保留的 tick。
- sealed = 显式 evaluated_at >= minute end，仅表示分钟时间已结束。未封口分钟只选择到 evaluated_at（inclusive），age也以 evaluated_at 计算；evaluated_at 早于分钟开始则拒绝。Raw 无最终提交 watermark，sealed 不保证后续 Raw 不变。每次事务读取 max(id) 作为 raw_revision；可传回该上限重建同一 append-only 日文件切片。相同 Raw、scope（含版本）、calendar、时间、策略和 revision 得到相同输出；不读取隐含 now。外部覆写/删除旧行不在 append-only 保证内。

## 质量与 Latest

quote_age_us = age_reference_us - received_us；stale 当 age > 显式 stale_after_us（默认60秒）。MISSING、STALE、INVALID 独立表达；invalid 包括缺失/非有限/非正的一级买卖价、非正挂量、买价大于卖价以及不一致的行身份/物化时间。原值保留，不修改价格、不算 mid、不筛选出“好看的”旧行。LastPrice 可缺失，一级双边报价质量是本模块默认可用标准，不等于可计算 IV 的承诺。

Latest 必须传入 at。OPEN 使用当前 period 截至 at；刚开盘没有新 observation 就 MISSING，不继承上一段。BREAK/CLOSED 只返回最近已经结束的 period 的历史 frame，标记 historical=true、effective_as_of 为该 period end（exclusive），age_reference 仍是请求 at，因此休市时间会增加 age。不是把历史价格重新盖上当前时间；最新竞价也可作为历史 period，不误用 Calendar.latest_session 的仅连续时段定义。

Latest 分开报告 calendar_trading_day（CLOSED 常为下一交易日）和 frame 的实际 trading_day，调用方 Universe 必须匹配后者。UNKNOWN 不猜测时段，返回无 frame 的明确状态。缺文件/不可读沿用 QueryError 404/503，不能伪装 EMPTY，也不跨库搜索“有数据的旧日”。

## SQL、部署与不可破坏边界

一帧一个 Store.connect 只读事务，先读取 max(id)，逐成员用已有 snapshots_instrument_time 索引做有界 top-1 查询；绑定所有参数，不加 Raw 索引或表。清单最多10000成员，沿用3秒 SQL预算；超时明确失败。不建立 Derived SQLite，不写缓存/Raw/sidecar，不改变 Collector、runtime、日历规则或部署读写挂载。模块随 Query 镜像复制，不新增第三方依赖。

下游 IV Chain → Skew 获得有序 scope、原始 observation、时间、session、revision、quality、completeness；MO Skew v1按[已冻结下游契约](analytics-skew.md)筛选PARTIAL、age和报价有效性，不直接回到 SQLite；其他派生业务不得默认沿用为通用口径。本模块不实现 IV、Skew、Basis、定价或 Analytics；这些属于独立下游。

## 验证

使用临时真实 SQLite/WAL、固定时间及受控 writer，覆盖分钟、完整链、平局、质量、跨 session、夜盘、迟到/revision、只读和错误。入口为 `python3 harness/run.py offline`；业务计算另按[MVP 验收条件](../../docs/acceptance.md)验证。

审核 Skew 读取上下文可显式传 `MarketStateReader(..., calendar=已加载Calendar)`；一旦提供即固定使用该对象，默认目录读取行为不变。Calendar 支持从已核对哈希的原字节初始化。该注入只固定参考身份，不改变 as-of/minute/latest、session、age 或 revision 规则。
