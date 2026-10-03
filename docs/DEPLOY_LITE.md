# 低配上云部署说明（2核2G 轻量机，年付百元级）

面向腾讯云轻量应用服务器的最小部署路径。**当前不含鉴权，请勿直接暴露敏感数据到公网。**

## 与默认编排的差异

| 项 | 根目录 `docker-compose.yml` | `docker-compose.deploy.yml` |
|---|---|---|
| embedding 容器 | 启动（常驻 0.6–1.2GB） | **不启动** |
| 检索方式 | 语义 + FTS5/BM25 混合 | **仅 FTS5/BM25 关键词** |
| web 端口 | `127.0.0.1:8765`（仅本机） | `0.0.0.0:8080`（外网可访问） |
| 内存限制 | 无 | web 256MB / API 768MB |

关闭 embedding 后仍有完整功能：资料库、JD 分析、规则决策、投递记录、简历导入导出都能用，
只是 RAG 召回退化成关键词匹配（中文按 trigram 切词），语义相关度不如向量。

## 两个编排文件怎么选

| 文件 | 镜像来源 | 适用场景 |
|---|---|---|
| `docker-compose.deploy.yml` | **服务器本地构建**（`build:`） | 没接 CI、想直接跑最新代码 |
| `docker-compose.server.yml` | **GitHub Actions 构建的 ghcr 镜像**（`image:`） | 已接 CI，发布只需 `pull` + `up -d`（实测 9 秒） |

用 ghcr 版本时，发布流程变成纯拉取：

```bash
docker compose -f docker-compose.server.yml pull
docker compose -f docker-compose.server.yml up -d

# 回滚到某个历史版本（用 CI 产出的 sha tag）
JSA_IMAGE_TAG=sha-4a452f1 docker compose -f docker-compose.server.yml up -d
```

## 部署步骤

```bash
# 1. 加 2G swap（低配必做，否则构建/启动时容易 OOM）
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab

# 2. 装 Docker（国内建议走 apt；官方 get.docker.com 脚本拉境外站点易超时）
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2   # Ubuntu 24.04 的 compose v2 包名
sudo usermod -aG docker "$USER"   # 重新登录后生效

# 3. 配置镜像加速（国内机器不配会拉不动基础镜像）
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "registry-mirrors": ["https://mirror.ccs.tencentyun.com"]
}
JSON
sudo systemctl restart docker

# 4. 拉代码（GitHub 在国内服务器常连不上，可从本机 scp 打包代码）
git clone https://github.com/a764506248/Job-Search-Assistant.git
cd Job-Search-Assistant
git checkout deploy/lite-no-embedding

# 5. 起服务（compose 已内置腾讯云 PyPI/npm 源，可用环境变量覆盖）
docker compose -f docker-compose.deploy.yml up -d --build

# 6. 验证
curl http://127.0.0.1:8080/healthz          # 应返回 ok
curl http://127.0.0.1:8080/v1/health        # API 健康
curl http://127.0.0.1:8080/v1/rag/status    # mode 应为 keyword-only
```

国内网络相关：`docker-compose.deploy.yml` 默认把 `PIP_INDEX_URL` 指向
`mirrors.tencentyun.com/pypi/simple`、`NPM_REGISTRY` 指向 `mirrors.tencentyun.com/npm/`。
非腾讯云环境或境外构建时用环境变量覆盖，例如
`JSA_PIP_INDEX_URL=https://pypi.org/simple JSA_NPM_REGISTRY=https://registry.npmjs.org`。

浏览器访问 `http://<公网IP>:8080`。

> 若 8080 打不开，检查轻量控制台「防火墙」是否放行该端口（轻量有独立的防火墙策略，与安全组不同）。

## 数据位置与备份

数据落在仓库目录下的 `deploy-data/`：

```
ls deploy-data
# jobs.sqlite3          ← 全部业务数据
# resume-images/        ← 简历图片
```

备份（SQLite 用 `.backup` 比直接 cp 安全）：

```bash
sqlite3 deploy-data/jobs.sqlite3 ".backup /tmp/bak-$(date +%F).sqlite3"
tar czf jsa-backup-$(date +%F).tar.gz deploy-data
```

## 已知限制（上线前必须处理）

- [ ] **无鉴权**：`/v1/*` 完全裸奔，任何拿到 IP 的人可读写全部简历和投递记录。
      临时方案：nginx 加 basic auth，或只允许自己的 IP 访问防火墙端口。
- [ ] **SQLite 并发**：多用户同时写会锁表，正式给多人用需换 PostgreSQL。
- [ ] **本地文件**：简历图片和生成文件都在容器卷里，迁移机器需整体拷贝。
- [ ] **许可证**：根目录声明为 `PolyForm-Noncommercial-1.0.0`，禁止商用。

## 恢复语义检索

机器升到 4核4G 以上后，把 `docker-compose.deploy.yml` 末尾注释掉的 embedding 块放开，
并把 `local-service` 的 `JSA_EMBEDDING_ENABLED` 改成 `"true"`、加上
`JSA_EMBEDDING_URL: http://embedding:8766`，重新 rebuild 索引即可，不用改代码。
