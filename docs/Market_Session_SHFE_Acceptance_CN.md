# Market Calendar / Session 与 SHFE AU、AG 验收

实施：2026-09-07 夜间至 2026-09-08 早晨（Asia/Shanghai）。设计及独立任务见 [设计文档](Market_Calendar_Session_Design_CN.md)、[Task Specs](tasks/market-session/README.md)。

## 交付状态

**implemented；AU/AG 短时真实夜盘已验证；跨自然日与次日日盘的连续 live acceptance pending。**

- 2026 年审核参考日历，每交易所242个显式交易日；SHFE夜盘自然日期与逻辑交易日显式映射，覆盖法定假期、调休周末仍休市、节前取消夜盘、普通周五夜盘归属周一及跨00:00。缺失/损坏/未知年份不以工作日或自然日期猜测，返回UNKNOWN。
- 13个交易所/品种会话：原11个CFFEX产品，新增SHFE AU/AG期货。区分OPEN/BREAK/CLOSED/UNKNOWN、DAY/NIGHT、CONTINUOUS/AUCTION；CFFEX期权收盘集合竞价和国债时段独立处理。产品级时段不替代单合约有效期/国债到期日仅上午交易等特殊规则。
- 独立标准库CLI与 `/api/sessions`；多市场coverage和Dashboard，时段失败清空旧状态；市场是否开市与CTP健康、订阅失败、暂无推送分开表达。
- SHFE官方上市清单、夜盘目标日期、兼容v1 manifest与保留旧清单的原子发布。native仅扩充既有universe刷新时点，没有Session驱动的Collector自动启停。
- 对比此前15秒提交，`collector/src/` **没有变更**。源TradingDay分区、默认15000ms、callback、物化、SQLite schema、CTP生命周期和健康诊断不变。Python没有进入Raw SQLite写入链路。

## 官方清单实测

2026-09-07 23:26，隔离目录发现CFFEX当日714个、SHFE下一逻辑交易日20260908的AU 8个和AG 12个，共734个，complete=true。9月8日07:44重新获取当天两交易所来源，仍为734个，原11个CFFEX品种/数量完整保留。

| 市场 | 实际发布结果 |
|---|---|
| CFFEX | IF/IH/IC/IM各4，TS/TF/T/TL各3，IO 232、HO 166、MO 288；合计714 |
| SHFE AU | au2609、au2610、au2611、au2612、au2702、au2704、au2706、au2708 |
| SHFE AG | ag2609、ag2610、ag2611、ag2612、ag2701、ag2702、ag2703、ag2704、ag2705、ag2706、ag2707、ag2708 |

