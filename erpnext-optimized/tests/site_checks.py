"""空站点运行检查，不生成业务单据。"""
import os

import frappe

os.chdir("/home/frappe/frappe-bench/sites")
frappe.init(site=os.environ["SITE_NAME"], sites_path=os.getcwd())
frappe.connect()
try:
    # 优化镜像继承标准镜像的独立迁移兼容钩子，同样验证真实表及官方补丁。
    frappe.get_attr("china_sme_accounting.tests.migration.run")()
    from erpnext.stock.doctype.item.item_search import ItemSearch
    frappe.db.set_single_value("Global Defaults", "enable_item_search_index", 1)
    frappe.db.commit()
    search = ItemSearch()
    search.build_index()
    assert search.index_exists()
    assert set(["erpnext", "hrms", "crm", "china_sme_accounting"]).issubset(frappe.get_installed_apps())
    assert frappe.db.count("Company") == 0
    assert frappe.db.count("GL Entry") == 0
    assert frappe.db.count("Customer") == 0
    assert frappe.db.count("Supplier") == 0
    print("应用、空物料索引与无业务数据检查通过")
finally:
    frappe.destroy()
