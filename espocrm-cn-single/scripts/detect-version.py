#!/usr/bin/env python3
"""核对官方稳定发布和对应的 Docker 标签，拒绝自动降级。"""
import json
import os
import re
import subprocess
import urllib.request
from pathlib import Path

headers = {"Accept": "application/vnd.github+json", "User-Agent": "espocrm-single-builder"}
if os.environ.get("GH_TOKEN"):
    headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
request = urllib.request.Request(
    "https://api.github.com/repos/espocrm/espocrm/releases?per_page=100", headers=headers
)
with urllib.request.urlopen(request, timeout=60) as response:
    releases = json.load(response)
versions = [
    r["tag_name"].removeprefix("v")
    for r in releases
    if not r["draft"] and not r["prerelease"]
    and re.fullmatch(r"v?\d+\.\d+\.\d+", r["tag_name"])
]
if not versions:
    raise SystemExit("未找到 EspoCRM 官方稳定发布")
key = lambda value: tuple(map(int, value.split(".")))
latest = max(versions, key=key)
current = (Path(__file__).resolve().parents[1] / "VERSION").read_text().strip()
if key(latest) < key(current):
    raise SystemExit("官方版本回退，拒绝降级")
subprocess.run(
    ["docker", "buildx", "imagetools", "inspect", "espocrm/espocrm:" + latest],
    check=True,
)
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
    output.write(f"current={current}\nlatest={latest}\n")
print(f"EspoCRM: {current} -> {latest}")
