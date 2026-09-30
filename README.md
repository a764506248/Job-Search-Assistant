# Job-Search-Assistant

面向 Boss 直聘的智能求职辅助产品。通过浏览器扩展获取职位 JD，由本地知识库检索用户的真实项目与简历资料，再结合云端大模型生成匹配分析、定制简历和个性化问候语。

## 许可证

本项目以 [PolyForm Noncommercial License 1.0.0](LICENSE) 提供源码：允许个人学习、研究、实验、修改和其他非商业用途，也可在保留许可证的前提下分发；**不允许商业使用**。

由于包含非商业限制，本项目属于“源码可用（source-available）”，不属于 OSI 定义的开源软件。第三方依赖仍分别适用其自身许可证。

当前阶段：MVP 基础开发。已建立浏览器扩展、本地服务、材料策略决策和 Boss JD 快照采集链路。

## 产品原则

- 用户资料与知识库保存在本机。
- 云端模型只接收完成当前任务所需的最小上下文。
- 所有简历内容必须能够追溯到用户确认过的真实资料。
- 低匹配、风险识别失败或生成失败时，回退到默认简历和默认问候语。
- 用户启动任务后，系统按已保存的策略自动投递并发送问候语。

## 设计文档

- [安装、前置依赖与首次启动](docs/SETUP.md)
- [产品需求文档](docs/PRD.md)
- [系统架构与流程](docs/ARCHITECTURE.md)
- [数据模型与接口约定](docs/DATA_MODEL.md)

## 自动投递 Skill

项目内已经包含与当前本地 API 架构配套的
[`boss-zhipin-assistant`](skills/boss-zhipin-assistant/SKILL.md) Skill。它负责流程编排，Kimi
浏览器扩展只负责读取页面、点击和安全发送；个人档案、匹配规则、RAG、职位快照、问候语和投递记录均由本地服务管理。

使用自动投递前，请先安装
[Kimi Browser Extension](https://www.kimi.com/products/kimi-browser-extension)，再按照
[首次启动文档](docs/SETUP.md#5-skill-与-kimi-自动投递)安装项目内 Skill。

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

首次使用前请先阅读 [安装、前置依赖与首次启动](docs/SETUP.md)。特别注意：首次启动需要联网下载 Embedding 模型；Docker 中访问宿主机模型服务不能使用 `127.0.0.1`；浏览器扩展必须加载构建产物 `.output/chrome-mv3`，不能直接加载源码目录。

```bash
docker compose up -d --build
```

启动后打开 <http://127.0.0.1:8765>。Compose 会同时启动基于 Vue 3 + Ant Design Vue 的独立 Web 前端、FastAPI 本地服务与 Embedding 服务。Web 容器通过同源 `/v1` 反向代理访问 FastAPI，因此扩展、Skill 和已有接口地址仍保持 `http://127.0.0.1:8765` 不变。SQLite 文件继续通过 `apps/local-service/data:/data` 挂载到服务容器，现有数据无需迁移。

当前可以管理个人档案、项目、简历资料、匹配规则、模型配置和职位快照；所有修改都会持久化到本地 SQLite。“简历库”支持导入 PDF、DOCX、TXT 和 Markdown 文件，并将识别结果分别写入个人档案、项目库和简历库，随后自动重建向量索引。“简历模板”提供投递版式选择、网页预览和 PDF 示例，“向量知识库”可使用 768 维的 `jinaai/jina-embeddings-v2-base-zh` 重建本地索引并测试语义检索。

Embedding 服务运行在 Docker 中，仅监听 `127.0.0.1:8766`。模型文件保存在 Docker 持久化卷，首次启动需要下载，后续启动会直接复用。原始资料、文本分片和向量都保存在本机。

> 当前安全状态：模型 API Key 保存在本地 SQLite 中，接口列表不会返回明文，但尚未接入系统密钥链；`JSA_LOCAL_TOKEN` 也尚未形成完整的服务端认证闭环。请勿将 `apps/local-service/data` 提交到 Git、发送给他人，或把 `8765` 暴露到局域网和公网。
