app_name = "china_sme_accounting"
app_title = "中国小企业会计准则"
app_publisher = "myerp maintainers"
app_description = "ERPNext V16 中国小企业会计准则公共元数据扩展"
app_email = ""
app_license = "MIT"

required_apps = ["erpnext"]

# 升级复用 Redis 卷时，必须先刷新模块清单，再同步新增模块的表结构。
before_migrate = "china_sme_accounting.migration.refresh_module_registry"
