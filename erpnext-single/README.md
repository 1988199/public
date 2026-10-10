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

公共仓库的 GitHub Actions 每天北京时间 **10:43** 检查官方稳定版。**只有 ERPNext 自身的 V16 发布版本号变化才构建发布**；Frappe、HRMS、CRM 单独更新时只显示待处理提示，不修改已验证版本清单或重建镜像。这里的版本号变化包括 V16 内的小版本和补丁版本，不是等待 V17。

ERPNext 发布新版本后，再一并选择各组件的官方稳定版，检查配置、空站点、空目录挂载、中文网页资源，并验证上一版 latest 的临时空站点备份升级；所有测试通过后才发布版本标签和 latest，最后记录版本清单。

定时、手动运行和源码推送均遵守同一发布门禁；ERPNext 版本未变时不构建，即使其他组件更新或镜像标签缺失，也不会自动重建。需要同版本修复重发时，应另行明确授权调整发布规则。

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

[2026-10-04 镜像升级 Release](../docs/更新清单/2026-10-04.md)

[2026-10-06 镜像升级 Release](../docs/更新清单/2026-10-06.md)
