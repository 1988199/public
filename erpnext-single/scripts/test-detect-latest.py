#!/usr/bin/env python3
"""离线验证发布门禁；不访问 GitHub，不构建镜像。"""
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("detect_latest", Path(__file__).with_name("detect-latest.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class GateTests(unittest.TestCase):
    def run_case(self, updates):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docker").mkdir()
            (root / "docs").mkdir()
            refs = {"frappe": "v16.51.0", "erpnext": "v16.50.0", "hrms": "v16.50.0", "crm": "v1.86.0"}
            current = {name: {"repository": repo, "ref": refs[name], "sha": "1" * 40}
                       for name, (repo, _) in module.SOURCES.items()}
            candidates = {name: dict(value) for name, value in current.items()}
            for name, ref in updates.items():
                candidates[name] = {**candidates[name], "ref": ref, "sha": "2" * 40}
            files = {
                "docker/upstream.lock.json": json.dumps(current),
                "docker/apps.json": json.dumps([{"name": name, "ref": refs[name]} for name in ("erpnext", "hrms", "crm")]),
                "Dockerfile": "ARG FRAPPE_REF=v16.51.0\n",
                "compose.yaml": "        FRAPPE_REF: v16.51.0\n",
                "docs/版本清单.md": "当前 ERPNext 稳定版本：`v16.50.0`\n",
            }
            for name, content in files.items():
                (root / name).write_text(content, encoding="utf-8")
            output = root / "output.txt"
            by_repo = {value["repository"]: value for value in candidates.values()}
            with patch.object(module, "ROOT", root), patch.object(module, "LOCK", root / "docker/upstream.lock.json"), \
                 patch.object(module, "latest", side_effect=lambda repo, major: by_repo[repo]), \
                 patch.dict(os.environ, {"GITHUB_OUTPUT": str(output), "GITHUB_STEP_SUMMARY": str(root / "summary.md")}):
                module.main()
            actual = {name: (root / name).read_text(encoding="utf-8") for name in files}
            return files, actual, output.read_text(), candidates

    def assert_waits(self, updates):
        before, after, output, _ = self.run_case(updates)
        self.assertEqual(before, after)
        self.assertIn("erpnext_changed=false", output)
        self.assertIn("changed=false", output)

    def test_no_updates(self):
        self.assert_waits({})

    def test_crm_only_waits(self):
        self.assert_waits({"crm": "v1.87.0"})

    def test_frappe_only_waits(self):
        self.assert_waits({"frappe": "v16.52.0"})

    def test_hrms_only_waits(self):
        self.assert_waits({"hrms": "v16.51.0"})

    def test_erpnext_unlocks_bundle(self):
        _, after, output, candidates = self.run_case({"erpnext": "v16.50.1", "crm": "v1.87.0"})
        self.assertIn("erpnext_changed=true", output)
        self.assertEqual(json.loads(after["docker/upstream.lock.json"]), candidates)
        apps = {app["name"]: app["ref"] for app in json.loads(after["docker/apps.json"])}
        self.assertEqual(apps["crm"], "v1.87.0")

    def test_changed_tag_rejected(self):
        with self.assertRaisesRegex(ValueError, "标签提交发生变化"):
            self.run_case({"crm": "v1.86.0"})

if __name__ == "__main__":
    unittest.main()
