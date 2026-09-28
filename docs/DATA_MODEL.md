# 数据模型与接口约定

## 1. 设计原则

- 结构化数据与向量索引分离。
- 生成内容必须可追溯到事实来源。
- 原始文件、解析结果和用户确认结果分开保存。
- 所有会影响投递的判断都保存版本和证据。
- Token、Cookie 和 API Key 不进入业务数据库。

示例使用 JSON 表达，正式实现以数据库迁移和 OpenAPI Schema 为准。

## 2. 核心实体关系

```mermaid
erDiagram
    USER_PROFILE ||--o{ CAREER_TARGET : owns
    USER_PROFILE ||--o{ EXPERIENCE : owns
    USER_PROFILE ||--o{ PROJECT : owns
    USER_PROFILE ||--o{ RESUME : owns
    PROJECT ||--o{ PROJECT_FACT : contains
    PROJECT ||--o{ TAG_ASSIGNMENT : tagged
    PROJECT_FACT ||--o{ KNOWLEDGE_CHUNK : indexed_as
    CAREER_TARGET ||--o{ RISK_RULE : configures
    CAREER_TARGET }o--|| RESUME : defaults_to
    JOB_POSTING ||--o{ JOB_ANALYSIS : analyzed_as
    JOB_ANALYSIS ||--o{ MATCH_EVIDENCE : contains
    JOB_ANALYSIS ||--o{ GENERATED_ARTIFACT : produces
    RESUME ||--o{ GENERATED_ARTIFACT : based_on
    DELIVERY_PLAN ||--o{ DELIVERY_ITEM : contains
    DELIVERY_ITEM }o--|| JOB_POSTING : targets
    DELIVERY_ITEM }o--o| GENERATED_ARTIFACT : uses
```

## 3. 用户档案

```json
{
  "id": "profile_01",
  "display_name": "用户名称",
  "summary": "个人简介",
  "years_of_experience": 3,
  "locations": ["上海", "杭州"],
  "skills": ["Python", "RAG"],
  "privacy": {
    "send_name_to_llm": false,
    "send_contact_to_llm": false
  },
  "created_at": "2026-09-28T00:00:00Z",
  "updated_at": "2026-09-28T00:00:00Z"
}
```

联系方式应保存在独立表，并为每个字段配置使用范围。

## 4. 求职目标

```json
{
  "id": "target_ai_app",
  "profile_id": "profile_01",
  "name": "AI 应用开发工程师",
  "keywords": ["RAG", "Agent", "Python"],
  "excluded_keywords": [],
  "cities": ["上海", "杭州", "远程"],
  "salary": {
    "minimum": 20,
    "maximum": 35,
    "unit": "K_MONTH"
  },
  "industries": [],
  "minimum_suitability_score": 75,
  "minimum_customization_confidence": 80,
  "default_resume_id": "resume_default",
  "default_greeting_id": "greeting_default",
  "resume_template_id": "template_standard",
  "enabled": true
}
```

## 5. 项目与项目事实

### 5.1 项目

```json
{
  "id": "project_003",
  "profile_id": "profile_01",
  "name": "企业知识库问答系统",
  "repository": {
    "provider": "github",
    "owner": "example",
    "name": "knowledge-base",
    "url": "https://github.com/example/knowledge-base",
    "default_branch": "main",
    "visibility": "public",
    "last_synced_commit": "commit_sha"
  },
  "role": "独立开发者",
  "start_date": "2025-01",
  "end_date": "2025-04",
  "summary": "面向内部文档的 RAG 问答系统",
  "status": "confirmed",
  "allowed_in_resume": true,
  "allowed_in_greeting": true
}
```

### 5.2 项目事实

```json
{
  "id": "fact_031",
  "project_id": "project_003",
  "type": "achievement",
  "statement": "实现关键词与向量混合检索链路",
  "source": {
    "type": "repository_file",
    "path": "README.md",
    "commit": "commit_sha",
    "line_start": 20,
    "line_end": 24
  },
  "verification_status": "user_confirmed",
  "confidence": 1.0,
  "allowed_in_resume": true,
  "allowed_in_greeting": true,
  "sensitivity": "normal"
}
```

事实状态：

