<a id="analytics-skew-contract"></a>

# MVP Analytics / Skew contract v1

状态：**FROZEN**，2026-09-08；契约 ID `mo-skew-25d-v1`。本文件冻结七项设计，机器常量见[策略文件](analytics-skew-v1.json)。这是当前单月 Skew MVP 的唯一 Analytics 定义；实现与验证状态见 [Analytics Acceptance](../ACCEPTANCE.md)，系统门槛见[根 Acceptance](../../docs/acceptance.md)。共享 [Indicator 查询](../../docs/contracts/indicators.md)复用本契约，不改变任何冻结数值或质量要求。

| 决定 | v1 选择 |
|---|---|
| Skew definition | `100 × (IV_25Δ_put − IV_25Δ_call)`，单位 vol point（波动率百分点） |
| Pricing model | 无 displacement 的 Black-76；年化 lognormal IV；European premium-style 折现价格 |
| Underlying semantics | 同一 MO 到期月三个近 ATM C/P 对的平价隐含远期，中位数聚合；不是现货或 IM 报价 |
| Reference parameters | 官方已验证合约/到期日与产品规则；前一 CFFEX 交易日 3M Shibor；显式版本化日参考包 |
| Quote synchronization | 已封口的连续交易分钟；最新真实 bid/ask midpoint；age≤30秒；C/P差≤5秒；最终所有输入跨度≤15秒 |
| IV solver contract | 有界二分法，σ∈[0.0001,5]、最多128轮，同时满足σ区间和回代价格精度；失败不夹值 |
| Independent validation | 固定 QuantLib 1.40 外部 oracle、mpmath 1.3.0 高精度价格对照、入库数值向量；生产后续另做真实10时点对账 |

## 1. 范围与边界

仅 `CFFEX / MO / 一个显式 YYMM`，同一 expiry 的完整上市清单。用户显式选月，v1 不自动换月、不混月、不拼期限曲面。清单须完整且当天已验证；Raw frame 可以 PARTIAL，只有本契约所需输入全部合格才产出 Skew。缺失其他合约仍报告缺口，不能将 PARTIAL 改为 COMPLETE。

只消费 [Market Frame v1](../../data_provider/contracts/market-frame.md) 的 `option_chain` frame 与独立参考包；不直接访问 SQLite，不改变 Collector、Raw schema、15秒物化、日历、部署或 `experiments/`。派生值按请求在 Python 计算，不写 Raw 或 Derived SQLite，不把计算放进浏览器。现有 Market Frame 的 `usable` 不是 IV 保证。

## 2. 数学定义与单位

所有期权价格、F、K 都是指数点，乘数100仅作产品元数据，不乘进 IV 定价。σ 为年化小数（0.25=25%）。T 使用到期时刻与估值时刻间的真实秒数 / (365×86400)，包括周末、假日和午休；不按交易分钟年化。

令 `t=frame.effective_as_of`（分钟 end，报价 cutoff 仍严格小于 end），`E=expiry_at`，`s=E−t` 的秒数：

```text
T      = s / (365 * 86400)
tau360 = s / (360 * 86400)
D      = 1 / (1 + L * tau360)
r_eff  = log1p(L * tau360) / T
w      = sigma * sqrt(T)
d1     = log(F/K)/w + w/2
d2     = d1 - w
C      = D * [F*N(d1) - K*N(d2)]
P      = D * [K*N(-d2) - F*N(-d1)]
vega   = D * F * phi(d1) * sqrt(T)
```

`N` 为标准正态 CDF，`phi` 为其密度。D 由 §4 定义的 Shibor 单利代理得到，与 `exp(-r_eff*T)` 相同；不得再按另一利率重复折现。无单独 q 输入，`dividend_yield=null` 表示 carry 已包含在隐含远期中，不代表市场分红率为零。

25Δ 的 delta **明确采用未折现、未作 premium adjustment 的 forward delta**：call=`N(d1)`，put=`N(d1)−1`。它等于价格对 F 的偏导除以 D；不是 spot delta，也不是折现后的 PV forward delta。目标分别 +0.25、−0.25。

```text
skew_25d_vp = 100 * (sigma_put_25 - sigma_call_25)
```

