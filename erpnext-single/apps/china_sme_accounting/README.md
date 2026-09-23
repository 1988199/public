# China SME Accounting

本 App 为 ERPNext V16 提供经过来源核对的中国《小企业会计准则》公共元数据，以及不修改上游源码的简体中文补充翻译承载点。

当前版本只包含可在创建中国公司时选择的标准科目基线，不包含公司、期初余额、凭证、客户、供应商、税号或其他企业数据。详细来源、差异和使用限制见 `china_sme_accounting/standards/cn_sme_2011_v1/README.md`。

镜像构建时会从 Frappe 官方 GitHub 获取经过哈希固定的有效简体中文基线，并在本 App 的 `translations/zh.csv` 中加载；仓库自身仅维护当前 V16 新界面所需的公共补充译文。
