# Twenty CRM 单容器镜像

把 Twenty Server、Twenty Worker、PostgreSQL 16、Redis 放在一个容器中，由 Supervisor 管理。基于官方 `twentycrm/twenty` 镜像，保留官方前后端；这是社区封装，不是 Twenty 官方生产镜像。

镜像：`ghcr.io/1988199/twenty-single`。支持 `linux/amd64`。

标签：`latest`、`2.41.0`、`twenty-2.41.0`（后续稳定版本以相同规则发布）。`VERSION` 与 Dockerfile 默认版本仅在发布成功后由 Actions 更新。

## 启动

```bash
docker run -d --name twenty \
  --restart unless-stopped \
  --stop-timeout 180 \
  -p 3000:3000 \
  -e SERVER_URL=http://localhost:3000 \
  -v twenty-data:/data \
  ghcr.io/1988199/twenty-single:latest
```

访问 `http://localhost:3000`，按 Twenty 页面创建首个账号。没有内置演示账号或默认管理员密码。部署到服务器时，将 `SERVER_URL` 改成用户实际访问的完整地址；使用 HTTPS 反向代理时填写外部 HTTPS 地址。

或使用本目录的 Compose 模板：

```bash
cp .env.example .env
# 编辑 .env 中的访问地址、端口和版本
docker compose up -d
docker compose logs -f --tail=100
```

首次初始化需要执行数据库迁移，健康检查给予 10 分钟启动宽限期。建议测试起点为 2 核 / 4 GB 内存，实际需求取决于数据量、同步任务和并发；未进行容量压测。

## 数据与密钥

| 容器目录 | 内容 |
| --- | --- |
| `/data/postgres` | PostgreSQL 16 数据库 |
| `/data/redis` | Redis AOF 数据 |
| `/data/twenty` | 本地附件，链接到官方 `.local-storage` 路径 |
| `/data/config` | 自动生成的数据库密码、APP_SECRET、ENCRYPTION_KEY |

首次启动自动生成随机密钥，以权限 `0600` 保存，重启时复用。可在首次启动传入至少 32 字符的 `POSTGRES_PASSWORD`、`APP_SECRET`、`ENCRYPTION_KEY`；后续若传入不同值，容器拒绝启动，避免无意破坏原有加密数据。密钥与数据库必须一起备份。密钥轮换应按 Twenty 官方轮换说明专门操作，本封装不自动轮换。

内部数据库和 Redis 只监听容器内的 `127.0.0.1`，仅发布 HTTP 3000 端口。Supervisor 以 root 管理进程，PostgreSQL、Redis、Twenty 分别以 postgres、redis、node 用户运行。不要添加 `--user`，不要将同一个 `/data` 同时挂到多个运行中的实例。本封装固定使用内置数据库、Redis 和 local 存储；SMTP/OAuth 等可按官方环境变量另行配置。

## 检查与备份

```bash
docker inspect --format '{{.State.Health.Status}}' twenty
docker exec twenty supervisorctl -c /etc/twenty-single/supervisord.conf status
docker logs --tail=200 twenty
```

最简单的一致性备份方式：停止容器后备份整个数据卷，再启动容器。下例是 Linux shell：

```bash
mkdir -p backup
docker stop -t 180 twenty
docker run --rm -v twenty-data:/data:ro -v "$PWD/backup:/backup" \
  alpine:3.23 tar czf /backup/twenty-data.tar.gz -C /data .
docker start twenty
```

备份含客户资料、附件和密钥，应保存在私有位置。恢复时使用空数据卷还原完整 `/data`，并首先使用备份时的镜像版本启动。

## 自动构建与升级

`.github/workflows/twenty-auto-build.yml` 在相关文件推送、手动运行及每日 UTC 02:43（北京时间 10:43）触发。

1. 读取 `twentyhq/twenty` 官方最新稳定 Release，排除预发布和非标准版本。
2. 验证官方 Docker 标签，优先 `vX.Y.Z`，再尝试 `X.Y.Z`。找不到镜像则失败，不猜测、不回退到 upstream latest。
3. 定时检查版本未变且目标版本镜像存在时跳过构建；手动触发可重新构建系统依赖补丁。
4. 构建候选镜像，测试 HTTP、四个进程、容器重建后的数据库/Redis/附件/密钥保留、Worker 自动恢复。
5. 全部通过后将同一镜像推送为版本号、`twenty-版本号`、`latest`，最后更新仓库版本文件。

工作流使用仓库 `GITHUB_TOKEN`，需要 `contents: write` 与 `packages: write`，不需要在代码中保存访问令牌。GHCR 首次创建的软件包可能默认为私有；若匿名拉取失败，应将软件包可见性设为 Public。

自动构建只发布镜像，不自动升级已有容器。生产部署建议固定版本，先备份，再阅读对应版本的官方升级说明；跨版本迁移可能要求逐个小版本升级。健康测试验证空库初始化及同版本重建，不代表所有历史版本数据库都可直接升级。数据库迁移失败时停止应用启动，不带错继续运行。Supervisor 会重启退出的服务；Docker 的 `unhealthy` 状态本身不会触发 `unless-stopped` 重启。

## 官方依据（核对版本 v2.41.0）

- [官方 Dockerfile](https://github.com/twentyhq/twenty/blob/twenty/v2.41.0/packages/twenty-docker/twenty/Dockerfile)：Alpine 基础、生产命令 `node dist/main`、工作目录。
- [官方 Compose](https://github.com/twentyhq/twenty/blob/twenty/v2.41.0/packages/twenty-docker/docker-compose.yml)：PostgreSQL 16、Redis `noeviction`、Worker `yarn worker:prod`、`/healthz`、存储挂载及环境变量。
- [官方 entrypoint](https://github.com/twentyhq/twenty/blob/twenty/v2.41.0/packages/twenty-docker/twenty/entrypoint.sh)：数据库初始化、cache flush、upgrade、cron 注册顺序。本封装相同命令执行失败即退出。
- [官方环境变量示例](https://github.com/twentyhq/twenty/blob/twenty/v2.41.0/packages/twenty-docker/.env.example)：SERVER_URL、ENCRYPTION_KEY、APP_SECRET、STORAGE_TYPE。

仓库只收录通用脚本和模板。`.env`、数据卷、备份、访问令牌与任何公司资料不得提交。上游 Twenty 及镜像内各组件仍按各自许可证分发；请参阅 [Twenty LICENSE](https://github.com/twentyhq/twenty/blob/twenty/v2.41.0/LICENSE)。
