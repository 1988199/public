# Twenty CRM 单容器

基于 Twenty 官方容器构建，将 Twenty Server、Worker、PostgreSQL、Redis 和 Supervisor 整合到一个 Docker 容器中。

镜像：`ghcr.io/1988199/twenty-single`（`linux/amd64`）。自动发布 `latest`、版本号和 `twenty-版本号` 标签；当前版本见 [`VERSION`](VERSION)。

## 启动

```bash
cp .env.example .env
docker compose up -d
docker compose logs -f twenty
```

默认访问 `http://localhost:3000`，在 Twenty 页面创建首个账号。Compose 将数据库、Redis、附件和实例密钥统一保存在 Docker volume `twenty-data` 中。

## 自动更新与发布

GitHub Actions 每天北京时间 **10:43** 检查 Twenty 官方稳定版，也可手动运行。新版本出现时，先确认对应的官方 Docker 标签并构建候选镜像；通过 HTTP、服务进程、数据持久化及 Worker 恢复测试后，才发布版本号、`twenty-版本号` 和 `latest` 标签，并更新 `VERSION`。

若版本未变化且所有目标标签均已发布，定时任务跳过构建。工作流文件：[`.github/workflows/twenty-auto-build.yml`](../.github/workflows/twenty-auto-build.yml)。

## 数据

`/data` 保存 PostgreSQL、Redis、附件和自动生成的实例密钥。容器更新时复用原数据卷；备份和恢复时应完整保留该目录内容。

上游项目：[Twenty](https://github.com/twentyhq/twenty)。Twenty 及容器内组件分别遵循各自许可证。
