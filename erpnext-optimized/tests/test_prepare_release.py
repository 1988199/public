"""离线验证优化发布衔接；只操作临时文件，不连接站点或镜像仓库。"""
import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("prepare_release", Path(__file__).resolve().parents[1] / "scripts/prepare-release.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"runtime_revision": "20261012.1", "base_digest": "sha256:" + "a" * 64,
                         "sqlite": "3.54.0", "apps": {"frappe": "16.51.0", "erpnext": "16.50.0",
                         "hrms": "16.50.0", "crm": "1.87.0", "china_sme_accounting": "0.2.0"}}
        self.lock = {name: {"repository": "frappe/" + name, "ref": "v" + self.manifest["apps"][name],
                           "sha": "b" * 40} for name in ("frappe", "erpnext", "hrms", "crm")}

    def test_same_version_skips(self):
        changed, target = module.plan(self.manifest, self.lock)
        self.assertFalse(changed)
        self.assertEqual(target, self.manifest)

    def test_component_updates_wait(self):
        self.lock["frappe"]["ref"] = "v16.51.1"
        self.assertFalse(module.plan(self.manifest, self.lock)[0])

    def test_historical_standard_crm_does_not_downgrade(self):
        self.lock["crm"]["ref"] = "v1.86.0"
        changed, target = module.plan(self.manifest, self.lock)
        self.assertFalse(changed)
        self.assertEqual(target["apps"]["crm"], "1.87.0")

    def test_next_erp_unlocks_bundle(self):
        self.lock["erpnext"]["ref"] = "v16.50.1"
        self.lock["crm"]["ref"] = "v1.88.0"
        changed, target = module.plan(self.manifest, self.lock)
        self.assertTrue(changed)
        self.assertEqual(target["apps"]["crm"], "1.88.0")
        self.assertEqual(target["sqlite"], self.manifest["sqlite"])

    def test_erp_downgrade_rejected(self):
        self.lock["erpnext"]["ref"] = "v16.49.0"
        with self.assertRaises(ValueError):
            module.plan(self.manifest, self.lock)

    def test_component_downgrade_rejected_on_release(self):
        self.lock["erpnext"]["ref"] = "v16.50.1"
        self.lock["crm"]["ref"] = "v1.86.0"
        with self.assertRaises(ValueError):
            module.plan(self.manifest, self.lock)

    def test_nonofficial_source_rejected(self):
        self.lock["crm"]["repository"] = "someone/crm"
        with self.assertRaises(ValueError):
            module.plan(self.manifest, self.lock)

    def test_preparation_pins_digest_and_commit(self):
        self.lock["erpnext"]["ref"] = "v16.50.1"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "optimized"
            standard = Path(directory) / "standard"
            (root / "docker").mkdir(parents=True)
            (standard / "docker").mkdir(parents=True)
            (root / "docker/manifest.json").write_text(json.dumps(self.manifest))
            (standard / "docker/upstream.lock.json").write_text(json.dumps(self.lock))
            (root / "Dockerfile").write_text("ARG BASE_IMAGE=old\nARG CRM_SHA=old\n")
            image = "ghcr.io/1988199/erpnext-single@sha256:" + "c" * 64
            module.prepare(root, standard, image)
            result = json.loads((root / "docker/manifest.json").read_text())
            self.assertEqual(result["base_digest"], "sha256:" + "c" * 64)
            self.assertEqual(result["source_lock"], self.lock)
            self.assertIn("ARG BASE_IMAGE=" + image, (root / "Dockerfile").read_text())


if __name__ == "__main__":
    unittest.main()
