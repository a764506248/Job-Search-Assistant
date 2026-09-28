# Local Service

本地服务保存用户资料和知识库，并向浏览器扩展提供规则判断、RAG、材料生成和任务记录 API。

开发启动：

```bash
# 仓库根目录
docker compose up -d --build embedding

# apps/local-service 目录
uv sync --dev
uv run uvicorn job_search_assistant.main:app --reload --port 8765
```

- 管理后台：<http://127.0.0.1:8765>
- API 文档：<http://127.0.0.1:8765/docs>
- Embedding 健康检查：<http://127.0.0.1:8766/health>

可通过 `JSA_EMBEDDING_URL` 和 `JSA_EMBEDDING_MODEL` 覆盖默认服务地址与模型。
