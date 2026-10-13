# Local Service

本地服务保存用户资料，并向浏览器扩展提供规则判断、本地资料匹配、材料生成和任务记录 API。

数据按账号隔离：所有业务接口都要求登录身份（`Authorization: Bearer <JWT>`，或浏览器扩展携带的配对令牌），并按 `user_id` 过滤读写。未登录访问数据接口统一返回 401；管理员通过 `/v1/admin/users` 管理账号。字段与迁移细节见仓库根目录 `docs/DATA_MODEL.md`。

Docker 一键启动（推荐，在仓库根目录执行）：

```bash
docker compose up -d --build
```

这会同时启动：

- Web 管理端：`127.0.0.1:8765`；
- FastAPI：只在 Compose 内网的 `local-service:8765` 提供服务，由 Web 入口转发 `/v1`；
- SQLite 数据文件：宿主机 `apps/local-service/data/jobs.sqlite3`，挂载到容器 `/data/jobs.sqlite3`。

设置 `JSA_DATABASE_URL` 时会改用 PostgreSQL（兼容层会把 SQLite 方言翻译过去），服务器部署即使用这一模式。

开发模式：

```bash
# apps/local-service 目录
uv sync --dev
uv run uvicorn job_search_assistant.main:app --reload --port 8767
```

测试：

```bash
# apps/local-service 目录
uv run pytest -q
```

`tests/conftest.py` 会在每个测试客户端首次请求前准备一个已登录账号，因此新增用例无需手工拼装令牌。修改任何 `INSERT ... RETURNING` 语句时注意：SQLite 需要消费返回行才能提交事务，`database.py` 的 `SqliteConnection` 已统一处理。

- 管理后台：<http://127.0.0.1:8765>（需要从仓库根目录运行 Compose）
- API 文档：<http://127.0.0.1:8765/docs>

FastAPI 已不再托管前端静态文件。单独调试 API 时可直接访问 <http://127.0.0.1:8767/docs>。
