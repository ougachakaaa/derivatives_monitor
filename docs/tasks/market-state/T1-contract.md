# T1 契约与 scope

Spec：新增纯 Python 模块，验证带时区时间、instrument 标识、明确 Universe（day/version/complete）及 instrument/product/month/option_chain scope。固定成员顺序，不读取当前清单或从行情推断完整链。支持显式 manifest 解析，拒绝日期/来源验证不匹配却声称完整的输入。

验证：代码归属、月份、去重排序、缺失日期/版本、错误 scope、清单不完整、历史清单显式选择。提交不得修改 Raw/Collector。
