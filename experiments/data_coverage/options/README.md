# Options Coverage

本目录验证 CFFEX 股指期权的完整链获取能力。开始 Sina Probe 时依次读取：

1. 本目录的 [SPEC.md](SPEC.md)；
2. [sina/README.md](sina/README.md)；
3. [sina/REFERENCE.md](sina/REFERENCE.md)。

重点不是查询少量已知合约，而是从 Product 发现 Expiry，再从每个被测 Expiry 获取 Strike × Call/Put 的完整返回组织。

