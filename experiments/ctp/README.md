# CTP Linux C++ 行情客户端

该目录使用官方 `v6.7.13_20260225` Linux x86-64 Market Data SDK，构建和运行原生 Linux C++ 行情客户端。构建所需的最小 SDK 已置于仓库中，不需要再解压完整官方包。

券商提供的前置地址、行情范围、频率和接入边界见 [中信建投期货 CTP 行情接入信息](docs/csc-futures-ctp-market-data-access.md)。

## 目录结构

```text
ctp/
├── cpp/                              # Linux C++ 工程
│   ├── CMakeLists.txt
│   ├── config.example.ini
│   ├── src/main.cpp
│   └── scripts/
│       ├── build.sh
│       └── run.sh
├── docs/                             # 券商接入信息和项目边界
└── sdk/v6.7.13_20260225/             # Linux 行情 SDK 最小构建集
```

保留的 SDK 文件为：

```text
sdk/v6.7.13_20260225/
├── MANIFEST.txt
└── linux64/mdapi/
    ├── ThostFtdcMdApi.h
    ├── ThostFtdcUserApiDataType.h
    ├── ThostFtdcUserApiStruct.h
    └── thostmduserapi_se.so
```

`MANIFEST.txt` 保留官方原包文件名、SHA-256、SDK 版本和平台信息。三份厂商头文件的中文原为 GB18030 编码，且仅出现在注释中；仓库版已转为 UTF-8，转码前后的哈希均记录在清单中。未保留 Windows DLL/LIB、Trader API、中间压缩包和不参与当前客户端构建或运行的错误码 XML。

## 环境要求

- Linux x86-64；
- GCC/G++ 支持 C++17；
- CMake 3.16 或更高版本。

当前环境已用 Ubuntu 22.04、G++ 11.4、CMake 3.22 验证。官方 `.so` 是 ELF x86-64，所需 GLIBC/GLIBCXX 符号不高于当前系统提供的版本。

## 快速开始

在 `experiments/ctp` 下运行：

```bash
./cpp/scripts/build.sh Release
./cpp/scripts/run.sh --run-seconds 5
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
cpp/build/Release/bin/ctp_md
cpp/build/Release/bin/thostmduserapi_se.so
```

ELF 的 `RUNPATH` 是 `$ORIGIN`，因此运行时从可执行文件所在目录加载官方 `.so`，不依赖绝对 SDK 路径或手工设置 `LD_LIBRARY_PATH`。

## 配置

本机需要修改配置时：

```bash
cp cpp/config.example.ini cpp/config.ini
```

`cpp/config.ini` 已被 Git 忽略。配置项：

| 字段 | 说明 |
|---|---|
| `FrontMdAddr` | CTP 行情前置，必填。 |
| `BrokerID` | 经纪公司代码。 |
| `UserID` / `Password` | 行情前置需要账号时填写；不要提交真实凭据。 |
| `UserProductInfo` | CTP 用户端产品标识，必须适配 CTP 固定字段长度。 |
| `Instruments` | 手工订阅的精确合约代码，使用冒号或逗号分隔；留空只验证登录。 |
| `FlowPath` | CTP flow 目录，相对路径以配置文件所在目录为基准。 |
| `ConnectTimeoutSeconds` | 等待连接和登录的超时时间。 |
| `RunSeconds` | 登录后运行时间；`0` 表示持续运行到 `SIGINT`/`SIGTERM`。 |

`run.sh` 优先读取 `cpp/config.ini`，不存在时使用示例配置。

## 运行选项

```text
--config PATH
--instrument CODE      # 可重复传入，并覆盖配置中的 Instruments
--run-seconds N        # 覆盖 RunSeconds；0 表示持续运行
--help
```

例如，使用你已确认的合约运行到按下 `Ctrl+C`：

```bash
./cpp/scripts/run.sh \
  --instrument FUTURES_CONTRACT_CODE \
  --instrument OPTION_CONTRACT_CODE \
  --run-seconds 0
```

程序不自动发现或猜测合约。订阅成功后，每个 `event=tick` 行包含合约、交易所、更新时间、最新价、买一/卖一、成交量和持仓量。

## 已验证与已知现象

- Debug 和 Release 都可通过 CMake 构建。
- `ctp_md` 为 Linux ELF 64-bit x86-64 可执行文件。
- API 报告版本 `v6.7.13_20260225 14:16:30.12079`。
- 示例行情前置已验证 `front_connected` 及 `login_response error_id=0`。
- SDK 初始化可能在某些容器/WSL 网卡上输出类似 `docker0: Resource temporarily unavailable` 的诊断；若之后仍出现 `front_connected` 和成功登录，该行不影响行情连接。
- 当前工程仅包含行情 API，不会登录交易前置或发送交易请求。