正值代表看跌翼 IV 高于看涨翼；0.30−0.25 输出 **+5.0 vol points**，不是0.05、500bp或5%的相对涨幅。本指标命名“25Δ Put−Call Skew”；不得仅标“Risk Reversal”，因为常见 Call−Put RR 的符号相反。v1 不做 ATM 归一化。

### 两翼插值

使用 §5 合格且 §6 求解成功的真实合约。Put 仅取 `K<F`，Call 仅取 `K>F`；排除 `K=F`。以 `x=abs(forward_delta)` 为坐标，只保留 `0.10≤x≤0.40` 的节点，边界比较容差1e−10。

按 K 排序，在该翼保留节点中，put 的 x 应随 K 非减，call 的 x 应随 K 非增；逆向超过1e−10时该翼失败 `NON_MONOTONE_DELTA`，不拟合或修正异常笑脸。去重时先按(x,K,instrument ID)排序，以尚未分组的最小x为锚，距锚≤1e−10的节点组成一组；组内保留K最小、再instrument ID字典序最小者，随后处理下一组，输出被舍弃身份。

有 `|x−0.25|≤1e−10` 的真实节点直接使用（多个时按 `abs(x−0.25),K,instrument ID` 排名取首个）；否则选择最大的 `x_lo<0.25` 和最小的 `x_hi>0.25`。必须两端存在且 `x_hi−x_lo≤0.10+1e−10`，线性插值 **σ 对 x**：

```text
alpha = (0.25 - x_lo)/(x_hi - x_lo)
sigma_25 = (1-alpha)*sigma_lo + alpha*sigma_hi
```

不按 K/variance 插值、不外推、不增加合成报价。输出两端代码/K/σ/x/权重；没有两翼就 `skew_25d_vp=null`，不拿单边、最近 delta 或前一分钟代替。统计完整性与 Skew 是否可计算分开。

## 3. 隐含远期的唯一算法

MO 的法律标的是中证1000指数；v1 的估值输入是该到期月的**期权平价隐含远期**。它是派生估计，包含市场 carry/供需/报价误差，不声称观测到现货、真实无套利远期或可交易期货价。

1. 从同一个 frame 的 latest observations 中组成同 K、同到期日的 C/P 对。两条都须满足 §5 的基础报价条件，且 received_us 差≤5,000,000。
2. 按 `(abs(C_mid−P_mid), K, call_id, put_id)` 升序选 **前三个不同 K**；不足三个返回 `FORWARD_PAIRS_MISSING`。这是确定的近 ATM 代理选择，不需要先有现货或 IM。
3. 六条报价整体 received_us 跨度须≤15,000,000，否则 `FORWARD_UNSYNCHRONIZED`。不更换旧 observation 或搜索其他三元组来掩盖失败。
4. 各对 `F_i=K+(C_mid−P_mid)/D`。三个 F_i 均须正且有限；`F=median(F_i)`。每个 `abs(F_i−F)/F≤0.001`，否则 `FORWARD_INCONSISTENT`。阈值是项目质量策略，不是交易所规则。
5. 输出三个 K、六个 observation ID、mid、F_i、选取排序依据、最大偏差和时间跨度。三个对可能与最终翼节点重合，来源按 observation ID 去重。

不回退到 IM、其他月份、LastPrice、现货猜值或昨日 F；不同时估计 D 与 F，不增加平价回归模型。选用同一 MO frame 避免跨产品读取混合 revision，也不受 IM 与 MO 挂牌月份不完全重合的限制。平价计算不需要先求 IV，不形成循环依赖。

## 4. 参考参数与可重放性

运行值随交易日变化，冻结的是来源、单位、取值规则和有效性，不是把今天的利率永久硬编码。生产计算必须显式传入经审核的 `ReferenceBundle`，不得在请求中联网抓取，缺包不启用默认数值。

