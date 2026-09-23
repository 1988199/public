"""仅用于 CI 合成空站点：检查入口页面、静态资源和上游中文目录。"""

import http.client
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from babel.messages.pofile import read_po


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        url = attrs.get("src") if tag == "script" else attrs.get("href") if tag == "link" else None
        if url and url.startswith("/assets/"):
            self.urls.add(url)


def main():
    site = sys.argv[1]
    if site not in {"ci.localhost", "erp.localhost"}:
        raise ValueError("此脚本仅允许用于 CI 空站点")
    cookies = {}

    def request(path, method="GET", body=None):
        conn = http.client.HTTPConnection("127.0.0.1", timeout=60)
        headers = {"Host": "localhost", "Cookie": "; ".join(f"{k}={v}" for k, v in cookies.items())}
        if body is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        conn.request(method, path, body, headers)
        response = conn.getresponse()
        for key, value in response.getheaders():
            if key.lower() == "set-cookie":
                name, val = value.split(";", 1)[0].split("=", 1)
                cookies[name] = val
        status, location = response.status, response.getheader("Location")
        content = response.read()
        conn.close()
        if status in {301, 302, 303, 307, 308}:
            parsed = urlsplit(location)
            if parsed.netloc and parsed.hostname != "localhost":
                raise AssertionError(f"异常跨站跳转: {path}")
            return request(parsed.path + ("?" + parsed.query if parsed.query else ""))
        assert status == 200, f"页面或资源返回 {status}: {path}"
        return content

    assets = set()
    parser = Assets()
    parser.feed(request("/login").decode())
    assets.update(parser.urls)
    login = json.loads(request("/api/method/login", "POST", urlencode({"usr": "Administrator", "pwd": "Pass1234"})))
    assert login["message"] == "Logged In"
    for path in ("/desk", "/desk/stock", "/desk/accounting", "/hrms", "/crm"):
        parser = Assets()
        parser.feed(request(path).decode())
        assert parser.urls, f"页面没有静态资源引用: {path}"
        assets.update(parser.urls)
        print(f"入口通过: {path}")
    for asset in sorted(assets):
        assert request(asset), f"静态资源为空: {asset}"
    print(json.dumps({"web_assets_verified": len(assets)}, ensure_ascii=False))

    for app in ("frappe", "erpnext", "hrms", "crm"):
        root = Path("/home/frappe/frappe-bench/apps") / app
        paths = sorted(root.glob("**/locale/zh.po"))
        assert paths, f"未找到官方中文目录: {app}"
        for path in paths:
            raw = path.read_text(encoding="utf-8")
            language = re.search(r'"Language: ([^\\]*)', raw)
            with path.open("rb") as stream:
                catalog = read_po(stream, locale="zh")
            messages = [m for m in catalog if m.id]
            empty = sum(not m.string or (isinstance(m.string, (list, tuple)) and not any(m.string)) for m in messages)
            print(json.dumps({"app": app, "file": str(path.relative_to(root)), "language_header": language.group(1) if language else None, "entries": len(messages), "empty": empty}, ensure_ascii=False))


if __name__ == "__main__":
    main()
