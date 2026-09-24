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
request = urllib.request.Request("https://api.github.com/repos/twentyhq/twenty/releases?per_page=100", headers=headers)
with urllib.request.urlopen(request, timeout=60) as response:
    releases = json.load(response)

# The repository also publishes SDK releases (for example sdk/v2.41.0).
# Prefer application releases explicitly named twenty/vX.Y.Z.
candidates = []
for release in releases:
    if release["draft"] or release["prerelease"]:
        continue
    tag_name = release["tag_name"]
    app_match = re.fullmatch(r"twenty/v(\d+\.\d+\.\d+)", tag_name)
    if app_match:
        candidates.append((2, tuple(map(int, app_match[1].split("."))), release, app_match[1]))
        continue
    if tag_name.startswith("sdk/"):
        continue
    fallback_match = re.fullmatch(r"v?(\d+\.\d+\.\d+)", tag_name)
    if fallback_match:
        candidates.append((1, tuple(map(int, fallback_match[1].split("."))), release, fallback_match[1]))

if not candidates:
    raise SystemExit("No recognized stable Twenty application release was found")
_, _, release, version = max(candidates, key=lambda item: (item[0], item[1]))
for tag in ["v" + version, version]:
    result = subprocess.run(["docker", "buildx", "imagetools", "inspect", "twentycrm/twenty:" + tag], capture_output=True, text=True)
    if result.returncode == 0:
        break
else:
    raise SystemExit(f"Official stable release {version} has no accessible Docker image; refusing to publish")
print(f"Official release: {release['html_url']}; Docker tag: {tag}")
with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
    output.write(f"version={version}\ntag={tag}\n")
