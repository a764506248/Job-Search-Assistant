# PostgreSQL 迁移阶段

当前分支已完成 PostgreSQL 连接兼容层、核心 Repository 初始化验证和 SQLite 一次性迁移脚本；线上仍应在发布新镜像前保持 SQLite，避免半切换。

## 本地启动

```bash
export POSTGRES_PASSWORD='请使用随机强密码'
docker compose -f docker-compose.postgres.yml up -d postgres
docker compose -f docker-compose.postgres.yml ps
```

数据库只暴露在 Compose 内网，不映射宿主机端口，也不要在云防火墙开放 5432。

## 迁移顺序

1. 统一数据库连接和事务接口；
2. 逐个迁移用户、会话、简历、职位、规则、投递和自动化 Repository；
3. 编写 SQLite 到 PostgreSQL 的一次性迁移脚本；
4. 用 SQLite 副本做迁移演练并校验记录数；
5. 备份线上数据后切换 `JSA_DATABASE_URL`；
6. 保留原 SQLite 文件用于回滚。

在新镜像通过本地/预发布验证前，不应设置 `JSA_DATABASE_URL` 或删除现有 SQLite 文件。

## 服务器切换

服务器只需要在项目目录准备 `.env`（不要提交 Git），例如：

```dotenv
POSTGRES_PASSWORD=随机强密码
JSA_DATABASE_URL=postgresql://jsa:URL编码后的密码@postgres:5432/job_search_assistant
JSA_JWT_SECRET=随机生成的长随机字符串
JSA_IMAGE_TAG=v0.3.2
```

先备份 `deploy-data`，再使用迁移脚本把 SQLite 副本导入 PostgreSQL；确认表记录数后执行：

```bash
docker compose -f docker-compose.server.yml pull
docker compose -f docker-compose.server.yml up -d postgres
docker compose -f docker-compose.server.yml up -d local-service automation-runner web
docker compose -f docker-compose.server.yml ps
```

回滚时停止新编排，移除 `JSA_DATABASE_URL`，恢复旧镜像和 SQLite 文件即可。PostgreSQL 数据目录不要删除，便于再次切换或排查。
