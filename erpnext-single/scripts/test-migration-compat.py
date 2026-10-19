"""离线验证迁移钩子的顺序、幂等性及失败传播，不连接数据库。"""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

MODULE = Path(__file__).resolve().parents[1] / "apps/china_sme_accounting/china_sme_accounting/migration.py"


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.order = Mock()
        self.frappe = types.ModuleType("frappe")
        self.frappe.only_for = self.order.permission
        self.frappe.cache = types.SimpleNamespace(delete_value=self.order.shared_cache)
        self.frappe.client_cache = types.SimpleNamespace(delete_value=self.order.site_cache)
        self.frappe.setup_module_map = self.order.rebuild
        self.installer = types.ModuleType("frappe.installer")
        self.installer.sync_module_defs = self.order.register
        self.context = patch.dict(sys.modules, {"frappe": self.frappe, "frappe.installer": self.installer})
        self.context.start()
        spec = importlib.util.spec_from_file_location("migration_compat", MODULE)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def tearDown(self):
        self.context.stop()

    def test_refresh_before_register(self):
        self.module.refresh_module_registry()
        self.assertEqual(self.order.mock_calls, [call.permission("System Manager"),
            call.shared_cache("app_modules"), call.site_cache("installed_app_modules"),
            call.rebuild(), call.register()])

    def test_repeated_execution(self):
        self.module.refresh_module_registry()
        first = list(self.order.mock_calls)
        self.module.refresh_module_registry()
        self.assertEqual(self.order.mock_calls, first + first)

    def test_no_permission_does_not_mutate_cache(self):
        self.order.permission.side_effect = PermissionError("denied")
        with self.assertRaises(PermissionError):
            self.module.refresh_module_registry()
        self.order.shared_cache.assert_not_called()

    def test_failure_stops_registration(self):
        self.order.rebuild.side_effect = RuntimeError("broken module")
        with self.assertRaises(RuntimeError):
            self.module.refresh_module_registry()
        self.order.register.assert_not_called()


if __name__ == "__main__":
    unittest.main()
