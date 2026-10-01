# ERPNext V16 中文单容器

基于 ERPNext、Frappe Framework、Frappe HRMS 和 Frappe CRM 官方源码构建的单容器 Docker 镜像，提供简体中文环境及中国小企业会计准则科目表。

镜像：`ghcr.io/1988199/erpnext-single`

发布标签包括带 `V` 前缀的 ERPNext 版本号（如 `V16.37.0`）和 `latest`。当前上游版本见 [`docker/upstream.lock.json`](docker/upstream.lock.json)。

## 快速开始

1. 下载本目录的 Compose 配置及环境变量示例。
2. 将 `.env.example` 复制为 `.env`，设置管理员密码和数据库密码；默认镜像为 `ghcr.io/1988199/erpnext-single:latest`，也可将 `IMAGE_NAME` 改为指定版本标签。
3. 启动容器：

```powershell
Copy-Item .env.example .env
# 编辑 .env 后执行
docker compose pull
docker compose up -d --no-build
docker compose logs -f erpnext
```

首次启动会初始化空站点。默认浏览器入口为 `http://localhost:8080`；自定义端口请修改 `HTTP_PORT`。Compose 会将数据库、Redis、站点文件和日志分别保存在 Docker volumes 中。

容器镜像仅声明网页端口 `80`，默认映射为宿主机 `8080:80`。Gunicorn 和 Socket.IO 使用的 `8000`、`9000` 仅供容器内部 Nginx 通信，不发布到宿主机。

## 自动更新与发布

公共仓库的 GitHub Actions 每天北京时间 **10:43** 检查 Frappe V16、ERPNext V16、HRMS V16 和 CRM 的官方稳定版，也可手动运行。任一组件出现新版本后，自动生成候选镜像，检查配置、空站点安装、两种 `SITE_NAME` 启动方式、中文关键译文及网页资源，并从已发布的 `latest` 完成临时空站点备份与升级测试。所有测试成功后才发布版本标签和 `latest`，最后记录已验证的上游版本；版本未变且已有 `latest` 时，定时任务跳过构建。

测试失败不会发布候选镜像或更新已验证版本，下次每日检查会重新尝试。Actions 运行摘要区分“无更新，跳过构建”“测试通过并发布”和失败；检查成功不等于生成新镜像。发布只更新镜像仓库，不自动替换已运行的容器或迁移企业数据。

以上为计划检查时间，GitHub 的定时调度可能延迟；公开仓库连续 60 天没有活动时，定时工作流可能被自动停用。可在 Actions 页面检查运行记录、重新启用或手动执行。详见 [GitHub 定时任务说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

工作流文件：[`.github/workflows/erpnext-auto-build.yml`](../.github/workflows/erpnext-auto-build.yml)。镜像发布使用 GitHub Actions 的 `GITHUB_TOKEN`。

## 组件

- ERPNext V16、Frappe Framework V16、Frappe HRMS、Frappe CRM
- MariaDB、Redis、Nginx、WebSocket、后台队列和调度器
- 中国小企业会计准则公共科目表及中文补充翻译

上游项目分别遵循其各自许可证；本项目的许可证见 [`LICENSE`](LICENSE)。



## 更新记录

[2026-09-30 镜像更新清单](../docs/更新清单/2026-09-30.md)
