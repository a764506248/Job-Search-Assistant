# Job-Search-Assistant

面向 Boss 直聘的智能求职辅助产品。通过浏览器扩展获取职位 JD，由本地知识库检索用户的真实项目与简历资料，再结合云端大模型生成匹配分析、定制简历和个性化问候语。

当前阶段：MVP 基础开发。已建立浏览器扩展、本地服务、材料策略决策和 Boss JD 快照采集链路。

## 产品原则

- 用户资料与知识库保存在本机。
- 云端模型只接收完成当前任务所需的最小上下文。
- 所有简历内容必须能够追溯到用户确认过的真实资料。
- 低匹配、风险识别失败或生成失败时，回退到默认简历和默认问候语。
- 用户启动任务后，系统按已保存的策略自动投递并发送问候语。

## 设计文档

- [产品需求文档](docs/PRD.md)
- [系统架构与流程](docs/ARCHITECTURE.md)
- [数据模型与接口约定](docs/DATA_MODEL.md)

## 当前能力

- WXT Chrome MV3 扩展骨架；
- Boss 职位详情 DOM 采集与变更监听；
- 扩展到本地 FastAPI 服务的消息链路；
- SQLite 职位版本快照；
- 带原文证据位置的 JD 学历与名校背景解析；
- 风险规则和定制/默认/阻止材料策略；
- 可选择的简历模板、网页预览与 A4 PDF 示例；
- Python 测试及扩展类型、生产构建检查。

## 通信链路验证

页面主世界脚本读取 Boss DOM，通过 `CustomEvent` 把结构化职位交给内容脚本；内容脚本校验载荷后，以 HTTP JSON 调用本地 FastAPI，服务最终写入 SQLite。

```bash
npm run test:extension
cd apps/local-service
UV_CACHE_DIR=.cache/uv uv run pytest -q
```

自动化测试覆盖 DOM 字段提取、页面事件载荷校验、HTTP 路径/请求体/本地令牌，以及 FastAPI 写入 SQLite 和重复快照去重。真实 Boss 登录页面仍需安装构建后的扩展进行现场冒烟测试。

## 本地管理后台

```bash
docker compose up -d --build embedding

cd apps/local-service
uv sync --dev
uv run uvicorn job_search_assistant.main:app --port 8765
```

启动后打开 <http://127.0.0.1:8765>。当前可以管理个人档案、项目、简历资料、匹配规则、模型配置和职位快照；所有修改都会持久化到本地 SQLite。“简历库”支持导入 PDF、DOCX、TXT 和 Markdown 文件，并将识别结果分别写入个人档案、项目库和简历库，随后自动重建向量索引。“简历模板”提供投递版式选择、网页预览和 PDF 示例，“向量知识库”可使用 768 维的 `jinaai/jina-embeddings-v2-base-zh` 重建本地索引并测试语义检索。API Key 与 GitHub Token 不会保存在普通资料表中，后续通过系统钥匙串接入。

Embedding 服务运行在 Docker 中，仅监听 `127.0.0.1:8766`。模型文件保存在 Docker 持久化卷，首次启动需要下载，后续启动会直接复用。原始资料、文本分片和向量都保存在本机。
