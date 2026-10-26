# 服务器部署

服务器部署使用 GitHub Actions 构建的 GHCR 镜像，不在 2 核/2 GB 机器上执行前端或 Python 依赖构建。

## 正式环境地址

正式站点为 [https://jsazhushou.cn/](https://jsazhushou.cn/)，后台登录 `/login`、扩展安装与配对 `/setup`、手机投递 `/codex-delivery`。浏览器扩展服务地址和 Agent Base URL 均填写 `https://jsazhushou.cn`，健康检查为 `https://jsazhushou.cn/v1/health`。本地安装继续使用 `http://127.0.0.1:8765`，不做全局替换。

服务器使用项目部署目录下的两份 Compose 文件，业务数据保留在该目录的 `deploy-data/`，证书保留在 `certs/`。实际目录、登录方式与凭据由内部运维记录维护。

## 接口文档的环境隔离

`JSA_ENV` 只接受 `local` 或 `production`，默认 `production`，拼写错误时服务启动失败。服务器 Compose 固定设置 `production`，关闭 `/docs`、`/redoc`、`/openapi.json` 及 `/docs/oauth2-redirect`；HTTPS Nginx 额外拦截文档与子路径并返回 404。环境不通过域名、请求 Host 或容器内的 localhost 判断。

本地 Compose 显式设置 `local`，开启 Swagger、ReDoc 和 OpenAPI；直接运行开发服务时设置 `JSA_ENV=local`。文档开关不改变业务 API、扩展 WebSocket、Agent 鉴权或健康检查。线上排障使用内部工具，不临时把生产环境切成 `local`。

## 发布镜像

部署工作流响应 `main` 分支和 `v*` 标签。功能分支不会自动发布；从功能分支发布时，先提交并推送，再创建版本标签：

```bash
git push origin HEAD
# 将 vX.Y.Z 替换为本次尚未发布的固定版本号。
git tag -a vX.Y.Z -m "production release" HEAD
git push origin vX.Y.Z
```

等待 GitHub Actions 完成后，服务器显式使用该版本标签。不要依赖 `latest`，这样可以避免服务器无意间拉到其他版本。

## 服务器更新

在服务器项目目录执行：

```bash
cd /path/to/Job-Search-Assistant
# 以下为仅启用 HTTP 的自建实例示例；正式域名必须使用后文两份 Compose 的 HTTPS 更新命令。
JSA_IMAGE_TAG=vX.Y.Z docker compose -f docker-compose.server.yml pull
JSA_IMAGE_TAG=vX.Y.Z docker compose -f docker-compose.server.yml up -d
docker compose -f docker-compose.server.yml ps
curl http://127.0.0.1/v1/health
```

编排会启动 `web`、`local-service` 和同镜像的 `automation-runner`。Web 对外监听 80 端口；Local Service 只在 Compose 内网可见。业务数据使用 `./deploy-data:/data`，更新容器不会切换数据库目录。

## jsazhushou.cn 启用 HTTPS

基础 `docker-compose.server.yml` 继续提供 HTTP，不要求域名或证书。`jsazhushou.cn` 实例额外使用 `docker-compose.server.https.yml`，在同一个 Web 容器中增加 HTTPS 443。启用后原 HTTP 地址仍可访问，当前配置不强制跳转 HTTPS。

启用前确认域名解析指向该服务器，服务器防火墙允许 TCP 443，并在项目目录准备以下文件：

```text
deploy/server-nginx.conf
certs/jsazhushou.cn_bundle.crt
certs/jsazhushou.cn.key
```

证书使用 Nginx 格式的完整证书链和匹配的私钥。`certs/` 已被 Git 忽略；部署用私钥保存在服务器，不写入仓库或镜像，目录权限设为 `700`、私钥权限设为 `600`。确认 `.env` 中的 `JSA_IMAGE_TAG` 为已验证的固定版本，后续命令会沿用该版本。

首次启用时先检查合并后的编排与 Nginx 配置，再重建 Web 容器：

```bash
docker compose -f docker-compose.server.yml -f docker-compose.server.https.yml config --quiet
docker compose -f docker-compose.server.yml -f docker-compose.server.https.yml run --rm --no-deps web nginx -t
docker compose -f docker-compose.server.yml -f docker-compose.server.https.yml up -d --no-deps web
docker compose -f docker-compose.server.yml -f docker-compose.server.https.yml ps
curl --fail https://jsazhushou.cn/v1/health
curl --fail http://jsazhushou.cn/v1/health
```

HTTPS 实例后续更新镜像时，每次都带上两份 Compose 文件，避免更新时移除 443 与证书挂载：

```bash
docker compose -f docker-compose.server.yml -f docker-compose.server.https.yml pull
docker compose -f docker-compose.server.yml -f docker-compose.server.https.yml up -d
docker compose -f docker-compose.server.yml -f docker-compose.server.https.yml exec -T web nginx -t
curl --fail https://jsazhushou.cn/v1/health
```

HTTPS 的 Nginx 配置通过服务器文件覆盖镜像默认配置。若发布版本修改了 `apps/web/nginx.conf` 的 API、WebSocket 或其他路由，也需要把对应改动同步到 `deploy/server-nginx.conf`。

正式发布前备份数据库和当前部署配置，记录旧镜像标签；同步本次版本的 Compose 与 Nginx 配置，保持 `deploy-data/`、`.env` 和 `certs/` 不变。在 `.env` 中将 `JSA_IMAGE_TAG` 更新为本次已构建成功的固定标签，再执行上面的 HTTPS 更新命令。不得执行 `down -v` 或复制开发机数据库覆盖线上数据。

发布后验证：

```bash
curl --fail https://jsazhushou.cn/
curl --fail https://jsazhushou.cn/login
curl --fail https://jsazhushou.cn/v1/health
# 未携带 Key 时必须返回 401，不能泄露用户资料。
curl -s -o /dev/null -w '%{http_code}\n' https://jsazhushou.cn/v1/agent/me
# 以下文档入口及其子路径必须返回 404（不是前端 SPA 的 200）。
curl -s -o /dev/null -w '%{http_code}\n' https://jsazhushou.cn/docs
curl -s -o /dev/null -w '%{http_code}\n' https://jsazhushou.cn/openapi.json
curl -s -o /dev/null -w '%{http_code}\n' https://jsazhushou.cn/redoc
curl -s -o /dev/null -w '%{http_code}\n' https://jsazhushou.cn/docs/oauth2-redirect
```

同时核对健康接口版本、实际容器镜像标签与发布版本一致。浏览器登录后确认现有资料、手机投递计划和扩展连接状态；文档更新或容器启动成功不能单独当作业务验收完成。

续期时将新的证书链和匹配私钥替换到上述 `certs/` 文件，保留文件名和权限，再校验并平滑重新加载。证书使用目录挂载，因此原子替换文件后也能读到新证书：

```bash
docker compose -f docker-compose.server.yml -f docker-compose.server.https.yml exec -T web nginx -t
docker compose -f docker-compose.server.yml -f docker-compose.server.https.yml exec -T web nginx -s reload
curl --fail https://jsazhushou.cn/v1/health
```

校验失败时先修正证书或配置，不执行 reload。若只需撤销 HTTPS、恢复原 HTTP 部署，使用基础编排单独重建 Web 容器；业务数据与其他容器保留：

```bash
docker compose -f docker-compose.server.yml up -d --no-deps --force-recreate web
curl --fail http://jsazhushou.cn/v1/health
```

## 回滚

```bash
JSA_IMAGE_TAG=v0.4.13 docker compose -f docker-compose.server.yml up -d
```

回滚只切换镜像版本，不删除 `deploy-data`。发布前仍应自行备份该目录，并确认服务器防火墙不开放 Portainer 的 9443 端口。

已启用 HTTPS 的实例回滚镜像时也需保留 HTTPS 配置，例如：

```bash
JSA_IMAGE_TAG=v0.4.13 docker compose -f docker-compose.server.yml -f docker-compose.server.https.yml up -d
```
