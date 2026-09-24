# ERPNext V16 中文单容器发行版

这是一个面向简体中文环境的 ERPNext V16 Docker 发行版。镜像构建时直接获取 Frappe、ERPNext、Frappe HRMS 和 Frappe CRM 官方 GitHub 源码；仓库保存基础设施、版本清单、中文技术文档，以及独立的中国小企业会计准则与中文补充翻译 App，不保存任何企业业务数据。

- 镜像：`ghcr.io/1988199/erpnext`
- 当前版本：Frappe `v16.35.0`、ERPNext `v16.35.0`、HRMS `v16.20.0`、CRM `v1.84.0`。
- 访问入口：默认 `http://localhost:8080`；自定义端口通过 `HTTP_PORT` 设置。
- 数据卷：数据库、Redis、站点文件和日志分开持久化。

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

### 自动检查、重建与发布

此功能已实现在仓库根目录的 `.github/workflows/erpnext-auto-build.yml`，不是仅供规划的后续事项。

- **检查时间：**每天 UTC 02:43（北京时间 10:43）自动运行；也支持手动触发。运行代码或构建配置变更时同样会触发。
- **检查来源：**读取 Frappe、ERPNext、HRMS、CRM 官方 GitHub Release，过滤预发布版本，并按各自版本线选取最新稳定版；同时核对版本标签对应的源码提交。
- **版本未变：**若官方版本没有前进且 GHCR 中已有 `latest`，定时任务跳过构建；手动运行或代码变更仍会重新验证。
- **发现新版本：**更新候选版本清单后，从官方源码构建镜像，并依次测试配置、空站点创建、未设置 `SITE_NAME` 的启动、`localhost` 页面资源，以及上一版空站点备份迁移。任一检查失败时，不发布 `latest`，也不把候选版本记录为已验证版本。
- **全部通过后：**发布版本标签（例如 `V16.35.0` 和 `16.35.0`）及 `latest`，然后提交已验证的上游版本锁定信息。镜像名为 `ghcr.io/1988199/erpnext`；精确复现建议固定实际发布摘要（digest）。
- **权限要求：**工作流使用 `GITHUB_TOKEN`，需要 `contents: write` 与 `packages: write`；密钥不写入仓库。GitHub 不会因工作流声明 `packages: write` 就自动授予它访问另一个仓库关联的既有 GHCR 包。

**当前发布状态：**自动检查和构建测试逻辑已经存在；但目前 `ghcr.io/1988199/erpnext` 是私有 GHCR 包，并关联私有仓库 `1988199/myerp`。`1988199/public` 的 Actions 尚未获得该包的访问权，因此当前运行在拉取上一版迁移基线时失败，镜像发布步骤尚未通过验证。需要在 GHCR 包设置中单独授权 `1988199/public` 的 Actions 访问（可以保持包为私有），之后才能完成端到端的自动迁移测试和发布验证。此权限尚未擅自修改。

如需试构建，先复制环境变量示例并更换密码：

```powershell
Copy-Item .env.example .env
docker compose build
docker compose up -d
```

如需直接运行已发布镜像，可先拉取版本标签，再使用本项目 Compose 模板：

```powershell
docker pull ghcr.io/1988199/erpnext:V16.35.0
Copy-Item .env.example .env
docker compose up -d
```

首次启动需要一段时间完成空站点安装，可通过 `docker compose logs -f erpnext` 查看进度。默认测试管理员为 `Administrator`，初始密码读取 `ADMIN_PASSWORD`（示例值 `Pass1234`）；数据库 root 密码读取 `DB_ROOT_PASSWORD`。在 `.env` 中配置强密码后再启动。已有数据卷不会因为修改 `.env` 而自动重置站点管理员密码。

首次启动会创建一个没有业务数据的站点并安装 ERPNext、HRMS、CRM 和中国小企业会计准则 App。新建国家为“中国”的公司时，可直接选择“中国小企业会计准则”。默认入口为 `http://localhost:8080`（若设置 `HTTP_PORT=8090`，则为 `http://localhost:8090`）。`SITE_NAME` 是容器内部站点名；既有卷中的 `erp.localhost` 无需改名，Nginx 会将浏览器的 `localhost` 请求转给它。

当前测试镜像在未提供环境变量时，数据库 root 密码和首次建站的 ERPNext `Administrator` 密码均默认为 `Pass1234`。可分别通过 `DB_ROOT_PASSWORD` 和 `ADMIN_PASSWORD` 覆盖。管理员默认密码只在创建新站点时写入，不会重置已有数据卷内的站点密码。该测试例外不得用于正式环境或对外联网部署。

## 重要限制

单容器是明确的产品约束，适合单机部署、内部测试和 PoC，但数据库、缓存与应用无法独立扩缩容或滚动升级。正式上线前必须完成备份恢复、容量、并发、崩溃恢复和安全测试。官方 Frappe Docker 的生产推荐仍是多服务拓扑。

升级前先按[升级指南](docs/升级指南.md)备份数据库、站点文件及当前版本信息，再拉取目标版本并按计划升级。不要删除 Docker 数据卷；回退镜像不一定兼容已经迁移过的数据库。Compose 服务只映射主机端口到容器，容器内部站点目录名（默认 `erp.localhost`）不需要与浏览器地址相同。

详细说明见 [Docker 基础架构设计](docs/Docker基础架构设计.md)、[版本清单](docs/版本清单.md)、[中国小企业会计准则 App 设计](docs/中国小企业会计准则App设计.md)、[私有企业初始化方案](docs/私有企业初始化方案.md)、[架构说明](docs/架构说明.md)、[扩展接口](docs/扩展接口.md)、[升级指南](docs/升级指南.md) 和 [安全与数据边界](docs/安全与数据边界.md)。

## 上游与参考

- [Frappe Framework](https://github.com/frappe/frappe)
- [ERPNext](https://github.com/frappe/erpnext)
- [Frappe CRM](https://github.com/frappe/crm)
- [Frappe HRMS](https://github.com/frappe/hrms)
- [Frappe Docker](https://github.com/frappe/frappe_docker)
- [lvxj11/docker](https://github.com/lvxj11/docker/tree/master/erpnext16)：参考其 all-in-one 与 Supervisor 思路；本仓库不继承其固定密码、预装业务站点或非官方 App。

本仓库自身的编排代码采用 MIT License；随镜像分发的上游软件分别遵循各自许可证。
