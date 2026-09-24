#!/usr/bin/env python3
"""不依赖第三方包的仓库结构与公共数据边界检查。"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    ".github/workflows/image.yml",
    ".github/workflows/validate.yml",
    "AGENTS.md",
    "apps/china_sme_accounting/china_sme_accounting/hooks.py",
    "apps/china_sme_accounting/china_sme_accounting/standards/cn_sme_2011_v1/accounts.json",
    "apps/china_sme_accounting/china_sme_accounting/standards/cn_sme_2011_v1/manifest.json",
    "apps/china_sme_accounting/pyproject.toml",
    "README.md",
    "Dockerfile",
    "compose.yaml",
    "docker/apps.json",
    "docker/upstream.lock.json",
    "docker/entrypoint.sh",
    "docker/install_apps.py",
    "docker/install_translations.py",
    "docker/mariadb.cnf",
    "docker/redis.conf",
    "docker/translations.json",
    "docs/Docker基础架构设计.md",
    "docs/中国小企业会计准则App设计.md",
    "docs/私有企业初始化方案.md",
    "docs/架构说明.md",
    "docs/版本清单.md",
    "docs/中文本地化.md",
    "docs/升级指南.md",
    "schemas/private-enterprise-init-manifest.schema.json",
    "scripts/ci-smoke-test.sh",
    "scripts/detect-latest.py",
}
FORBIDDEN_NAMES = {".env", "site_config.json", "common_site_config.json"}
FORBIDDEN_SUFFIXES = {".sql", ".key", ".pem", ".tgz"}
FORBIDDEN_PARTS = {"enterprise-data", "init-packages", "tenant-data"}
SECRET_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|secret[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_/+.-]{12,}"
)

CN_SME_ACCOUNTS = {
    "1001": "库存现金", "1002": "银行存款", "1012": "其他货币资金", "1101": "短期投资",
    "1121": "应收票据", "1122": "应收账款", "1123": "预付账款", "1131": "应收股利",
    "1132": "应收利息", "1221": "其他应收款", "1401": "材料采购", "1402": "在途物资",
    "1403": "原材料", "1404": "材料成本差异", "1405": "库存商品", "1407": "商品进销差价",
    "1408": "委托加工物资", "1411": "周转材料", "1421": "消耗性生物资产", "1501": "长期债券投资",
    "1511": "长期股权投资", "1601": "固定资产", "1602": "累计折旧", "1604": "在建工程",
    "1605": "工程物资", "1606": "固定资产清理", "1621": "生产性生物资产",
    "1622": "生产性生物资产累计折旧", "1701": "无形资产", "1702": "累计摊销",
    "1801": "长期待摊费用", "1901": "待处理财产损溢", "2001": "短期借款", "2201": "应付票据",
    "2202": "应付账款", "2203": "预收账款", "2211": "应付职工薪酬", "2221": "应交税费",
    "2231": "应付利息", "2232": "应付利润", "2241": "其他应付款", "2401": "递延收益",
    "2501": "长期借款", "2701": "长期应付款", "3001": "实收资本", "3002": "资本公积",
    "3101": "盈余公积", "3103": "本年利润", "3104": "利润分配", "4001": "生产成本",
    "4101": "制造费用", "4301": "研发支出", "4401": "工程施工", "4403": "机械作业",
    "5001": "主营业务收入", "5051": "其他业务收入", "5111": "投资收益", "5301": "营业外收入",
    "5401": "主营业务成本", "5402": "其他业务成本", "5403": "税金及附加", "5601": "销售费用",
    "5602": "管理费用", "5603": "财务费用", "5711": "营业外支出", "5801": "所得税费用",
}


def fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def main() -> int:
    errors: list[str] = []
    for relative in sorted(REQUIRED):
        if not (ROOT / relative).is_file():
            fail(f"缺少文件: {relative}", errors)

    apps_path = ROOT / "docker/apps.json"
    lock_path = ROOT / "docker/upstream.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else {}
    if apps_path.is_file():
        apps = json.loads(apps_path.read_text(encoding="utf-8"))
        expected = {"erpnext", "hrms", "crm"}
        names = {app.get("name") for app in apps}
        if not expected.issubset(names):
            fail("官方 App 清单必须包含 erpnext、hrms 和 crm", errors)
        for app in apps:
            if not str(app.get("url", "")).startswith("https://github.com/frappe/"):
                fail(f"公共 App 不是 Frappe 官方来源: {app.get('name')}", errors)
        expected_majors = {"erpnext": 16, "hrms": 16, "crm": 1}
        for name, major in expected_majors.items():
            app = next((item for item in apps if item.get("name") == name), {})
            if not re.fullmatch(rf"v{major}\.[0-9]+\.[0-9]+", str(app.get("ref", ""))):
                fail(f"{name} 必须固定到 V{major} 正式标签", errors)
            if lock.get(name, {}).get("ref") != app.get("ref"):
                fail(f"{name} 标签与官方来源锁文件不一致", errors)
            if lock.get(name, {}).get("repository") != f"frappe/{name}":
                fail(f"{name} 锁文件来源不正确", errors)

    for name, source in lock.items():
        if name not in {"frappe", "erpnext", "hrms", "crm"}:
            fail(f"来源锁文件含未知 App: {name}", errors)
        if not re.fullmatch(r"[0-9a-f]{40}", str(source.get("sha", ""))):
            fail(f"{name} 官方提交 SHA 不正确", errors)

    dockerfile_path = ROOT / "Dockerfile"
    if dockerfile_path.is_file():
        dockerfile = dockerfile_path.read_text(encoding="utf-8")
        frappe_match = re.search(r"^ARG FRAPPE_REF=(v16\.[0-9]+\.[0-9]+)$", dockerfile, re.M)
        if not frappe_match:
            fail("Frappe 必须固定到 V16 正式标签", errors)
        if frappe_match and lock.get("frappe", {}).get("ref") != frappe_match.group(1):
            fail("Frappe 标签与官方来源锁文件不一致", errors)
        compose_path = ROOT / "compose.yaml"
        if frappe_match and compose_path.is_file() and f"FRAPPE_REF: {frappe_match.group(1)}" not in compose_path.read_text(encoding="utf-8"):
            fail("Compose Frappe 版本必须与 Dockerfile 一致", errors)
        if (
            "frappe/bench:v5.31.0@sha256:"
            "6df74bce06ab017aa350a16ffdc7aff4559a4a1bf3d785d8e552dacc19b5f0e7"
            not in dockerfile
        ):
            fail("frappe/bench 基础镜像必须固定到 v5.31.0 及已验证 digest", errors)
        exposed_ports = re.findall(r"^EXPOSE\s+(.+)$", dockerfile, re.M)
        if exposed_ports != ["80"] or "FROM scratch AS runtime" not in dockerfile:
            fail("最终镜像只能声明 80 端口，并且不得继承 bench 开发端口", errors)
        if "cn_small_enterprise_accounting_standard.json" not in dockerfile:
            fail("Dockerfile 必须注册中国小企业会计准则模板", errors)
        if "--available-list /home/frappe/frappe-bench/apps-available.json" not in dockerfile:
            fail("Dockerfile 必须保存镜像可用 App 清单，用于已有站点升级", errors)
        if "ADMIN_PASSWORD=Pass1234" not in dockerfile:
            fail("当前测试镜像必须内置 Administrator 测试密码", errors)
        if (
            "env/bin/python /usr/local/lib/erpnext/install_translations.py" not in dockerfile
            or "translations/zh.csv" not in dockerfile
        ):
            fail("Dockerfile 必须构建独立 App 的简体中文补充翻译", errors)
        if dockerfile.count("--mount=type=cache,id=myerp-yarn") < 2:
            fail("Dockerfile 必须以 BuildKit cache mount 复用且隔离 Yarn 缓存", errors)
        if "cp -a /home/frappe/frappe-bench/sites/assets /opt/erpnext-assets" not in dockerfile:
            fail("Dockerfile 必须在持久卷之外保存当前镜像的静态资源快照", errors)
        if "/home/frappe/frappe-bench/apps/frappe/node_modules" in dockerfile:
            fail("Dockerfile 不得删除 Frappe WebSocket 运行所需的 node_modules", errors)

    install_apps_path = ROOT / "docker/install_apps.py"
    if install_apps_path.is_file():
        install_apps = install_apps_path.read_text(encoding="utf-8")
        if install_apps.count('"--skip-assets"') < 2:
            fail("所有 App 获取步骤必须跳过重复资源编译，由最终生产构建统一处理", errors)

    translations_path = ROOT / "docker/translations.json"
    if translations_path.is_file():
        translations = json.loads(translations_path.read_text(encoding="utf-8"))
        if translations.get("language") != "zh":
            fail("翻译清单必须使用简体中文 zh", errors)
        if int(translations.get("minimum_entries", 0)) < 5700:
            fail("Frappe 官方简体中文基线条目门禁过低", errors)
        for source in translations.get("sources", []):
            if not str(source.get("url", "")).startswith(
                "https://raw.githubusercontent.com/frappe/frappe/"
            ):
                fail("简体中文基线必须来自 Frappe 官方 GitHub", errors)
            if not re.fullmatch(r"[0-9a-f]{64}", str(source.get("sha256", ""))):
                fail("简体中文基线必须固定 SHA-256", errors)
        required_translations = translations.get("required_translations", {})
        for source in {"Save", "Submit", "Cancel", "Search"}:
            if not required_translations.get(source):
                fail(f"翻译清单缺少关键译文门禁: {source}", errors)

    entrypoint_path = ROOT / "docker/entrypoint.sh"
    if entrypoint_path.is_file():
        entrypoint = entrypoint_path.read_text(encoding="utf-8")
        if 'ADMIN_PASSWORD="${ADMIN_PASSWORD:-Pass1234}"' not in entrypoint:
            fail("入口脚本必须在未传入 ADMIN_PASSWORD 时使用测试默认值", errors)
        if 'list-apps --format json' not in entrypoint or 'grep -Fxq "$app"' not in entrypoint:
            fail("入口脚本必须为已有站点安装镜像清单中新增的 App", errors)
        if '"$BENCH_DIR/apps-available.json"' not in entrypoint or 'mv -f "$apps_txt_tmp"' not in entrypoint:
            fail("入口脚本必须在安装前同步持久化 sites/apps.txt", errors)
        if 'cp -a --remove-destination /opt/erpnext-assets/. "$BENCH_DIR/sites/assets/"' not in entrypoint:
            fail("入口脚本必须同步新镜像静态资源，避免升级后使用旧资源清单", errors)

    smoke_test_path = ROOT / "scripts/ci-smoke-test.sh"
    if smoke_test_path.is_file():
        smoke_test = smoke_test_path.read_text(encoding="utf-8")
        if "--env ADMIN_PASSWORD" in smoke_test:
            fail("镜像烟雾测试不得显式传入 ADMIN_PASSWORD，必须覆盖默认值路径", errors)
        if "'pwd=Pass1234'" not in smoke_test or '"message":"Logged In"' not in smoke_test:
            fail("镜像烟雾测试必须验证 Administrator 默认密码可登录", errors)
        if "tests.localization.run" not in smoke_test or '"key_translations_verified": true' not in smoke_test:
            fail("镜像烟雾测试必须验证简体中文关键译文", errors)
        if 'for app in frappe erpnext hrms crm' not in smoke_test:
            fail("镜像烟雾测试必须逐一核对官方 App 的实际版本", errors)
        if 'CI_OMIT_SITE_NAME' not in smoke_test:
            fail("镜像烟雾测试必须覆盖未设置 SITE_NAME 的启动路径", errors)
        if r"^china_sme_accounting[[:space:]]+0\.2\.0" not in smoke_test:
            fail("镜像烟雾测试必须核对中国本地化 App 版本", errors)

    chart_path = (
        ROOT
        / "apps/china_sme_accounting/china_sme_accounting/standards/cn_sme_2011_v1/accounts.json"
    )
    app_version_path = ROOT / "apps/china_sme_accounting/china_sme_accounting/__init__.py"
    if app_version_path.is_file() and '__version__ = "0.2.0"' not in app_version_path.read_text(
        encoding="utf-8"
    ):
        fail("中国本地化 App 版本必须为 0.2.0", errors)

    if chart_path.is_file():
        chart = json.loads(chart_path.read_text(encoding="utf-8"))
        if chart.get("name") != "中国小企业会计准则":
            fail("中国小企业会计准则模板名称不正确", errors)
        if chart.get("standard_code") != "CN-SME-2011-v1":
            fail("中国小企业会计准则模板版本标识不正确", errors)

        actual_accounts: dict[str, str] = {}
        inherited_types: dict[str, str] = {}
        for root_name, root in chart.get("tree", {}).items():
            root_type = root.get("root_type")
            if root_type not in {"Asset", "Liability", "Equity", "Income", "Expense"}:
                fail(f"非法根账户类型: {root_name}={root_type}", errors)
            for account_name, account in root.items():
                if account_name in {"is_group", "root_type"}:
                    continue
                number = str(account.get("account_number", ""))
                if not number or number != number.strip():
                    fail(f"中国准则科目编码为空或带空格: {account_name}", errors)
                    continue
                if number in actual_accounts:
                    fail(f"中国准则科目编码重复: {number}", errors)
                actual_accounts[number] = account_name
                inherited_types[number] = root_type

        if actual_accounts != CN_SME_ACCOUNTS:
            fail("中国准则科目必须与经核对的 66 个一级科目完全一致", errors)
        if any(inherited_types.get(number) != "Income" for number in {"5001", "5051", "5111", "5301"}):
            fail("损益类收入科目必须继承 ERPNext Income 根类型", errors)
        if any(inherited_types.get(number) != "Expense" for number in {"5401", "5402", "5403", "5601", "5602", "5603", "5711", "5801"}):
            fail("损益类费用科目必须继承 ERPNext Expense 根类型", errors)

        manifest_path = chart_path.with_name("manifest.json")
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            actual_hash = hashlib.sha256(chart_path.read_bytes()).hexdigest()
            if manifest.get("accounts_sha256") != actual_hash:
                fail("中国准则科目文件哈希与 manifest.json 不一致", errors)

    for path in ROOT.rglob("*"):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative = path.relative_to(ROOT)
        if FORBIDDEN_PARTS.intersection(relative.parts):
            fail(f"禁止提交的企业数据目录: {relative}", errors)
        if path.name in FORBIDDEN_NAMES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            fail(f"禁止提交的数据/密钥文件: {relative}", errors)
        if path.stat().st_size <= 1_000_000:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if SECRET_PATTERN.search(text):
                fail(f"疑似硬编码秘密: {relative}", errors)

    if errors:
        print("验证失败：")
        for error in errors:
            print(f"- {error}")
        return 1
    print("验证通过：结构、官方 App 来源和公共数据边界符合当前规则。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
