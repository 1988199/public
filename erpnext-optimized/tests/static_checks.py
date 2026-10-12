"""发布前静态门禁，不允许企业配置或备份进入构建上下文。"""
import ast
import json
from pathlib import Path

root = Path.cwd()
for file in root.rglob("*.py"):
    ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
for file in root.rglob("*"):
    if not file.is_file():
        continue
    assert file.suffix not in {".sql", ".gz", ".tgz", ".xlsx", ".zip"}, file
    assert file.name not in {".env", "site_config.json", "configuration.json"}, file
    text = file.read_text(encoding="utf-8")
    assert "广州" + "嵘创" + "技术有限公司" not in text, file
manifest = json.loads((root / "docker/manifest.json").read_text())
assert manifest["apps"]["erpnext"].startswith("16.")
assert "@sha256:" in (root / "Dockerfile").read_text()
assert 'DB_ROOT_PASSWORD="" ADMIN_PASSWORD=""' in (root / "Dockerfile").read_text()
print("静态检查通过")
