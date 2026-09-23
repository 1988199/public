# ERPNext V16 中文单容器发行版

这是一个面向简体中文环境的 ERPNext V16 Docker 发行版。镜像构建时直接获取 Frappe、ERPNext、Frappe HRMS 和 Frappe CRM 官方 GitHub 源码；仓库保存基础设施、版本清单、中文技术文档，以及独立的中国小企业会计准则与中文补充翻译 App，不保存任何企业业务数据。

> 当前包含经财政部来源核对的 66 个小企业会计准则一级科目，供新建中国公司选择。它是公共标准元数据，不包含公司、期初余额、凭证或其他企业业务数据。

## 设计目标

- 单个 Docker 容器承载 MariaDB、Redis、Web、WebSocket、队列、调度器和 Nginx。
- 当前发行组合固定为 Frappe `v16.35.0`、ERPNext `v16.35.0`、HRMS `v16.20.0` 和 CRM `v1.84.0`。
- 内置独立 `china_sme_accounting` App，提供“中国小企业会计准则”建账模板；企业专属会计扩展仍通过构建密钥接口接入。
- 数据库、站点和日志使用独立 Docker volume；镜像可以替换，业务数据不进入镜像。
- 通过 App 清单、升级流程和 CI 校验持续跟随 V16。

## 仓库结构

```text
.
├── .github/workflows/erpnext-auto-build.yml # 每日检查版本并构建发布镜像
├── apps/china_sme_accounting/      # 中国小企业会计准则公共元数据 App
├── docker/                         # 构建、进程管理与反向代理
│   ├── apps.json                   # 官方 App 来源和版本线
│   ├── apps.extra.example.json     # 私有扩展清单格式示例
│   ├── entrypoint.sh               # 空站点初始化与迁移
│   ├── install_apps.py             # 构建期 App 获取器
│   ├── nginx.conf
│   └── supervisord.conf
├── docs/                           # 中文架构、扩展和升级说明
├── scripts/validate.py             # 本地静态检查
├── AGENTS.md                       # 长期维护规则
├── compose.yaml
└── Dockerfile
```

## 本地架构验证

```powershell
python scripts/validate.py
docker compose --env-file .env.example config --quiet
```

GitHub Actions 会在本项目文件变更及每日定时检查官方稳定版时运行。发布前测试带 `SITE_NAME`、未设置 `SITE_NAME` 的两种新建站点启动、`localhost` 页面资源，以及上一版空站点备份升级。成功后发布 `ghcr.io/1988199/erpnext:V16.35.0`、`:16.35.0` 等具体版本标签；`main` 通过测试后还发布 `:latest`。精确复现应使用成品镜像 digest。

如需试构建，先复制环境变量示例并更换密码：

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d
```

首次启动会创建一个没有业务数据的站点并安装 ERPNext、HRMS、CRM 和中国小企业会计准则 App。新建国家为“中国”的公司时，可直接选择“中国小企业会计准则”。默认入口为 `http://localhost:8080`（若设置 `HTTP_PORT=8090`，则为 `http://localhost:8090`）。`SITE_NAME` 是容器内部站点名；既有卷中的 `erp.localhost` 无需改名，Nginx 会将浏览器的 `localhost` 请求转给它。

当前测试镜像在未提供环境变量时，数据库 root 密码和首次建站的 ERPNext `Administrator` 密码均默认为 `Pass1234`。可分别通过 `DB_ROOT_PASSWORD` 和 `ADMIN_PASSWORD` 覆盖。管理员默认密码只在创建新站点时写入，不会重置已有数据卷内的站点密码。该测试例外不得用于正式环境或对外联网部署。

## 重要限制

单容器是明确的产品约束，适合单机部署、内部测试和 PoC，但数据库、缓存与应用无法独立扩缩容或滚动升级。正式上线前必须完成备份恢复、容量、并发、崩溃恢复和安全测试。官方 Frappe Docker 的生产推荐仍是多服务拓扑。

详细说明见 [Docker 基础架构设计](docs/Docker基础架构设计.md)、[版本清单](docs/版本清单.md)、[中国小企业会计准则 App 设计](docs/中国小企业会计准则App设计.md)、[私有企业初始化方案](docs/私有企业初始化方案.md)、[架构说明](docs/架构说明.md)、[扩展接口](docs/扩展接口.md)、[升级指南](docs/升级指南.md) 和 [安全与数据边界](docs/安全与数据边界.md)。

## 上游与参考

- [Frappe Framework](https://github.com/frappe/frappe)
- [ERPNext](https://github.com/frappe/erpnext)
- [Frappe CRM](https://github.com/frappe/crm)
- [Frappe HRMS](https://github.com/frappe/hrms)
- [Frappe Docker](https://github.com/frappe/frappe_docker)
- [lvxj11/docker](https://github.com/lvxj11/docker/tree/master/erpnext16)：参考其 all-in-one 与 Supervisor 思路；本仓库不继承其固定密码、预装业务站点或非官方 App。

本仓库自身的编排代码采用 MIT License；随镜像分发的上游软件分别遵循各自许可证。
