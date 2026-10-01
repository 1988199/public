# EspoCRM 中文单容器

基于 EspoCRM 官方容器构建，集成 MariaDB，预设简体中文、上海时区和人民币。镜像适用于单机 Docker 部署。

镜像：`ghcr.io/1988199/espocrm-cn-single`

提供 `latest`、上游版本号和 `espocrm-版本号` 标签；当前版本见 [`VERSION`](VERSION)。支持 `linux/amd64`，主机默认端口 `8080`，数据统一持久化到 `./data`。

## 启动

```bash
cp .env.example .env
```

编辑 `.env`：替换所有 `CHANGE_ME` 值，设置强管理员和数据库密码，并将 `ESPOCRM_SITE_URL` 改为实际访问地址。本机默认可用 `http://localhost:8080`。

```bash
docker compose up -d
docker compose logs -f espocrm
```

首次启动完成后访问配置的站点地址，以 `ESPOCRM_ADMIN_USERNAME` 和 `ESPOCRM_ADMIN_PASSWORD` 登录。更新容器时保留 `./data`。

## 自动更新与发布

GitHub Actions 每天北京时间 **10:17** 查询 EspoCRM 官方 GitHub 稳定发布并验证对应 Docker 标签，也可手动运行。需要发布时，工作流构建候选镜像，通过首次启动、HTTP、中文配置和容器重建后的持久化测试后，再推送三个标签；成功后更新 `VERSION` 与 Dockerfile 中的默认版本。版本未变且三个发布标签均存在时，定时任务跳过构建。

工作流文件：[`.github/workflows/espocrm-auto-build.yml`](../.github/workflows/espocrm-auto-build.yml)。自动构建只发布容器镜像，不操作运行中的实例。

测试失败不会发布候选镜像或更新已验证版本，下次每日检查会重新尝试。Actions 运行摘要显示官方版本、已记录版本及是否需要构建；检查成功不等于生成新镜像。发布只更新镜像仓库，不自动替换已运行的容器。

以上为计划检查时间，GitHub 的定时调度可能延迟；公开仓库连续 60 天没有活动时，定时工作流可能被自动停用。可在 Actions 页面检查运行记录、重新启用或手动执行。详见 [GitHub 定时任务说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。

## 配置

| 变量 | 说明 |
| --- | --- |
| `HTTP_PORT` | 主机访问端口，默认 `8080` |
| `ESPOCRM_SITE_URL` | 用户访问 CRM 的完整 URL |
| `ESPOCRM_ADMIN_USERNAME` / `ESPOCRM_ADMIN_PASSWORD` | 首次初始化的管理员账号 |
| `ESPOCRM_DATABASE_PASSWORD` | EspoCRM 数据库密码 |
| `MARIADB_ROOT_PASSWORD` | MariaDB 管理密码 |

本项目基于 [EspoCRM 官方容器](https://hub.docker.com/r/espocrm/espocrm)构建；EspoCRM 及相关组件遵循各自许可证。


## 更新记录

[2026-09-30 镜像更新清单](../docs/更新清单/2026-09-30.md)
