#!/usr/bin/env python3
"""从官方发布中选择稳定版本；仅在版本前进时更新候选构建清单。"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "docker/upstream.lock.json"
SOURCES = {
    "frappe": ("frappe/frappe", 16),
    "erpnext": ("frappe/erpnext", 16),
    "hrms": ("frappe/hrms", 16),
    "crm": ("frappe/crm", 1),
}


def api(path: str) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "erpnext-v16-release-builder",
    }
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(f"https://api.github.com/{path}", headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def version(ref: str, major: int) -> tuple[int, int, int]:
    match = re.fullmatch(rf"v({major})\.(\d+)\.(\d+)", ref)
    if not match:
        raise ValueError(f"非法 V{major} 稳定标签：{ref}")
    return tuple(map(int, match.groups()))


def tag_commit(repo: str, ref: str) -> str:
    obj = api(f"repos/{repo}/git/ref/tags/{ref}")["object"]
    for _ in range(3):
        if obj["type"] == "commit":
            return obj["sha"]
        if obj["type"] != "tag":
            break
        obj = api(f"repos/{repo}/git/tags/{obj['sha']}")["object"]
    raise ValueError(f"无法解析官方标签：{repo} {ref}")


def latest(repo: str, major: int) -> dict[str, str]:
    releases = api(f"repos/{repo}/releases?per_page=100")
    refs = [
        item["tag_name"]
        for item in releases
        if not item["draft"]
        and not item["prerelease"]
        and re.fullmatch(rf"v{major}\.\d+\.\d+", item["tag_name"])
    ]
    if not refs:
        raise ValueError(f"未找到 {repo} 的 V{major} 正式发布")
    ref = max(refs, key=lambda item: version(item, major))
    return {"repository": repo, "ref": ref, "sha": tag_commit(repo, ref)}


def replace_once(path: Path, pattern: str, replacement: str) -> None:
    original = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, original, count=1, flags=re.M)
    if count != 1:
        raise ValueError(f"无法更新版本字段：{path}，匹配数 {count}")
    path.write_text(updated, encoding="utf-8", newline="\n")


def main() -> None:
    current = json.loads(LOCK.read_text(encoding="utf-8"))
    candidate = {}
    changed = False
    for app, (repo, major) in SOURCES.items():
        selected = latest(repo, major)
        old = current[app]
        if old["repository"] != repo:
            raise ValueError(f"{app} 官方来源变更，需人工核对")
        if version(selected["ref"], major) < version(old["ref"], major):
            raise ValueError(f"{app} 官方版本意外回退，拒绝自动降级")
        if selected["ref"] == old["ref"] and selected["sha"] != old["sha"]:
            raise ValueError(f"{app} 的已用标签提交发生变化，拒绝自动覆盖")
        candidate[app] = selected
        changed |= selected["ref"] != old["ref"]
        print(f"{app}: {old['ref']} -> {selected['ref']} ({selected['sha']})")

    if changed:
        replace_once(ROOT / "Dockerfile", r"^ARG FRAPPE_REF=v16\.\d+\.\d+$", f"ARG FRAPPE_REF={candidate['frappe']['ref']}")
        replace_once(ROOT / "compose.yaml", r"^        FRAPPE_REF: v16\.\d+\.\d+$", f"        FRAPPE_REF: {candidate['frappe']['ref']}")
        apps_path = ROOT / "docker/apps.json"
        apps = json.loads(apps_path.read_text(encoding="utf-8"))
        for item in apps:
            if item["name"] in candidate:
                item["ref"] = candidate[item["name"]]["ref"]
        apps_path.write_text(json.dumps(apps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        LOCK.write_text(json.dumps(candidate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        version_path = ROOT / "docs/版本清单.md"
        for app, label in (("frappe", "Frappe"), ("erpnext", "ERPNext"), ("hrms", "HRMS"), ("crm", "CRM")):
            item = candidate[app]
            replace_once(version_path, rf"^\| {label} \| v\d+\.\d+\.\d+ \| [0-9a-f]{{40}} \|$", f"| {label} | {item['ref']} | {item['sha']} |")

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"changed={str(changed).lower()}\n")
            stream.write(f"version={candidate['erpnext']['ref'].removeprefix('v')}\n")


if __name__ == "__main__":
    main()
