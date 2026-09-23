#!/usr/bin/env python3
"""在镜像构建期从清单获取 Frappe App；不在镜像层保存私有清单。"""

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


APP_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def load(path: Path, optional: bool = False) -> list[dict]:
    if optional and not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"App 清单必须是数组: {path}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--optional-manifest", type=Path)
    parser.add_argument("--local-app", action="append", type=Path, default=[])
    parser.add_argument("--install-list", type=Path, required=True)
    parser.add_argument("--available-list", type=Path, required=True)
    args = parser.parse_args()

    apps = load(args.manifest)
    if args.optional_manifest:
        apps.extend(load(args.optional_manifest, optional=True))

    install_on_new_site = (
        json.loads(args.install_list.read_text(encoding="utf-8"))
        if args.install_list.is_file()
        else []
    )
    if not isinstance(install_on_new_site, list) or not all(
        isinstance(name, str) and APP_NAME.fullmatch(name)
        for name in install_on_new_site
    ):
        raise ValueError(f"现有安装清单格式非法: {args.install_list}")
    seen: set[str] = set(install_on_new_site)
    for app in apps:
        name, url, ref = app["name"], app["url"], app["ref"]
        if not APP_NAME.fullmatch(name):
            raise ValueError(f"非法 App 名称: {name}")
        if name in seen:
            raise ValueError(f"重复 App: {name}")
        if not url.startswith("https://"):
            raise ValueError(f"App URL 必须使用 HTTPS: {name}")
        if not ref or any(c.isspace() for c in ref):
            raise ValueError(f"非法 ref: {name}")
        seen.add(name)
        subprocess.run(
            ["bench", "get-app", "--skip-assets", "--branch", ref, name, url],
            check=True,
        )
        if app.get("install_on_new_site", False):
            install_on_new_site.append(name)

    for path in args.local_app:
        path = path.resolve()
        name = path.name
        if not APP_NAME.fullmatch(name):
            raise ValueError(f"非法本地 App 名称: {name}")
        if name in seen:
            raise ValueError(f"重复 App: {name}")
        if not (path / "pyproject.toml").is_file():
            raise ValueError(f"本地 App 缺少 pyproject.toml: {path}")
        seen.add(name)
        if not (path / ".git").exists():
            subprocess.run(
                ["git", "init", "--initial-branch", "main", str(path)],
                check=True,
            )
            subprocess.run(["git", "-C", str(path), "add", "."], check=True)
            git_env = os.environ.copy()
            git_env.update(
                {
                    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
                    "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
                }
            )
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(path),
                    "-c",
                    "user.name=myerp build",
                    "-c",
                    "user.email=build@invalid.example",
                    "commit",
                    "-m",
                    "Bundle local app",
                ],
                check=True,
                env=git_env,
            )
        subprocess.run(
            ["bench", "get-app", "--skip-assets", path.as_uri()],
            check=True,
        )
        install_on_new_site.append(name)

    args.install_list.write_text(
        json.dumps(install_on_new_site, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    apps_txt = Path("sites/apps.txt")
    available_apps = [
        line.strip() for line in apps_txt.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if not available_apps or not all(APP_NAME.fullmatch(name) for name in available_apps):
        raise ValueError(f"生成的可用 App 清单格式非法: {apps_txt}")
    args.available_list.write_text(
        json.dumps(available_apps, ensure_ascii=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
