<a id="query-design-rationale"></a>

# Query 设计取舍

本文件只解释 Query 内部选择；跨模块原则见[根 Design](../DESIGN.md)，当前文件关系见[本级 Architecture](ARCHITECTURE.md)，精确行为见[本级 Contracts](CONTRACT.md)。

## 按请求计算可重建派生值

单月 Skew MVP 在 Query 内按请求计算，不预先建立第二份权威派生库或常驻指标调度器。Market State、输入 revision、参考版本和算法身份使同一输入可重放；未来缓存或物化若有必要，仍须可重建、可失效，且不能成为新的 Market Facts 来源。

## 复用既有 Analytics 的薄 Feature provider

Query 已有受约束的 Market State、数值核心和 Skew business service，因此 Feature provider 只做稳定公共结果的薄投影，避免维护第二套金融口径。它不引入动态插件、通用计算图或后台指标调度；新指标本身也不触发拆包。共享 HTTP/Feature 语义与提取独立 Analytics 包的触发条件仍由[根 Design](../DESIGN.md#9-以稳定语义共享-analytics按实际需要拆模块)负责。