- `machine_extracted`：机器提取，不能直接用于最终材料；
- `user_confirmed`：用户确认，可以使用；
- `user_rejected`：用户否认，禁止使用；
- `outdated`：已过期，默认不使用。

## 6. 标签

```json
{
  "id": "tag_rag",
  "category": "technology",
  "name": "RAG",
  "aliases": ["检索增强生成"],
  "parent_id": "tag_llm_application"
}
```

标签类别：

- `technology`
- `business_domain`
- `capability`
- `role`
- `outcome`

项目标签关联需要保存来源：用户添加、仓库检测或模型推荐。

## 7. 知识切片

```json
{
  "id": "chunk_101",
  "profile_id": "profile_01",
  "entity_type": "project_fact",
  "entity_id": "fact_031",
  "text": "实现关键词与向量混合检索链路",
  "tags": ["RAG", "向量检索", "后端"],
  "usage_scopes": ["resume", "greeting", "matching"],
  "verification_status": "user_confirmed",
  "embedding_model": "configured-model",
  "embedding_version": 1,
  "content_hash": "sha256",
  "created_at": "2026-09-28T00:00:00Z"
}
```

数据库只保存向量引用或向量本身；索引必须可以根据结构化数据重新生成。

## 8. 简历

```json
{
  "id": "resume_default",
  "profile_id": "profile_01",
  "name": "默认中文简历",
  "kind": "default",
  "source_file_id": "file_001",
  "format": "docx",
  "parsed_content_version": 2,
  "status": "approved",
  "created_at": "2026-09-28T00:00:00Z"
}
```

定制简历作为生成物保存，不覆盖默认简历。

## 9. 默认问候语

```json
{
  "id": "greeting_default",
  "profile_id": "profile_01",
  "name": "默认问候语",
  "content": "您好，我对这个岗位很感兴趣，希望可以进一步沟通。",
  "status": "active"
}
```

## 10. 风险规则

```json
{
  "id": "rule_education_elite",
  "career_target_id": "target_ai_app",
  "name": "名校学历偏好",
  "type": "semantic",
  "patterns": ["985", "211", "双一流", "第一学历"],
  "instruction": "仅在文本将学校背景作为招聘条件时命中，忽略否定表达和团队介绍。",
  "action": "use_default_materials",
  "severity": "high",
  "enabled": true
}
```

动作枚举：

- `notify`
- `reduce_score`
- `use_default_materials`
- `block_delivery`

## 11. 职位快照

```json
{
  "id": "job_boss_123",
  "platform": "boss",
  "platform_job_id": "encrypted-job-id",
  "url": "https://www.zhipin.com/job_detail/example.html",
  "title": "AI 应用开发工程师",
  "company_name": "示例公司",
  "location": "上海",
  "salary_text": "20-35K",
  "raw_description": "原始 JD",
  "raw_payload_hash": "sha256",
  "captured_at": "2026-09-28T00:00:00Z"
}
```

职位更新后创建新快照版本，不覆盖历史投递使用的内容。

## 12. JD 解析结果

```json
{
  "id": "analysis_001",
  "job_posting_id": "job_boss_123",
  "career_target_id": "target_ai_app",
  "parser_version": "jd-parser-1",
  "requirements": [
    {
      "id": "req_01",
      "category": "education",
      "level": "preferred",
      "normalized_value": "985_or_211",
      "evidence": {
        "text": "985、211院校优先",
        "start": 120,
        "end": 131
      }
    }
  ],
  "suitability_score": 42,
  "customization_confidence": 81,
  "material_strategy": "default",
  "strategy_reason": "命中名校学历偏好风险规则",
  "model": "user-configured-model",
  "prompt_version": "match-v1"
}
```

## 13. 匹配证据

```json
{
  "id": "evidence_01",
  "analysis_id": "analysis_001",
  "requirement_id": "req_rag",
  "project_fact_id": "fact_031",
  "retrieval": {
    "keyword_score": 0.73,
    "vector_score": 0.88,
    "rerank_score": 0.91
  },
  "conclusion": "用户存在与岗位相关的混合检索实现经验"
}
```

## 14. 生成材料

