# CFFEX 全量采集与 Windows 8101 验收

> 历史验收快照：仅证明文中日期/版本/环境下的观察。旧端口、临时路径、待验状态和操作命令可能已过时；当前设计见[文档入口](../../README.md)，当前门槛见[验收矩阵](../../acceptance.md)，运行见[操作说明](../../operations.md)。原始日志缺失时仅作为历史摘要。


2026-09-07，北京时间约 13:18–13:23，在当前 WSL 完成原生服务切换及真实 CTP 验收。不是合成行情验收，也不代表 Docker 已部署。

## 实际结果

合约来自中金所当日官方交易参数：
[20260907 挂牌参数 XML](http://www.cffex.com.cn/sj/jycs/202609/07/index.xml)。代码、品种、月份、上市日与最后交易日均来自响应；期权校验各月份各行权价的看涨/看跌配对。本次官方来源完整，未使用新浪补充。

| 品种 | 官方清单 | 订阅成功 | 收到过行情 |
|---|---:|---:|---:|
| IF | 4 | 4 | 4 |
| IH | 4 | 4 | 4 |
| IC | 4 | 4 | 4 |
| IM | 4 | 4 | 4 |
| TS | 3 | 3 | 3 |
| TF | 3 | 3 | 3 |
| T | 3 | 3 | 3 |
| TL | 3 | 3 | 3 |
| IO | 232 | 232 | 232 |
| HO | 166 | 166 | 166 |
| MO | 288 | 288 | 288 |
| 合计 | **714** | **714** | **714** |

覆盖 28 个期货、686 个期权，共 46 个品种/月分组。当次检查的订阅失败、未发送、等待确认、未收到过行情合约均为 0。后续不活跃或休市导致无新推送，应与订阅失败区分。

- 前置：`tcp://61.186.254.135:42213`；SDK 来源为 `CTP v6.7.13_20260225 14:16:30.12079`。
- 本次全量 run：`d4b7c331eb38381d26709239e253be6f`；登录成功、官方返回 `request_id=0` 的响应被正确接受。
- 实际每日库：`collector/data/20260907.sqlite`。间隔读取 snapshot 行数从 **13,297** 增至 **48,502**，库中有 **714** 个不同合约。`integrity_check=ok`，`foreign_key_check` 无结果。
- 三个原生服务处于 active/running，切换后观测重启次数均为 0。
- 手工再次刷新：`changed=false`、714 个合约；Collector PID 仍为 19872，没有因相同清单重启。

## Windows 与自动运行

Windows PowerShell 请求 `http://localhost:8101` 返回 HTTP 200，同端口 `/api/coverage` 返回 `complete=true` 和 46 个分组。

另通过 Windows Node 驱动真实 Windows Edge（无头）打开同一地址，等待覆盖成功提示，确认页面渲染了真实 snapshot 数量、同源 API 可访问，JavaScript 错误为 0。无需修改 Windows 防火墙、WSL 转发配置或重启 WSL。

用户级 systemd 已启用 Collector、FastAPI、Vite 看板和持久定时器。下一次更新为 2026-09-08 08:45 CST；失败重试时点为 09:00、09:15。每天定时器的未来触发仍需实际运行观察，本次验证了配置解析、启用状态和更新程序的跳过/重试逻辑。

Docker Compose 配置解析确认默认绑定 `127.0.0.1:8101 → dashboard:8080`；没有重新构建 Docker 镜像或宣称容器验收通过。

## 回归验证

- CTest 六项全部通过，新增清单文件优先级、缺失/空文件、超过 10000 上限、205 个合约分批订阅、单合约失败隔离、重连订阅及零编号登录响应用例。
- 清单更新程序六项测试通过：全品种多月份和 Call/Put 解析、去重、源日期不匹配、单边缺失、来源失败保留旧清单、未到期合约异常消失、原子发布、清单变化后的重启请求、失败后的重启补偿、启动跳过和每日重试逻辑。
- FastAPI 十一项测试通过，包含覆盖计数、订阅失败和暂无推送的区别、跨 run / 过期诊断清空实时计数、损坏文件和严格只读检查。
- React 五项组件测试及生产构建通过，覆盖统计请求失败后清除旧值。
- 原生进程闭环 smoke 通过：临时合成 SDK → SQLite → FastAPI，独立停启、持久行数及 SIGKILL 心跳过期。该测试数据与真实目录隔离。

## 本机证据与操作

以下原始证据位于被 Git 忽略的本机目录：

- `collector/data/universe/raw/20260907-131754-0cad5322/`：官方响应、请求 URL、抓取时间和 SHA-256。
- `collector/data/universe/current/manifest.json`：当前解析清单、来源和完整性状态。
- `collector/logs/cffex-coverage-20260907.json.log`：逐分组与逐合约覆盖证据。
- `collector/logs/cffex-summary-{first,second}.json.log`：两次数据库行数检查。
- `collector/logs/windows-browser-8101.log`、`collector/tmp/windows-8101.png`：Windows Edge 验收输出和完整页面截图。
- `collector/logs/{cffex-build,universe-tests,query-cffex-tests,dashboard-cffex-tests,native-read-smoke}.log`：回归结果。

```bash
./collector/scripts/native.sh status
./collector/scripts/native.sh logs
./collector/scripts/native.sh update
./collector/scripts/native.sh stop
# 恢复/更新已构建的部署
./collector/scripts/native.sh up
```

运行日志由 `journalctl --user -u derivatives-monitor-collector.service` 查看。配置与每日数据保留；WSL 关闭或 Windows 睡眠时无法继续采集。原始响应与不可变清单版本暂不自动清理，需要按磁盘容量保留或归档。
