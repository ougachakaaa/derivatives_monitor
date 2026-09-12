# Collector tools

本目录包含 Universe 清单工具、原生三服务管理入口及 Collector 镜像的健康/只读验收辅助脚本。精确 Universe 行为见本级 [Contract](CONTRACT.md)；共享日期、版本与消费者交接见 [Market Session Contract](../../docs/contracts/market-session.md)。系统 lifecycle 与操作步骤仍由根 [Deployment Contract](../../docs/contracts/deployment.md)和 [Operations](../../docs/operations.md)负责。

## Universe discovery

从仓库根手工刷新公开合约清单：

```bash
python3 collector/scripts/universe.py --data-dir collector/data
python3 collector/scripts/universe.py --data-dir collector/data --date YYYYMMDD
```

输出位于 `collector/data/universe/`，原生管理器使用 `current/instruments.txt`。查看全部参数用 `--help`；运行专用测试：

```bash
python3 -m unittest discover -s collector/tests -p 'test_universe.py' -v
```

## Native systemd manager

完成 [Collector 构建与配置](../README.md#构建与测试)、Query 环境和 Dashboard 依赖准备后，从仓库根执行：

```bash
./collector/scripts/native.sh up
./collector/scripts/native.sh status
./collector/scripts/native.sh logs
./collector/scripts/native.sh update
./collector/scripts/native.sh stop
```

`up` / `update` 会改变服务状态；配置准备、三服务与 Universe timer 的 enable/restart、停止、更新与长期禁用步骤见 [Operations](../../docs/operations.md#native-systemd-部署)。

## Container helpers

`healthcheck.sh` 和 `verify.sh` 是 Collector 镜像的明确 build inputs，由仓库级 `scripts/deploy.sh` 调用链使用，不是另一套部署入口。宿主侧状态、日志与指定交易日验证命令见 [Operations](../../docs/operations.md#docker-compose-部署)。