| 字段组 | 必需内容与拒绝条件 |
|---|---|
| 身份 | `schema_version=1`、`bundle_id`、外部manifest记录的原文件字节 SHA-256（不在文件内自哈希）、`valid_trading_day`、`exchange=CFFEX`、`product=MO`、`month`、`reviewed_at`、审核记录、`source_kind=OFFICIAL` |
| 合约 | 与 frame 相同的不可变 Universe generation/哈希；每个成员的精确代码、C/P、正数 K、官方 `END_TRADING_DAY`；同月所有 expiry 一致，K/C/P可从官方已列出的精确代码读取，再与参考包校验；不从代码或月份规则猜上市/到期日、不生成候选合约 |
| 产品规则 | `underlying_index=CSI1000`、European、cash settlement、CNY、指数点、tick=0.2、multiplier=100、规则来源 URL/版本/哈希；变化需新契约版本 |
| 到期 | `expiry_at=官方最后交易日 15:00:00+08:00`；来源为审核的当日官方挂牌参数与产品规则。假日顺延以实际挂牌日期为准，不自行算第三个星期五作为权威 |
| 日历 | 显式 Calendar 版本/哈希，版本必须与 frame 一致；未知日历、无法确定前一交易日均拒绝 |
| 利率 | CFETS/中国货币网/官方 Shibor 发布的 **3M 单利年率**；原始百分数、`L=百分数/100`、fixing_date、published_at、URL、原响应 SHA-256、retrieved_at、期限/ACT360/T+0 元数据 |

固定使用 `fixing_date=valid_trading_day 的前一个 CFFEX 交易日` 的官方 3M fixing，当天所有分钟都用同一记录，不在11点切换。published_at 必须早于当天09:00；找不到该精确日期的记录就 `RATE_MISSING`，不再回退更老记录。长假前一交易日的 fixing 按此规则合法，不靠自然日 age 任意剔除。缺失 source/审核/哈希、错日期、单位矛盾均 `REFERENCE_INVALID`。L须有限且在[−0.05,0.20]，`1+L*tau360>0`；范围外拒绝而不截断。

**固定折现约定**：将该 3M fixing 作为整段剩余期限的 flat simple ACT/360 代理，按 §2 计算 D；不做期限匹配插值、曲线 bootstrap 或连续复利误读。Shibor 是无担保银行间利率，并非无风险零息曲线；将其延伸到任意 MO 期限是本项目明确的 MVP 估值近似，输出 `discount_convention=SHIBOR_3M_FLAT_SIMPLE_ACT360`，不称“官方风险中性 IV”。

允许 `0<T≤1`；**到期日当天全部停止新 IV/Skew 计算**，返回 `EXPIRY_DAY_UNSUPPORTED`，到期时刻及之后 `EXPIRED`。原因是股指期权交割基于指数最后两小时平均值，v1 不建立平均价期权模型；到期日前的 Black IV 也只是统一报价约定。历史查询按历史 t 判断，不能用今天的自然日期拒绝过去有效分钟。

参考包布局、不可变导入、选择文件、原字节哈希核对、固定 Universe/Calendar 读取上下文及重放身份见 [ReferenceBundle adapter Contract](references.md)。数值核心仍只读 frame/参考输入，不读取 Raw 或参考文件。

## 5. 分钟、质量与同步

### 时间入口

数值核心只接受 `kind=minute, sealed=true, session.phase=CONTINUOUS` 的完整单分钟 frame。`valuation_at=effective_as_of=minute_end`；请求的当前时间另作 `requested_at`，不得改变 T 或历史报价的计算 age。尚未封口返回 `MINUTE_UNSEALED`；竞价、跨 period、错 day、UNKNOWN 分别明确拒绝，不改 Calendar/Market Frame 语义。

产品“最新值”选择规则也冻结：连续交易中只选**当前 period 最近已结束的整分钟**，首分钟未结束返回 `WAITING_FOR_MINUTE`；BREAK/CLOSED/竞价时，选日历上最近结束的连续交易分钟，输出 `historical=true`。这是按日历定位，不是查找有数据的旧分钟；所选分钟缺数据就失败，不再后退。调用 `reader.minute(..., evaluated_at=requested_at, stale_after_us=30000000)`，不消费或重写 `reader.latest()` 的盘后陈旧标志。

