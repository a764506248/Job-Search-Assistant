# Local Service

本地服务保存用户资料，并向浏览器扩展提供规则判断、本地资料匹配、材料生成和任务记录 API。

Docker 一键启动（推荐，在仓库根目录执行）：

```bash
docker compose up -d --build
```

这会同时启动：

- Web 管理端：`127.0.0.1:8765`；
- FastAPI：只在 Compose 内网的 `local-service:8765` 提供服务，由 Web 入口转发 `/v1`；
- SQLite 数据文件：宿主机 `apps/local-service/data/jobs.sqlite3`，挂载到容器 `/data/jobs.sqlite3`。

开发模式：

```bash
# apps/local-service 目录
uv sync --dev
uv run uvicorn job_search_assistant.main:app --reload --port 8767
```

- 管理后台：<http://127.0.0.1:8765>（需要从仓库根目录运行 Compose）
- API 文档：<http://127.0.0.1:8765/docs>

FastAPI 已不再托管前端静态文件。单独调试 API 时可直接访问 <http://127.0.0.1:8767/docs>。
