# Local Service

本地服务保存用户资料和知识库，并向浏览器扩展提供规则判断、RAG、材料生成和任务记录 API。

开发启动：

```bash
uv sync --dev
uv run uvicorn job_search_assistant.main:app --reload --port 8765
```
