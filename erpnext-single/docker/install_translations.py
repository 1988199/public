#!/usr/bin/env python3
"""在镜像构建期校验并安装简体中文补充翻译。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import urllib.parse
import urllib.request
from pathlib import Path
from string import Formatter

from babel.messages.pofile import read_po


ALLOWED_HOST = "raw.githubusercontent.com"
ALLOWED_PATH_PREFIX = "/frappe/"


def download(source: dict) -> bytes:
    url = str(source.get("url", ""))
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
        raise ValueError(f"翻译源必须来自 Frappe 官方 GitHub Raw: {url}")
    if not parsed.path.startswith(ALLOWED_PATH_PREFIX):
        raise ValueError(f"翻译源不在 Frappe 官方组织下: {url}")

    with urllib.request.urlopen(url, timeout=60) as response:
        content = response.read()
    actual = hashlib.sha256(content).hexdigest()
    expected = str(source.get("sha256", ""))
    if actual != expected:
        raise ValueError(
            f"翻译源哈希不匹配: {source.get('name', url)}，期望 {expected}，实际 {actual}"
        )
    return content


def message_text(value: str | tuple[str, ...] | list[str]) -> str:
    if isinstance(value, (tuple, list)):
        return str(value[0]) if value else ""
    return str(value or "")


def load_po(content: bytes) -> dict[tuple[str, str], str]:
    catalog = read_po(io.BytesIO(content), locale="zh")
    translations: dict[tuple[str, str], str] = {}
    for message in catalog:
        source = message_text(message.id)
        target = message_text(message.string)
        if not source or not target or message.fuzzy:
            continue
        translations[(source, message.context or "")] = target
    return translations


def load_overrides(path: Path) -> dict[tuple[str, str], str]:
    translations: dict[tuple[str, str], str] = {}
    if not path.is_file():
        return translations
    with path.open(encoding="utf-8", newline="") as stream:
        for row_number, row in enumerate(csv.reader(stream), start=1):
            if len(row) not in {2, 3} or not row[0] or not row[1]:
                raise ValueError(f"补充翻译第 {row_number} 行格式非法: {path}")
            source_fields = {name for _, name, _, _ in Formatter().parse(row[0]) if name}
            target_fields = {name for _, name, _, _ in Formatter().parse(row[1]) if name}
            if source_fields != target_fields:
                raise ValueError(
                    f"补充翻译第 {row_number} 行占位符不一致: "
                    f"{source_fields} != {target_fields}"
                )
            context = row[2] if len(row) == 3 else ""
            translations[(row[0], context)] = row[1]
    return translations


def write_csv(path: Path, translations: dict[tuple[str, str], str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        for (source, context), target in sorted(translations.items()):
            row = [source.replace("\n", "\\n"), target.replace("\n", "\\n")]
            if context:
                row.append(context)
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--overrides", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("language") != "zh":
        raise ValueError("当前构建器仅允许生成简体中文 zh 翻译")

    translations: dict[tuple[str, str], str] = {}
    for source in manifest.get("sources", []):
        translations.update(load_po(download(source)))
    official_count = len(translations)
    minimum_entries = int(manifest.get("minimum_entries", 0))
    if official_count < minimum_entries:
        raise ValueError(f"有效官方译文不足: {official_count} < {minimum_entries}")

    translations.update(load_overrides(args.overrides))
    flat = {source: target for (source, context), target in translations.items() if not context}
    for source, expected in manifest.get("required_translations", {}).items():
        if flat.get(source) != expected:
            raise ValueError(f"关键译文不正确: {source} -> {flat.get(source)!r}")

    write_csv(args.target, translations)
    print(
        f"已生成 {args.target}: 官方译文 {official_count} 条，"
        f"合并补充后 {len(translations)} 条。"
    )


if __name__ == "__main__":
    main()
