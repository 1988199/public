import frappe
from erpnext.accounts.doctype.account.chart_of_accounts.chart_of_accounts import (
	get_charts_for_country,
)


TEMPLATE_NAME = "中国小企业会计准则"


def run():
	"""在 CI 的临时站点创建虚构公司，并验证 66 个标准编号。"""
	assert frappe.db.count("Company") == 0, "空站点安装后不应自动创建公司"
	assert frappe.db.count("GL Entry") == 0, "空站点安装后不应存在总账分录"
	chart_options = get_charts_for_country("China", with_standard=True)
	assert TEMPLATE_NAME in chart_options, f"模板未出现在中国科目表选项中: {chart_options}"
	if not frappe.db.exists("Warehouse Type", "Transit"):
		frappe.get_doc({"doctype": "Warehouse Type", "name": "Transit"}).insert(
			ignore_permissions=True
		)

	company_name = "会计准则测试示例企业"
	company = frappe.get_doc(
		{
			"doctype": "Company",
			"company_name": company_name,
			"abbr": "CSAT",
			"default_currency": "CNY",
			"country": "China",
			"chart_of_accounts": TEMPLATE_NAME,
		}
	)
	company.flags.ignore_permissions = True
	company.insert()

	accounts = frappe.get_all(
		"Account",
		filters={"company": company_name, "account_number": ["is", "set"]},
		fields=["account_number", "account_name", "root_type"],
	)
	by_number = {account.account_number: account for account in accounts}
	assert len(by_number) == 66, f"预期 66 个编号科目，实际 {len(by_number)}"
	assert by_number["5001"].root_type == "Income"
	assert by_number["5403"].root_type == "Expense"
	assert by_number["5403"].account_name == "税金及附加"
	assert company.default_receivable_account
	assert company.default_payable_account

	return {
		"template": TEMPLATE_NAME,
		"template_visible": True,
		"empty_site_verified": True,
		"numbered_accounts": len(by_number),
	}
