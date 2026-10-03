# 服务器部署

服务器部署使用 GitHub Actions 构建的 GHCR 镜像，不在 2 核/2 GB 机器上执行前端或 Python 依赖构建。

## 发布镜像

部署工作流响应 `main` 分支和 `v*` 标签。功能分支不会自动发布；从功能分支发布时，先提交并推送，再创建版本标签：

```bash
git push origin codex/automation-controls-v030
git tag -a v0.3.1 -m "automation controls" codex/automation-controls-v030
git push origin v0.3.1
```

等待 GitHub Actions 完成后，服务器显式使用该版本标签。不要依赖 `latest`，这样可以避免服务器无意间拉到其他版本。

## 服务器更新

在服务器项目目录执行：

```bash
cd ~/Job-Search-Assistant
JSA_IMAGE_TAG=v0.3.1 docker compose -f docker-compose.server.yml pull
JSA_IMAGE_TAG=v0.3.1 docker compose -f docker-compose.server.yml up -d
docker compose -f docker-compose.server.yml ps
curl http://127.0.0.1/v1/health
```

编排会启动 `web`、`local-service` 和同镜像的 `automation-runner`。Web 对外监听 80 端口；Local Service 只在 Compose 内网可见。业务数据使用 `./deploy-data:/data`，更新容器不会切换数据库目录。

## 回滚

```bash
JSA_IMAGE_TAG=v0.3.0 docker compose -f docker-compose.server.yml up -d
```

回滚只切换镜像版本，不删除 `deploy-data`。发布前仍应自行备份该目录，并确认服务器防火墙不开放 Portainer 的 9443 端口。
