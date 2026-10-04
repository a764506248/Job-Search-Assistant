# PostgreSQL 迁移阶段

当前线上业务仍使用 SQLite。本阶段只增加 PostgreSQL 基础设施，不改变现有读写链路，便于随时回滚。

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

在全部 Repository 迁移完成前，不应设置 `JSA_DATABASE_URL` 或删除现有 SQLite 文件。