历史数值的输入 age 始终以历史 minute_end 计算；结果另给 `display_age_us=requested_at−valuation_at`、`historical` 和 `current_usable=false`，不能把历史有效数据当当前新报价。交易中正常返回最新封口分钟时，current_usable 还要求非历史、display_age≤60秒且所有实际使用报价相对requested_at的age≤30秒。数值有效但当前报价已陈旧时保留分钟结果并设current_usable=false。对应页面标识和失败清值由 [Dashboard Contract](../../dashboard/CONTRACT.md#dashboard-skew-contract)定义。P2仍需独立测量首次计算/显示时刻，封口等待与late Raw可见性不能从延迟统计中删除。不新增定时器/常驻缓存。

### 基础报价筛选

每个合约只使用 frame 已选择的真实 observation，不回查更老报价。以下全部满足才可作为平价或翼候选：

- observation 存在，Raw/Market Frame 身份正确、invalid=false；`0≤minute_end_us−received_us≤30,000,000`。不修改 frame.quality，也不把比30秒宽的通用 usable 当通过。
- bid/ask 正数且有限、bid≤ask，BidVolume1/AskVolume1 是正整数（至少1手）；不使用 LastPrice、结算价或挂量加权价。
- 报价符合0.2点格：`abs(price−round(price/0.2)*0.2)≤1e−8` 点；不替原报价取整。源 null、NaN/Inf、极大无效值仍无效。
- `mid=(bid+ask)/2≥1.0` 点，`(ask−bid)/mid≤0.20+1e−12`。mid 可为0.1点格，不强行按交易tick取整；不要求盘口每分钟有新 callback。
- 所有参考身份/期权类型/strike/expiry 与 bundle、scope 一致，revision 来自同一 frame。

基础剔除原因固定为 `MISSING, INVALID_IDENTITY, INVALID_BOOK, INVALID_TICK, PRICE_TOO_SMALL, SPREAD_TOO_WIDE, NEGATIVE_AGE, STALE_QUOTE`，一条可有多个原因，按上述阶段检查并输出去重排序结果；Market Frame原始flags/reasons另字段保留。

平价三对冻结后，对其余翼候选增加“该 observation 与平价六条合并跨度≤15秒”的筛选。最终实际使用的平价六条和左右翼插值端点（去重后最多10条）仍须整体跨度≤15秒；失败 `INPUTS_UNSYNCHRONIZED`，不重新选另一组。边界30秒/5秒/15秒均包含等号，使用整数 received_us 判断；不拿 snapshot_us/source UpdateTime 代替。

以上只保证**本地接收时间上的有界同步**，15秒采样无法恢复完整 tick，也无法证明交易所层面同时报价。输出 observation_clock、每条 received/snapshot/source时间和最终跨度。单翼 IV 失败可以保留诊断，但不产出 Skew；缺不相关成员可以产出明确 `PARTIAL_INPUT` 的合格 Skew。

## 6. IV solver

输入为 `side,F,K,T,D,mid`，全部有限；F/K/T/D 正且遵守上文范围。价格边界 `lower=D*max(sign*(F−K),0)`，`upper=D*(F if call else K)`；mid必须严格在(lower,upper)内，且 `mid−lower>0.1` 点。越界 `PRICE_OUT_OF_BOUNDS`；边界内但时间价值≤0.1为 `TIME_VALUE_TOO_SMALL`。不允许价格夹到边界、强行σ=0或返回上次 IV。

- 求年化σ，闭区间 `[0.0001,5.0]`；两端模型价格不能包住 mid 时 `IV_OUT_OF_RANGE`，不扩大区间。
- 纯二分，无 Newton 初值/随机或外部缓存。CDF 使用 `0.5*erfc(-x/sqrt(2))`；ITM 可用平价转换为对应 OTM 价格求解，作为数值恒等变换，不改市场输入。
- 每轮取 bracket 中点，价格较低更新下界，否则上界；即使浮点价格恰等也继续收窄 bracket，同时满足 **bracket宽≤1e−8** 和 **回代误差≤max(1e−8,1e−10*max(F,K))点** 才成功，最多128次价格迭代。输出σ、回代价格/误差、迭代数、最终 bracket。
- 解处 vega 必须≥1.0 指数点/单位σ（不是每1 vol point）；否则 `LOW_VEGA`。非有限中间值 `NUMERICAL_ERROR`，未同时达精度 `IV_NOT_CONVERGED`。
- 计算使用 float64，逻辑输出与 JSON 保留完整值；任何显示精度都不能反向用于插值或变化计算。

## 7. 输出、错误及当日变化

逻辑输出契约（HTTP 入口与投影另见 Read Path）：`schema_version=1, contract_id, algorithm_version, status, reasons[], scope, valuation_at, requested_at, historical, current_usable, reconstructed, display_age_us, raw_revision, universe/calendar/reference身份, input_completeness, expected/observed/eligible counts, F及三对明细, L/T/D/r_eff, wings, skew_25d_vp, provenance[]`。每个 provenance 含 day/id/run_id/received_us/snapshot_us/source time、mid、剔除原因或使用角色；不可计算为 JSON null，禁止 NaN/Inf、空字符串或0冒充失败。

`status=OK` 或 `UNAVAILABLE`；OK 仍可带 PARTIAL_INPUT，历史标识单独保留。参数类型/必需结构缺失或非MO scope 抛 `ValueError`（HTTP适配为400）；结构完整但参考缺失/不匹配、质量或业务前提不满足时返回 UNAVAILABLE 与对应reason，不另造成功结果；Data Provider 的缺失/不可用错误继续由 Query 映射为 404/503，不转成 EMPTY 或普通缺翼。

确定处理顺序：输入结构/参考身份 → 日历/分钟封口/expiry → 基础报价 → forward → IV → 两翼/最终同步 → Skew。收集阶段内全部原因，按 instrument/reason 排序；前置阶段失败不执行后续阶段。保留原始质量字段和剔除计数。常见状态包括 `REFERENCE_INVALID, RATE_MISSING, UNIVERSE_INCOMPLETE, MINUTE_UNSEALED, UNSUPPORTED_SESSION, WAITING_FOR_MINUTE, EXPIRY_DAY_UNSUPPORTED, EXPIRED, FORWARD_PAIRS_MISSING, FORWARD_UNSYNCHRONIZED, FORWARD_INCONSISTENT, PRICE_OUT_OF_BOUNDS, TIME_VALUE_TOO_SMALL, IV_OUT_OF_RANGE, LOW_VEGA, IV_NOT_CONVERGED, NUMERICAL_ERROR, NON_MONOTONE_DELTA, WING_UNBRACKETED, WING_GAP_TOO_WIDE, INPUTS_UNSYNCHRONIZED`；不把失败变成成功数字。

当日序列只枚举该交易日连续时段已封口分钟，竞价/午休留空；每个分钟独立计算，失败保留缺口，不 forward-fill。一次序列请求固定同一个日库 revision、同一 Universe/Calendar/参考包，所有逐分钟读取显式传该 revision。首个 frame 取得 revision 后其余固定，不直接读 Raw MAX(id)。“当日变化”为当前有效值减去同日首个有效分钟值，标出基准时刻；无基准则null，不暗中使用昨日收盘。页面切月行为见 [Dashboard Contract](../../dashboard/CONTRACT.md#dashboard-skew-contract)。

## 8. 独立验证与收尾门槛

本节是实现的硬门槛，不允许实现后放宽误差使其通过。

1. **独立数值 oracle**：QuantLib **1.40** 的 `blackFormula` / `blackFormulaImpliedStdDev`（返回σ√T，需要除√T），以及 `BlackCalculator.deltaForward()/D`；不把 futures premium式定价误配成不折现 payoff。验证环境独立于 Query，不新增生产依赖。源码以 v1.40 标签和[来源记录](../references/analytics-skew-sources.md)定位。
2. **高精度交叉核对**：mpmath **1.3.0**、80位精度正态积分表达式，验证 oracle 价格/平价；生产求解器不得 import oracle 或验证实现，也不得由生产实现重写 expected。入库[固定数值样本](../tests/fixtures/analytics-skew-v1.json)带 SYNTHETIC 标签、版本/生成器/策略哈希。
3. **提前冻结误差**：单价回代采用 §6；对 oracle 单合约 IV 绝对差≤1e−7（σ小数）、forward delta差≤1e−8、F差≤1e−6点、翼插值IV差≤1e−7、Skew差≤2e−5 vol points。相同输入的选中合约、排除原因、null/status、revision/参考身份必须完全一致。适用本契约可解且vega合格的输入，异常样本按状态对账，不把oracle能算出数字作为放行理由。
4. **必测场景**：平坦笑脸Skew=0、put翼高/低与符号/单位、非零/负利率ACT360、T的ACT365、C/P平价远期、三对不足/偏离、两翼不跨25Δ/跨度过宽/非单调、30s/5s/15s等号与超1μs、交叉/零量/错误tick/宽spread/小价格、时间价值边界、σ上下界/低vega/迭代失败、缺参考/错日期/单位、未知日历、竞价/首分钟/午休历史展示、到期日拒绝、固定revision重放及PARTIAL输入。生产实现必须补齐这些行为测试；数值向量不能替代它们。
5. **真实独立对账**：至少10个不同估值时点，至少6个可计算（含put翼较高及非平坦情况），至少4个异常/不可用；真实市场未自然出现的异常可对真实frame复制件定点扰动，单列 SYNTHETIC_MUTATION，不宣称实盘异常。固定输入包、使用独立 QuantLib/独立选择脚本或人工表格复算；至少一个完整链逐项核对三对选择/翼端点/权重/时间跨度。真实现场样本必须由真实行情提供，不能以合成向量充数。

契约冻结只证明公式和基准内部一致、决定可实现，不替代真实业务验收。当前 Analytics 实现与工程证据见[本级 Acceptance](../ACCEPTANCE.md)，G1–G6/P1/P2 见[根 Acceptance](../../docs/acceptance.md)；独立 oracle、合约选择及规则的测试映射见[Repository Verification](../../tests/README.md)。

## 9. 变更规则与依据

改符号、delta convention、模型/forward来源、利率/年化规则、同步/质量阈值、插值、求解边界或验证容差，都需要新 contract_id/策略版本和新 oracle 样本，更新 MVP/验收矩阵；不能原地改v1重算历史而仍声称同版本。每日官方利率/清单更新只增 ReferenceBundle 版本，不改契约。

[外部依据与项目选择](../references/analytics-skew-sources.md)明确分开官方合约事实、Black/平价数学和本项目阈值。官方没有为本项目规定“25Δ Put−Call”、三对中位数、Shibor flat proxy 或同步阈值；这些是本次授权冻结的工程/估值决定。

## 10. 数值核心接口

`calculate_skew(frame, reference_bundle, requested_at, historical=...)` 的依赖只有单个 Market Frame v1 MO option-chain minute frame、显式日参考包、请求时间与调用方按 Calendar 判定的历史标志；它不打开 Raw SQLite、不读取可变 `current`、不联网、不写 Derived SQLite，也不启动后台任务。

参考包的对象字段按§4表格落为：顶层 `schema_version/bundle_id/bundle_sha256/valid_trading_day/exchange/product/month/reviewed_at/review/source_kind/expiry_at`；`universe.version/sha256/instruments[]`，每个合约含 `id/side/strike/expiry`；`calendar.version/sha256/previous_cffex_trading_day`；`product_rules` 含产品事实、`source_url/source_version/source_sha256`；`rate` 含原始 `percent`、换算后 `decimal`、fixing/publish/retrieve/source 身份及计息元数据。必需结构缺失抛 `ValueError`，完整但不匹配返回 `UNAVAILABLE`。`SYNTHETIC` 只在 review 明确含 `TEST DOUBLE` 时接受。

结果除§7字段外，将冻结的模型、delta、插值、报价阈值和 solver 常量放入 `algorithm`，并在 `reference` 给出 bundle、Universe、Calendar、产品规则与利率来源哈希。`provenance` 为每个 scope 成员保留 TradingDay、observation/run ID、received/snapshot/source time、bid/ask/mid、原 Market Frame quality、剔除原因、使用角色与 solver 详情；`excluded_count` 与 `eligible_count` 分开。错误不复用旧报价、旧 IV 或旧 Skew。

实现和回归证据只见[本级 Acceptance](../ACCEPTANCE.md)，不能由本接口规范推断生产或实盘验收状态。
