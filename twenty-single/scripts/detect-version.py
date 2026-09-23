#!/usr/bin/env python3
"""Resolve only official stable Twenty releases, then verify a Docker image exists."""
import json
import os
import re
import subprocess
import urllib.request

headers = {"Accept": "application/vnd.github+json", "User-Agent": "twenty-single-builder"}
if os.environ.get("GH_TOKEN"):
    headers["Authorization"] = "Bearer " + os.environ["GH_TOKEN"]
request = urllib.request.Request("https://api.github.com/repos/twentyhq/twenty/releases/latest", headers=headers)
with urllib.request.urlopen(request, timeout=60) as response:
    release = json.load(response)
match = re.fullmatch(r"(?:twenty/)?v?(\d+\.\d+\.\d+)", release["tag_name"])
if release["draft"] or release["prerelease"] or not match:
    raise SystemExit("Latest official release is not a recognized stable Twenty version")
version = match[1]
for tag in ["v" + version, version]:
    result = subprocess.run(["docker", "buildx", "imagetools", "inspect", "twentycrm/twenty:" + tag], capture_output=True, text=True)
    if result.returncode == 0:
        break
else:
    raise SystemExit(f"Official stable release {version} has no accessible Docker image; refusing to publish")
print(f"Official release: {release['html_url']}; Docker tag: {tag}")
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
    output.write(f"version={version}\ntag={tag}\n")
