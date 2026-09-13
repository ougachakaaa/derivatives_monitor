<a id="query-design-rationale"></a>

# Query 设计取舍

本文件只解释 Query 内部选择；跨模块原则见[根 Design](../DESIGN.md)，当前文件关系见[本级 Architecture](ARCHITECTURE.md)，精确行为见[本级 Contracts](CONTRACT.md)。

## 按请求计算可重建派生值

单月 Skew MVP 由同一 Query 进程调用 Analytics 按请求计算，不预先建立第二份权威派生库或常驻指标调度器。Market Frame、输入 revision、参考版本和算法身份使同一输入可重放；未来缓存或物化若有必要，仍须可重建、可失效，且不能成为新的 Market Facts 来源。

## 复用既有 Analytics 的薄 Indicator provider

Query 通过 Data Provider 和 Analytics 取得受约束的 Market Frame 与 Skew 结果，因此 Indicator provider 只做稳定公共结果的薄投影，避免维护第二套金融口径。它不引入动态插件、通用计算图或后台指标调度。共享 HTTP/Indicator 语义与源码包边界仍由[根 Design](../DESIGN.md#10-以稳定语义共享-analytics按实际需要拆模块)负责。