来源：[CFFEX 20260908 XML](http://www.cffex.com.cn/sj/jycs/202609/08/index.xml)、[SHFE 20260908 ContractBaseInfo](https://www.shfe.com.cn/data/busiparamdata/future/ContractBaseInfo20260908.dat)，均HTTP200。SHA-256分别为 `388baca46210c2e3401c15a42403f23a33e9302a02678d0cefc44b7167e818fe`、`ffeee3e949d69c2684862506ad6bc1d9142feb5f749b6df06429234b0c8f1bcf`。

9月8日原始请求、响应和manifest保存在被Git忽略的 `collector/tmp/market-session-acceptance/reference/`。只获取公开合约参考数据，不把其中的价格当CTP行情。没有更改实际运行配置、发布到生产data目录或接管现有服务。

## 真实夜盘观测

9月7日使用仓库记录的 `tcp://61.186.254.135:42213`、BrokerID 9080、示例空行情账号，选择刚验证上市的 `au2610`、`ag2610` 及对照 `IF2609`，正式SDK写入隔离临时目录。初次使用旧构建登录超时；同步重建当前源码后成功，未为此修改生产代码。

实际成功run为 `04ee5d6b039fc01903467820e203561a`，SDK来源 `CTP v6.7.13_20260225 14:16:30.12079`，snapshot_interval_ms=15000。运行日志和只读SQL在当时确认：

- connected=1、logged_in=1、expected=3、subscribed=3、subscription_failed=0。
- AU/AG接收计数从各40增长到各61；稍后全局accepted=258、written=8，仍处于running。IF订阅成功但夜盘无推送；这不是订阅失败。
- 约每15秒提交2行，数据库为 `20260908.sqlite`。一次只读统计中AU/AG各4行，源ActionDay均20260907，UpdateTime从23:34:32推进至23:35:18。
- 当时AU received_us范围1788795272371391–1788795317766220，AG为1788795272368013–1788795317764530；snapshot_us范围1788795272747687–1788795318015347。源交易时间、本地接收及物化时间保留为不同字段。

上述是当时工具实际读取的摘要，不是synthetic结果，也不意味着所有账户都有SHFE权限。次日环境重启后 `/tmp/dm-shfe-live-sveih63x` 与进程句柄已消失，原始临时库/日志不能再复查；不声称已观察到最终正常退出、整夜不断线或跨零点延续。后续持续验收应使用持久的本机证据目录。

## 自动化验证

| 验证 | 结果 |
|---|---|
| 原生C++ | Release构建、7项CTest全部通过；包含真实33秒默认采样测试、源字段/状态、WAL、单writer、失败、重连/重新订阅、SIGTERM与SIGKILL恢复。现存CTest日志保存在build目录。 |
| 日历/Query | 22项通过；涵盖时区、节假日、夜盘与时段边界、集合竞价、未知/坏日历、只读接口、SHFE夜盘目标日期及原有coverage/健康。Docker构建阶段亦执行此套测试。 |
| Universe | 9项通过，含官方代码与日期验证、空/坏/失败/截断来源、保留旧合约、原子发布、重启补偿与显式日期。 |
| 部署/验收器 | 9项部署脚本测试、4项实际SQLite CLI只读验收测试通过。 |
| Dashboard | 7项组件测试与生产构建通过。 |
| 原生浏览器闭环 | Chromium实际React渲染/HTTP/网络失败恢复/移动布局通过；C++→SQLite→FastAPI独立停启、重启追加、SIGKILL心跳过期通过。 |
| 新增夜盘闭环 | `tests/night_session_smoke.py`通过，测试SDK驱动真实C++ writer，AU/AG 21:00→23:59→00:00→02:29→09:00→14:59→下一夜盘；同源TradingDay不换库，下一真正TradingDay才换库，CFFEX共存，重连、正常停止及第二个run追加、三类时间、WAL完整性和只读Query均通过。 |
| Collector容器 | `collector/tests/docker_smoke.sh`通过：独立镜像、合成采集、只读验收、重启/停止、持久数据；日志在 `collector/tmp/market-session-acceptance/collector-docker.log`。 |
| 三容器闭环 | 9月8日Docker Engine可用后实测通过：三镜像构建、healthcheck、Nginx API代理、只读共享WAL、独立停启、正常退出与重建保留数据。日志在 `collector/tmp/market-session-acceptance/read-path-docker.log`。 |

合成夜盘测试显式100ms加速源时间序列，生产默认15秒另由CTest覆盖；不把合成源日期作为真实跨午夜证据。切换到新日后旧日若已关闭且无sidecar，运行中的Query仍按既有规则返回503；正常停止后才能在共享锁保护下读取。没有放松只读/WAL约束。

## 夜盘八项验收逐项状态

1. 21:00以后真实接收：已在23:34–23:35观察AU/AG持续callback；21:00开盘瞬间待持续现场观测。
2. 真实跨00:00不停机：pending；合成源时钟跨界已通过。
3. 00:00不误切SQLite：合成已通过，真实连续运行pending。
4. 夜盘前后同一正确TradingDay：真实零点前已为20260908；零点后连续证据pending，合成已通过。
5. 次日日盘写同一交易日：合成已通过，真实连续证据pending。
6. 真正新TradingDay才换日库：合成已通过，真实连续证据pending。
7. Query读取夜盘和日盘：实际C++合成数据通过；完整真实夜盘/日盘数据集pending。
8. 源/接收/物化时间区分：真实零点前与合成跨界均通过。

## 补验操作

在有有效配置的真实部署上刷新经过验证的AU/AG清单，确认 `SnapshotIntervalMs=15000`，使用正常运行配置和原数据目录。不要从月份规则生成合约、改写源TradingDay或加载测试SDK。对新的独立实测目录，应使用持久目录，避免放在会随环境重启清理的 `/tmp`。

至少连续覆盖交易所日历确认的夜盘21:00、23:59、00:00、02:30、次日日盘及下一真正TradingDay；每个检查点保留run ID、订阅/接收/提交计数及只读SQL时间字段、文件身份。普通周五夜盘属于周一，节前取消夜盘必须以参考日历与最新交易所公告复核。只读查询活跃库采用mode=ro和短事务；旧日无sidecar遵循现有停止后读取规则。

日历支持范围为2026，跨年必须先审核发布新年日历；未知时不自动推断、不阻断Collector。需要变更时段参考时按 [年历更新说明](../query/calendars/README.md) 更新，Collector仍独立运行。本阶段没有新增Scheduler、Analytics或告警。
