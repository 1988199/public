from __future__ import annotations

from frappe.translate import get_all_translations


REQUIRED_TRANSLATIONS = {
	"Access Denied": "拒绝访问",
	"Cancel": "取消",
	"Continue": "继续",
	"Forgot password?": "忘记密码？",
	"Login with Email Link": "通过邮箱链接登录",
	"Save": "保存",
	"Search": "搜索",
	"Sign In": "登录",
	"Submit": "提交",
	"Welcome! Please sign in to continue.": "欢迎！请登录后继续。",
}


def run():
	"""验证简体中文基础包和发行版补充译文已合并到站点。"""
	translations = get_all_translations("zh")
	for source, expected in REQUIRED_TRANSLATIONS.items():
		actual = translations.get(source)
		assert actual == expected, f"关键译文不正确: {source} -> {actual!r}"

	assert len(translations) >= 14000, f"简体中文词典条目异常偏少: {len(translations)}"
	return {
		"language": "zh",
		"translation_count": len(translations),
		"required_translation_count": len(REQUIRED_TRANSLATIONS),
		"key_translations_verified": True,
		"login_translation": translations["Sign In"],
		"save_translation": translations["Save"],
		"crm_translation": translations["Access Denied"],
	}
