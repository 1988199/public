"""在合成测试站点核对 CRM 新模块及迁移结果。"""
import frappe


def run():
    """只读验证新模块真实表存在，避免只验证网页健康而漏检迁移。"""
    frappe.only_for("System Manager")
    if "crm" not in frappe.get_installed_apps():
        raise RuntimeError("CRM 未安装")
    from crm import __version__
    version = tuple(map(int, __version__.split(".")[:3]))
    if version < (1, 88, 0):
        return {"crm_version": __version__, "new_module_required": False}
    if not frappe.db.exists("Module Def", "Domain Enrichment"):
        raise RuntimeError("CRM 新模块未注册")
    for name in ("CRM Enrichment Rule Pattern", "CRM Enrichment Rule"):
        if not frappe.db.exists("DocType", name) or not frappe.db.table_exists(name):
            raise RuntimeError("CRM 新模块缺少实际表：" + name)
    for name in ("set_enrichment_rule_names", "drop_enrichment_headers_scope"):
        if not frappe.db.exists("Patch Log", "crm.patches.v1_0." + name):
            raise RuntimeError("CRM 官方补丁未执行：" + name)
    return {"crm_version": __version__, "enrichment_schema_verified": True,
            "official_patches_verified": True}
