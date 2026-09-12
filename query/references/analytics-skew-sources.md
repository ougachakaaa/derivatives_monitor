# Analytics / Skew v1 来源与决定依据

核对日期：2026-09-08。规范性决定在[Analytics 契约](../contracts/analytics-skew.md)，此处记录外部依据及其适用范围。只使用发布者/维护者一手材料，不把项目参数说成市场统一标准。

| 来源 | 支持的事实/方法 | 对本项目的决定 |
|---|---|---|
| [CFFEX MO 合约表](https://www.cffex.com.cn/zz1000gzqq/) | 中证1000指数标的、European、现金交割、指数点、0.2点tick、100元/点、月度挂牌与到期规则 | 元数据来自明确官方挂牌参数及规则，期权不是“IM期货期权” |
| [CFFEX 股指期权细则](https://www.cffex.com.cn/ssxz/20221214/43100.html)、[官方2022修订PDF](https://www.cffex.com.cn/u/cms/www/202207/1820311129r5.pdf) | 到期现金结算使用指数最后两小时平均值，竞价/连续时段分开 | v1 不计算到期日新IV/Skew；普通 Black IV 为统一估值近似，不是平均价期权精确模型 |
| [CFFEX IM 合约表](https://www.cffex.com.cn/zz1000/) | IM 掛牌为当月、下月及随后两个季月，与MO月份范围不相同 | 不强制依赖同月IM、不将IM当现货；从MO同月C/P平价估计F |
| [CFETS Shibor Code of Conduct](https://www.chinamoney.com.cn/r/cms/chinese/chinamoney/html/shiborOrg/sszzJieshao-e.html)、[官方发布入口](https://www.chinamoney.org.cn/chinese/bkshibor/) | 单利、无担保、年率百分数ACT/360、T+0，包含3M期限，通常11点发布 | 显式前一CFFEX日3M fixing；每天固定，ACT360单利折现；延伸至整个剩余期限是项目proxy，不是官方零息曲线 |
| [CME：CVOL Skew 与传统25Δ RR](https://www.cmegroup.com/education/courses/introduction-to-cvol/introduction-to-cvol-skew) | 25Δ两翼IV差为一种常见skew测量；Call−Put RR与本文符号相反，且两点指标不能描述整条曲线 | 明确命名 Put−Call Skew，并冻结单位/符号，不称CVOL或ATM归一化指标 |
| [QuantLib 1.40 发布](https://github.com/lballabio/QuantLib/releases/tag/v1.40)、[固定标签 Black formula 实现](https://github.com/lballabio/QuantLib/blob/v1.40/ql/pricingengines/blackformula.cpp)、[BlackCalculator](https://github.com/lballabio/QuantLib/blob/v1.40/ql/pricingengines/blackcalculator.cpp) | Black定价、平价、隐含标准差、forward偏导；由独立维护库提供数值对照 | 验证使用 QuantLib 1.40；返回stddev除√T，PV delta除D；生产采用独立二分实现，不能复用验证器作为生产求解器 |

部分 CFFEX HTML 直连超时，已通过官方搜索索引/同站PDF内容交叉核对；这不是当日真实挂牌清单或行情订阅验收。Shibor 本轮核对了规则，没有获取或声称某日具体 fixing 数值；入库数值案例均为 SYNTHETIC。每日运行仍须实际审核当日 ReferenceBundle。

没有外部来源规定本项目的：三对近ATM排名/中位数、0.1%一致性、30/5/15秒接收时间阈值、20%盘口价差、25Δ线性插值区间、σ范围、time value/vega门槛、flat 3M折现或验证误差。这些均由本次授权作为MVP策略冻结，变更必须升级契约。

资料与验证资产由 Query 自己的 references 与 tests 拥有，不移动 SDK 或修改 `experiments/`。参考摘要不替代原始来源；运行参考包须保存真实URL、发布/获取时间、原响应哈希与审核版本。验证环境依赖见[oracle requirements](../tests/analytics-oracle-requirements.txt)。
