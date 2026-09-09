# CTP Linux C++ 行情客户端

该目录保留原生 Linux C++ 行情客户端、接入验证记录和技术探索文档。实验客户端使用 Collector 正式拥有的 `v6.7.13_20260225` Linux x86-64 Market Data SDK 与 CMake 适配，不需要再解压完整官方包；正式模块不反向依赖本目录。

券商提供的前置地址、行情范围、频率和接入边界见 [中信建投期货 CTP 行情接入信息](docs/csc-futures-ctp-market-data-access.md)。

## 目录结构

```text
ctp/
├── market-data-client/               # Linux CTP 行情客户端
│   ├── CMakeLists.txt
│   ├── config.example.ini
│   ├── src/main.cpp
│   └── scripts/
│       ├── build.sh
│       └── run.sh
└── docs/                             # 券商接入信息和项目边界
```

Collector 保留的 SDK 文件为：

```text
../../collector/third_party/ctp/v6.7.13_20260225/
├── MANIFEST.txt
└── linux64/mdapi/
    ├── ThostFtdcMdApi.h
    ├── ThostFtdcUserApiDataType.h
    ├── ThostFtdcUserApiStruct.h
    └── thostmduserapi_se.so
```

[`MANIFEST.txt`](../../collector/third_party/ctp/v6.7.13_20260225/MANIFEST.txt) 保留官方原包文件名、SHA-256、SDK 版本和平台信息。三份厂商头文件的中文原为 GB18030 编码，且仅出现在注释中；仓库版已转为 UTF-8，转码前后的哈希均记录在清单中。未保留 Windows DLL/LIB、Trader API、中间压缩包和不参与当前客户端构建或运行的错误码 XML。

## 环境要求

- Linux x86-64；
- GCC/G++ 支持 C++17；
- CMake 3.16 或更高版本。

当前环境已用 Ubuntu 22.04、G++ 11.4、CMake 3.22 验证。官方 `.so` 是 ELF x86-64，所需 GLIBC/GLIBCXX 符号不高于当前系统提供的版本。

## 快速开始

在 `experiments/ctp` 下运行：

```bash
./market-data-client/scripts/build.sh Release
./market-data-client/scripts/run.sh --run-seconds 5
```

成功时会看到类似输出：

```text
event=start api_version="v6.7.13_20260225 ..."
event=front_connected ...
event=login_request result=0
event=login_response ... error_id=0 ...
event=ready instruments=0 message="login verified; no instruments configured"
event=stop reason=run_window_complete
```

Release 产物位于：

```text
market-data-client/build/Release/bin/ctp_md
market-data-client/build/Release/bin/thostmduserapi_se.so
```

ELF 的 `RUNPATH` 是 `$ORIGIN`，因此运行时从可执行文件所在目录加载官方 `.so`，不依赖绝对 SDK 路径或手工设置 `LD_LIBRARY_PATH`。

## 配置

本机需要修改配置时：

```bash
cp market-data-client/config.example.ini market-data-client/config.ini
```

`market-data-client/config.ini` 已被 Git 忽略。配置项：

| 字段 | 说明 |
|---|---|
| `FrontMdAddr` | CTP 行情前置，必填。 |
| `BrokerID` | 经纪公司代码。 |
| `UserID` / `Password` | 行情前置需要账号时填写；不要提交真实凭据。 |
| `UserProductInfo` | CTP 用户端产品标识，必须适配 CTP 固定字段长度。 |
| `Instruments` | 手工订阅的精确合约代码，使用冒号或逗号分隔；留空只验证登录。 |
| `FlowPath` | CTP flow 目录，相对路径以配置文件所在目录为基准。 |
| `CsvOutputPath` | 原始深度行情 CSV 输出路径；留空不写 CSV，启动时会覆盖同名文件。 |
| `ConnectTimeoutSeconds` | 等待连接和登录的超时时间。 |
| `RunSeconds` | 登录后运行时间；`0` 表示持续运行到 `SIGINT`/`SIGTERM`。 |

`run.sh` 优先读取 `market-data-client/config.ini`，不存在时使用示例配置。

## 运行选项

```text
--config PATH
--instrument CODE      # 可重复传入，并覆盖配置中的 Instruments
--csv PATH             # 将 CTP 原始深度行情写入 CSV
--run-seconds N        # 覆盖 RunSeconds；0 表示持续运行
--help
```

例如，使用你已确认的合约运行到按下 `Ctrl+C`：

```bash
./market-data-client/scripts/run.sh \
  --instrument FUTURES_CONTRACT_CODE \
  --instrument OPTION_CONTRACT_CODE \
  --csv ../tmp/market-data.csv \
  --run-seconds 0
```

程序不自动发现或猜测合约。订阅成功后，每个 `event=tick` 行包含合约、交易所、更新时间、最新价、买一/卖一、成交量和持仓量。

### CSV 行情输出

CSV 表头和列顺序与 SDK 的 `CThostFtdcDepthMarketDataField` 保持一致，共48 列，包含交易日、合约、交易所、价格、成交量、成交额、持仓量、五档买卖盘、结算价、涨跌停价和上下带价等字段。
完整字段名、CTP 类型和中文语义见 [`docs/ctp-depth-market-data-fields.csv`](docs/ctp-depth-market-data-fields.csv)。

- 列名保留 SDK 原始字段名，包括 `reserve1` 和 `reserve2`。
- 浮点数使用 C++17 最短往返表示，兼顾可读性与精确读回；不把 CTP 的无效极大值擅自转换为空值。
- 文本列按 CSV 规则转义逗号、引号和换行。
- CSV 仅包含 CTP 回调提供的原始字段；接收时间、行号等派生信息不混入原始表。

## SDK 链接模式

构建脚本支持 `AUTO`、`STATIC` 和 `SHARED` 三种模式：

```bash
./market-data-client/scripts/build.sh Release AUTO
./market-data-client/scripts/build.sh Release STATIC
./market-data-client/scripts/build.sh Release SHARED
```

- `AUTO` 是默认值：如果 SDK 目录中有 `thostmduserapi_se.a` 或 `libthostmduserapi_se.a`，优先静态链接；否则回退到 `.so`。
- `STATIC` 强制使用厂商静态库，缺失时构建立即失败，不会悄然改用动态库。
- `SHARED` 强制使用 `.so`，并将它复制到可执行文件目录，通过 `$ORIGIN` RUNPATH 加载，便于整目录发布。

当前官方 SDK 只提供 `thostmduserapi_se.so`，因此 `AUTO` 实际使用 `SHARED`。只有未来取得匹配版本的官方 `.a` 后，才能静态链接 CTP SDK；不应将现有 `.so` 转换或重打包成伪静态库。

## 已验证与已知现象

- Debug 和 Release 都可通过 CMake 构建。
- `ctp_md` 为 Linux ELF 64-bit x86-64 可执行文件。
- API 报告版本 `v6.7.13_20260225 14:16:30.12079`。
- 示例行情前置已验证 `front_connected` 及 `login_response error_id=0`。
- SDK 初始化可能在某些容器/WSL 网卡上输出类似 `docker0: Resource temporarily unavailable` 的诊断；若之后仍出现 `front_connected` 和成功登录，该行不影响行情连接。
- 当前工程仅包含行情 API，不会登录交易前置或发送交易请求。
