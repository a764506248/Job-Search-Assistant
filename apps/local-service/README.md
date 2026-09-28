# Local Service

本地服务保存用户资料和知识库，并向浏览器扩展提供规则判断、RAG、材料生成和任务记录 API。

Docker 一键启动（推荐，在仓库根目录执行）：

```bash
docker compose up -d --build
```

这会同时启动：

- 本地管理服务：`127.0.0.1:8765`；
- Embedding 服务：`127.0.0.1:8766`；
- SQLite 数据文件：宿主机 `apps/local-service/data/jobs.sqlite3`，挂载到容器 `/data/jobs.sqlite3`。

开发模式：

```bash
# 仓库根目录只启动 Embedding
docker compose up -d --build embedding

# apps/local-service 目录
uv sync --dev
uv run uvicorn job_search_assistant.main:app --reload --port 8765
```

- 管理后台：<http://127.0.0.1:8765>
- API 文档：<http://127.0.0.1:8765/docs>
- Embedding 健康检查：<http://127.0.0.1:8766/health>

可通过 `JSA_EMBEDDING_URL` 和 `JSA_EMBEDDING_MODEL` 覆盖默认服务地址与模型。
