from typing import Any

TEAL_PROFESSIONAL_ID = "teal-professional"

SAMPLE_RESUME: dict[str, Any] = {
    "name": "林晓舟",
    "headline": "AI Agent 开发工程师 · 全栈工程背景",
    "contact": ["北京", "8 年经验", "138****0000", "lin@example.com"],
    "coreSkills": "LangGraph / RAG / FastAPI / Python / PostgreSQL / MCP / SSE / RTC",
    "strengths": [
        "熟悉 AI 应用落地，能够将模型能力接入具体业务流程。",
        "熟悉 Python、FastAPI、asyncio 与 Pydantic，具备异步接口和流式输出经验。",
        "熟悉 RAG 数据清洗、文档切片、Embedding、混合检索和 Rerank 优化。",
        "具备 Prompt 版本管理、自动化评测和负样本优化经验。",
    ],
    "skillGroups": [
        ["Agent 与编排", "LangGraph、LangChain、MCP、Tool Calling"],
        ["RAG 与推理", "Embedding、HNSW、Rerank、Metadata、Prefix Cache"],
        ["后端与数据", "Python、FastAPI、PostgreSQL、SSE、WebSocket"],
        ["前端与工程", "Vue、TypeScript、Git、监控、熔断与重试"],
    ],
    "projects": [
        {
            "name": "实时语音导购 Agent",
            "role": "核心开发",
            "period": "2025.03 - 2026.07",
            "summary": "围绕到店决策场景，串联 RTC、ASR、RAG、LLM 与 TTS。",
            "bullets": [
                "构建混合检索方案，通过量化与 Metadata 过滤将向量存储空间降低 75%，"
                "检索速度提升 4 倍。",
                "优化检索片段与 System Prompt，将复杂 RAG 场景 TTFT 从 8 秒降低至 2 秒内。",
                "建立提示词版本、评测集和负样本优化闭环，支持问题回放与快速迭代。",
                "完成 RTC、ASR、LLM、TTS 实时链路联调与异常处理。",
            ],
        },
        {
            "name": "智能内容运营系统",
            "role": "核心开发",
            "period": "2025.03 - 2026.07",
            "summary": "使用 LangGraph 构建选题、写作、配图与审核的一体化生产工作流。",
            "bullets": [
                "使用 SubGraph 拆分业务单元，并通过 PostgreSQL Checkpointer 持久化状态。",
                "集成 SSE 流式输出，用户感知 TTFT 降低 60%。",
                "通过并发生成和指数退避重试，整体生成耗时缩减 70%。",
            ],
        },
    ],
    "experience": [
        {
            "role": "前端开发工程师 / AI 应用开发",
            "company": "示例科技有限公司",
            "period": "2021.09 - 2026.07",
            "summary": "负责业务前端与 AI Agent 应用研发。",
            "bullets": [
                "主导多端适配和组件体系建设，持续提升交付效率。",
                "参与语音导购、内容运营和模型评测等 AI Agent 项目。",
            ],
        },
        {
            "role": "前端开发工程师",
            "company": "示例网络科技有限公司",
            "period": "2018.06 - 2021.09",
            "summary": "负责 H5、PC 和国际化业务开发。",
            "bullets": ["完成多语言和性能优化建设，首屏加载速度提升 50%。"],
        },
    ],
    "education": [
        {"school": "示例大学", "degree": "计算机科学与技术 · 本科", "period": "2014 - 2018"}
    ],
}

RESUME_TEMPLATES = [
    {
        "id": TEAL_PROFESSIONAL_ID,
        "name": "经典青色专业版",
        "description": "适合 AI、研发和技术岗位，突出技能、量化成果与项目经历。",
        "accent": "#009c9c",
        "layout": "single-column",
        "status": "available",
    }
]