```json
{
  "id": "artifact_001",
  "analysis_id": "analysis_001",
  "type": "resume_docx",
  "strategy": "custom",
  "status": "ready",
  "template_id": "template_standard",
  "file_id": "file_generated_01",
  "model": "user-configured-model",
  "prompt_version": "resume-v1",
  "citations": [
    {
      "output_block_id": "resume_project_bullet_1",
      "fact_ids": ["fact_031"]
    }
  ]
}
```

材料状态：

- `generating`
- `ready`
- `rejected`
- `failed`
- `fallback_default`

## 15. 投递计划与投递项

```json
{
  "id": "plan_001",
  "career_target_id": "target_ai_app",
  "status": "draft",
  "created_at": "2026-09-28T00:00:00Z",
  "started_at": null,
  "items": [
    {
      "id": "delivery_001",
      "job_posting_id": "job_boss_123",
      "analysis_id": "analysis_001",
      "resume_strategy": "default",
      "resume_id": "resume_default",
      "greeting_strategy": "default",
      "greeting_id": "greeting_default",
      "status": "ready"
    }
  ]
}
```

投递状态建议：

- `draft`
- `ready`
- `running`
- `delivering`
- `delivered`
- `greeting_sent`
- `failed`
- `blocked`
- `paused_risk`

## 16. 本地 API 草案

### 16.1 配对与健康检查

```text
GET  /v1/health
POST /v1/pairing/start
POST /v1/pairing/complete
```

### 16.2 用户和求职目标

```text
GET    /v1/profile
PUT    /v1/profile
GET    /v1/career-targets
POST   /v1/career-targets
PUT    /v1/career-targets/{id}
DELETE /v1/career-targets/{id}
```

### 16.3 项目库

```text
POST /v1/projects/import/github
GET  /v1/projects
GET  /v1/projects/{id}
POST /v1/projects/{id}/sync
POST /v1/projects/{id}/facts/{factId}/confirm
POST /v1/projects/{id}/facts/{factId}/reject
PUT  /v1/projects/{id}/tags
```

### 16.4 简历与问候语

```text
POST /v1/resumes/import
GET  /v1/resumes
POST /v1/resumes/{id}/set-default
GET  /v1/greetings
POST /v1/greetings
PUT  /v1/greetings/{id}
```

### 16.5 职位分析

```text
POST /v1/jobs/capture
POST /v1/jobs/{id}/analyze
GET  /v1/jobs/{id}/analysis
POST /v1/jobs/analyze-batch
GET  /v1/tasks/{taskId}/events
POST /v1/jd/analyze
POST /v1/jobs/evaluate
```

`/v1/jd/analyze` 只负责识别要求和风险信号；`/v1/jobs/evaluate` 再根据用户配置的规则动作决定使用定制材料、默认材料或禁止投递，避免把单个用户的偏好写死在解析器中。

### 16.6 材料生成

```text
POST /v1/analyses/{id}/artifacts
GET  /v1/artifacts/{id}
POST /v1/artifacts/{id}/regenerate
```

### 16.7 投递计划

```text
POST /v1/delivery-plans
GET  /v1/delivery-plans/{id}
POST /v1/delivery-plans/{id}/start
POST /v1/delivery-plans/{id}/pause
POST /v1/delivery-plans/{id}/resume
POST /v1/delivery-plans/{id}/stop
POST /v1/delivery-items/{id}/result
POST /v1/delivery-plans/{id}/pause-risk
```

本地服务只生成计划和记录结果，不能直接持有 Boss 登录凭据。实际投递由扩展在 Boss 页面上下文中执行。

## 17. 标准错误结构

```json
{
  "error": {
    "code": "LLM_RATE_LIMITED",
    "message": "模型请求频率受限，已回退到默认材料",
    "retryable": true,
    "fallback_applied": "default_materials",
    "request_id": "request_001"
  }
}
```

错误码至少覆盖：

- 本地服务和配对错误；
- 文件解析错误；
- GitHub 同步错误；
- RAG 和 Embedding 错误；
- 模型超时、限流和结构化输出错误；
- Boss 页面适配错误；
- 投递限额和风控错误。

## 18. 数据保留与删除

- 用户可单独删除项目、简历、职位和投递记录。
- 删除项目时同步删除其向量切片。
- 删除原始文件后，不得保留可还原敏感内容的缓存。
- 审计日志只保留脱敏摘要。
- 提供“删除全部本地数据”功能。
