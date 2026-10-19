"""升级兼容：通过标准扩展点刷新旧 Redis 中的应用模块映射。"""

import frappe


def refresh_module_registry():
    """幂等刷新模块元数据；不修改业务记录，不跳过任何上游补丁。

    Frappe 的模块映射会跨镜像保存在 Redis。CRM 1.88 新增 Domain
    Enrichment 模块时，旧映射可能令模型同步漏表，随后补丁报缺表。
    清理限定的两个映射键，从当前镜像 modules.txt 重建；再次执行官方
    模块注册，补齐在 before_migrate 钩子之前被旧映射漏掉的模块。
    异常直接向上传播，阻止未完整迁移的站点继续启动。
    """
    from frappe.installer import sync_module_defs

    frappe.only_for("System Manager")
    frappe.cache.delete_value("app_modules")
    frappe.client_cache.delete_value("installed_app_modules")
    frappe.setup_module_map()
    sync_module_defs()
