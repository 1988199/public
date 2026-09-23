# EspoCRM 中文单容器镜像

将 EspoCRM、MariaDB 和 Supervisor 整合在一个 Docker 容器中，面向简体中文、小型单机及学习测试场景。镜像基于 EspoCRM 官方容器，并由本仓库维护单容器启动、数据持久化和低内存配置；它不是 EspoCRM 官方发行镜像。

- 镜像：`ghcr.io/1988199/espocrm-cn-single`
- 当前版本：见本目录 `VERSION`；自动发布 `latest`、版本号和 `espocrm-版本号` 标签。
- 架构：`linux/amd64`
- 默认访问端口：主机 `8080` 映射到容器 `80`。
- 持久化目录：容器 `/data`，Compose 默认映射到本目录下的 `./data`。

## 快速启动

先复制环境变量示例文件，替换所有 `CHANGE_ME` 密码，并填写浏览器实际访问地址：

```bash
cp .env.example .env
```

编辑 `.env`，本机测试可以将 `ESPOCRM_SITE_URL` 设为 `http://localhost:8080`。服务器部署应填写用户访问的完整域名或 IP；如果前面使用 HTTPS 反向代理，填写外部 HTTPS 地址。管理员密码、应用数据库密码和 MariaDB root 密码必须分别设置为强且互不相同的值。

然后启动：

```bash
docker compose up -d
docker compose logs -f espocrm
```

浏览器打开 `.env` 中配置的 `ESPOCRM_SITE_URL`。首次启动会初始化数据库和简体中文站点，等待日志出现初始化完成后登录。默认管理员用户名为 `admin`（可通过 `ESPOCRM_ADMIN_USERNAME` 修改），管理员密码使用 `ESPOCRM_ADMIN_PASSWORD` 设置的值。首次启动完成后，环境变量不会自动重置已有站点的管理员密码。

停止服务但保留数据：

```bash
docker compose down
```

不要使用 `docker compose down -v` 清理运行环境；备份并确认数据后再手工处理 `./data`。

## 配置项

| 变量 | 用途 |
| --- | --- |
| `HTTP_PORT` | 主机访问端口，默认 `8080` |
| `ESPOCRM_SITE_URL` | 浏览器使用的完整站点 URL，须与实际访问入口一致 |
| `ESPOCRM_ADMIN_USERNAME` / `ESPOCRM_ADMIN_PASSWORD` | 首次初始化的管理员账号和密码 |
| `ESPOCRM_DATABASE_PASSWORD` | EspoCRM 应用数据库账号密码 |
| `MARIADB_ROOT_PASSWORD` | MariaDB root 密码 |

EspoCRM 语言、时区和默认币种由镜像设置为简体中文（`zh_CN`）、上海（`Asia/Shanghai`）和人民币（`CNY`）。

## 自动构建与升级

`.github/workflows/espocrm-auto-build.yml` 在项目变更、手动运行及每日定时检查时触发。工作流查询 EspoCRM 官方 Docker Hub 稳定标签，构建 `linux/amd64` 镜像并推送到 GHCR；成功后更新本目录的 `VERSION` 和 Dockerfile 默认版本。发布标签为：

```text
ghcr.io/1988199/espocrm-cn-single:latest
ghcr.io/1988199/espocrm-cn-single:10.0.8
ghcr.io/1988199/espocrm-cn-single:espocrm-10.0.8
```

升级前先备份整个 `./data`，并保留当前镜像版本。获取新版后使用原数据目录启动；不要在没有可用备份时升级。自动构建只负责生成镜像，不会连接或修改用户正在运行的系统。

## 数据与安全

- 管理员密码、数据库密码、站点配置、附件和数据库都属于运行数据，不应提交到公共仓库。
- `.env`、`data/`、备份及日志已由本目录 `.gitignore` 排除；提交前仍应检查 Git 状态。
- `.env.example` 中的 `CHANGE_ME` 仅是占位符，运行前必须全部替换。不要将示例密码或公开网络上的默认密码用于真实环境。
- 单容器把 Web 和数据库放在同一故障域，适合学习与小规模测试；正式上线前还需完成备份恢复、访问控制、容量和安全评估。

## 上游

- [EspoCRM 官方容器](https://hub.docker.com/r/espocrm/espocrm)
- [EspoCRM 官方 GitHub](https://github.com/espocrm/espocrm)
- [本项目自动构建工作流](../.github/workflows/espocrm-auto-build.yml)
