# DerivativeMonitor CTP 行情 Demo

这是中信建投期货提供的 CTP C++ Demo 的可运行整理版。当前目标是让 Visual Studio 2022 能稳定构建和启动行情连接，用于验证 CTP 行情链路；暂不包含自动获取全部合约、行情落库、分钟线、基差或 IV 计算。

## 已确认的问题

- 项目只能使用 `x64`。随附的 CTP DLL 和 LIB 都是 64 位，选择 Win32 会导致架构不匹配。
- 原始 `config.ini` 的行情地址是 `127.0.0.1:41213`，它要求本机另有代理服务监听；没有代理时，程序会在 `Init()` 后无限等待，看起来像“没有反应”。
- 生成的 EXE 依赖 `thostmduserapi_se.dll`、`thosttraderapi_se.dll` 和 `WinDataCollect.dll`。直接从空的输出目录启动会以 `0xC0000135` 退出。
- CTP 要求 flow 目录在 API 初始化之前存在。

项目文件已经在构建后把上述 DLL 和本机配置复制到输出目录，并创建 `flow` 目录。Visual Studio 调试工作目录也固定为输出目录。

## 首次配置

1. 将 `demo/config.example.ini` 复制为 `demo/config.ini`。
2. 行情 MVP 可以保留模板中的 `BrokerID=9080` 和已验证可连接的行情前置地址。
3. 如期货公司给出了专属地址或凭据，以其最新通知为准。
4. `demo/config.ini` 包含 Password、AuthCode、AppID 等敏感项，已被 Git 忽略，不要提交。

## Visual Studio 启动

1. 用 Visual Studio 2022 打开 `demo_program.sln`。
2. 选择 `Debug | x64`，确认 `testProgram` 为启动项目。
3. 按 `F5` 启动，控制台出现菜单后输入 `2` 连接行情。
4. 看到 `OnFrontConnected` 和 `OnRspUserLogin` 后，输入当前有效的合约代码；多个合约使用英文冒号分隔，例如 `IF2609:IH2609`。合约月份会变化，示例仅用于说明格式。
5. 看到 `OnRspSubMarketData` 且 `ErrorID [0]` 表示订阅请求成功；交易时段内随后会收到 `OnRtnDepthMarketData`。

命令行构建也可使用：

```powershell
& 'C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe' demo_program.sln /m /t:Build /p:Configuration=Debug /p:Platform=x64
```

## 当前 Demo 的边界

- 行情前置只接受明确的合约代码；空数组不能表示订阅全市场。
- 当前代码由用户手工输入合约，不会自动发现 IF、IH、IC、IM、IO、HO、MO 的全部当月合约。
- 程序的连接等待没有超时。若停在行情地址输出后没有 `OnFrontConnected`，优先检查 `config.ini`、网络和期货公司前置状态。
- 交易入口仍使用原始本地占位地址，未提供真实交易前置前不要选择菜单 `1`。

后续行情 MVP 应新增合约发现、按产品过滤、分批订阅、断线重连、结构化落库以及分钟线/基差/IV 计算，而不是继续扩展这个交互式 Demo 的菜单。

