#!/usr/bin/env python3
"""把已验证的标准发行版本衔接到优化版，禁止同版本重发及组件降级。"""
import argparse
import copy
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STANDARD = ROOT.parent / "erpnext-single"


def version(value):
    if not re.fullmatch(r"\d+\.\d+\.\d+", value):
        raise ValueError("非法稳定版本号")
    return tuple(map(int, value.split(".")))


def plan(manifest, lock):
    expected = {"frappe": "frappe/frappe", "erpnext": "frappe/erpnext",
                "hrms": "frappe/hrms", "crm": "frappe/crm"}
    target = copy.deepcopy(manifest)
    for app, repository in expected.items():
        entry = lock[app]
        if entry["repository"] != repository or not re.fullmatch(r"[0-9a-f]{40}", entry["sha"]):
            raise ValueError("应用来源或固定提交不合法")
        if not entry["ref"].startswith("v"):
            raise ValueError("必须使用稳定标签")
        selected = entry["ref"][1:]
        if version(selected)[0] != (1 if app == "crm" else 16):
            raise ValueError("应用主系列不兼容")
        target["apps"][app] = selected
    old_erp = version(manifest["apps"]["erpnext"])
    new_erp = version(target["apps"]["erpnext"])
    if new_erp < old_erp:
        raise ValueError("拒绝 ERPNext 降级")
    if new_erp == old_erp:
        return False, copy.deepcopy(manifest)
    for app in expected:
        if version(target["apps"][app]) < version(manifest["apps"][app]):
            raise ValueError(f"拒绝 {app} 降级")
    target["source_lock"] = copy.deepcopy(lock)
    return True, target


def prepare(root, standard, base_image=None):
    path = root / "docker/manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    lock = json.loads((standard / "docker/upstream.lock.json").read_text(encoding="utf-8"))
    changed, target = plan(manifest, lock)
    if base_image:
        if not changed:
            raise ValueError("ERPNext 未前进，不允许准备同版本重发")
        match = re.fullmatch(r"ghcr\.io/[a-z0-9._-]+/erpnext-single@(sha256:[0-9a-f]{64})", base_image)
        if not match:
            raise ValueError("必须提供标准镜像的固定分发摘要")
        dockerfile = root / "Dockerfile"
        content = dockerfile.read_text(encoding="utf-8")
        for key, value in [("BASE_IMAGE", base_image), ("CRM_SHA", lock["crm"]["sha"])]:
            content, count = re.subn(rf"^ARG {key}=.+$", f"ARG {key}={value}", content, count=1, flags=re.M)
            if count != 1:
                raise ValueError(f"Dockerfile 中缺少 {key}")
        target["base_digest"] = match[1]
        revision = root / 'docker/RUNTIME_REVISION'
        if revision.exists():
            value = revision.read_text().strip()
            if not re.fullmatch(r'\d{8}\.\d+', value):
                raise ValueError('运行修订号非法')
            target['runtime_revision'] = value
        compose = root / "compose.yaml"
        if compose.exists():
            image_name = base_image.split("/erpnext-single@")[0] + "/erpnext-optimized:V" + target["apps"]["erpnext"] + "-opt-" + target["runtime_revision"]
            template, count = re.subn(r"^    image: .+$", "    image: ${IMAGE_NAME:-" + image_name + "}", compose.read_text(encoding="utf-8"), count=1, flags=re.M)
            if count != 1:
                raise ValueError("Compose 中缺少镜像参数")
            compose.write_text(template, encoding="utf-8", newline="\n")
        dockerfile.write_text(content, encoding="utf-8", newline="\n")
        path.write_text(json.dumps(target, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return changed, manifest, target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-image")
    args = parser.parse_args()
    changed, current, target = prepare(ROOT, STANDARD, args.base_image)
    status = "允许准备优化版" if changed else "ERPNext 版本未变化，跳过优化镜像构建发布"
    print(status)
    if output := os.environ.get("GITHUB_OUTPUT"):
        with open(output, "a", encoding="utf-8") as file:
            file.write(f"build={str(changed).lower()}\nversion={target['apps']['erpnext']}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as file:
            file.write(f"### 优化版发布门禁\n- 已发布优化版：{current['apps']['erpnext']}\n")
            file.write(f"- 标准基础版本：{target['apps']['erpnext']}\n- {status}\n")


if __name__ == "__main__":
    main()
