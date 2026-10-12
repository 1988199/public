"""验证登录、Desk、CRM 页面及引用的本地静态资源。"""
import os
from html.parser import HTMLParser
from urllib.parse import urlparse

import requests


class Assets(HTMLParser):
    def __init__(self):
        super().__init__()
        self.urls = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        value = attrs.get("src") if tag == "script" else attrs.get("href") if tag == "link" else None
        if value and value.startswith("/assets/"):
            self.urls.add(value)


session = requests.Session()
session.headers["Host"] = os.environ["SITE_NAME"]
base = "http://127.0.0.1"
response = session.post(base + "/api/method/login", data={"usr": "Administrator", "pwd": os.environ["CI_SITE_PASSWORD"]}, timeout=30)
response.raise_for_status()
assert response.json()["message"] == "Logged In"
count = 0
for page in ["/login", "/desk", "/crm"]:
    response = session.get(base + page, timeout=30)
    response.raise_for_status()
    assert "Traceback (most recent call last)" not in response.text
    assets = Assets()
    assets.feed(response.text)
    for url in sorted(assets.urls):
        response = session.get(base + url, timeout=30)
        response.raise_for_status()
        assert response.content
        count += 1
assert count >= 3
print("登录、Desk、CRM 与静态资源检查通过：", count)
