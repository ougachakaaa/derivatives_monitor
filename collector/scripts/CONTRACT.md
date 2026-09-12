<a id="universe-tool-contract"></a>

# Universe tool 长期契约

本契约只定义 `collector/scripts/universe.py` 自身拥有的来源抓取、校验、保留和发布行为。Calendar/Universe 的跨模块版本、日期交接与消费者语义见共享 [Market Session Contract](../../docs/contracts/market-session.md)；系统服务管理见 [Deployment Contract](../../docs/contracts/deployment.md)。

## 能力边界与来源

- 工具按 [MVP](../../docs/mvp.md) 的采集范围保留 CFFEX 现有产品与 Sina fallback，并覆盖 SHFE AU/AG 期货；拒绝 SHFE 期权及其他商品。SHFE 使用官方 ContractBaseInfo 日期接口；工具不把来源中的价格写入持久行情。
- CFFEX 保持既有清单刷新日期口径；SHFE 使用共享 Calendar 给出的当前/下一逻辑交易日，支持夜盘前发布的次日清单。`--date` 显式指定时两交易所均按该日期查询。缺失 Calendar 时保留旧 SHFE 清单并明确失败，不靠自然日期猜测夜盘归属。
- 来源代码、来源日期、上市日、到期日与产品类型严格验证；SHFE 精确代码为小写 `au` / `ag`。

## 保留、发布与失败

- manifest v1 保留 `products` 键，并记录 exchange、各产品 requested day、来源、完整性和 stale/error 状态；每个产品的已发现精确代码去重。具体字段的跨模块解释由共享 Market Session Contract 拥有。
- SHFE 来源失败或部分返回时按产品保留未到期旧代码并标记 stale/未完整确认；初次 SHFE 无可用代码不能伪装完整覆盖，已有 CFFEX 清单继续可用。
- 全量空清单拒绝发布并保留现有清单。可用结果沿用锁保护和原子 generation 切换；失败必须明确记录。
- 只有已发布合约集变化、活跃 Collector 的订阅集与清单不一致，或已有订阅诊断无法解析时，才请求正常重启指定的活跃 Collector。工具不依据 Market Session 启动或停止 Collector，也不成为 C++ 运行时依赖。

## 验收边界

解析、来源日期、部分失败、旧代码保留、原子发布和重启判定可用明确的 TEST DOUBLE 离线验证。真实 SHFE 清单成功与真实行情权限分别验收；合成来源或时钟不能替代实盘记录，当前证据见[根 Acceptance](../../docs/acceptance.md)。
