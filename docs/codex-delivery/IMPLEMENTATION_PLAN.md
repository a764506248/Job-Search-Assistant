# Codex 单岗投递实施计划

## 执行规则

- 分支：`codex/codex-delivery-flow`
- 顺序：完成当前阶段的代码、测试和检查后再进入下一阶段。
- 兼容：不修改旧自动投递协议和数据语义；如必须触及共享入口，只做新增注册。
- 记录：每完成一项，在本文件勾选并补充验证结果。

## Phase 0：需求与架构基线

- [x] 建立独立需求目录。
- [x] 编写 PRD，明确范围、字段、流程和验收标准。
- [x] 编写技术架构，明确表、API、鉴权和状态机。
- [x] 建立分阶段实施计划。

产物：

- `docs/codex-delivery/PRD.md`
- `docs/codex-delivery/TECHNICAL_ARCHITECTURE.md`
- `docs/codex-delivery/IMPLEMENTATION_PLAN.md`

## Phase 1：独立数据层与 Agent Key

- [x] 新建 `codex_delivery` 后端模块，不向旧 repository 塞入运行逻辑。
- [x] 建立 `agent_api_keys`、`codex_delivery_configs`、`codex_delivery_runs`、`codex_delivery_job_steps`。
- [x] 实现 Agent Key 创建、摘要存储、校验、过期和撤销。
- [x] 实现配置 CRUD、默认配置和用户隔离。
- [x] 实现运行/岗位步骤状态、计数和幂等约束。
- [x] 添加 Repository/API 单元测试。

完成条件：SQLite 测试通过；新表不改变旧表结构或写入旧运行数据。

## Phase 2：网页管理 API 与 Agent API

- [x] 新增独立 router 并只在应用入口注册。
- [x] 实现网页登录用户的 Key 管理和配置管理 API。
- [x] 实现 `/v1/agent/me`、context、默认配置和运行创建。
- [x] 实现岗位 check/capture/analyze/result API。
- [x] 实现 pause/finish 和自动停止条件。
- [x] 添加认证、状态转换、幂等和回归测试；现有用户隔离测试继续通过。

完成条件：新 API 测试通过；无效/过期/撤销 Key 被拒绝；旧 API 测试无回归。

## Phase 3：Codex 投递页面

- [x] 新增独立路由和导航项。
- [x] 实现 Agent Key 创建、一次性展示、复制和撤销。
- [x] 实现手机来源页签与全部筛选字段。
- [x] 实现投递计划与安全配置。
- [x] 实现配置保存、默认配置与表单校验。
- [x] 实现运行进度和岗位步骤展示。
- [x] 检查所有新增 `a-*` 组件均在 `main.ts` 注册；页面只使用现有已注册组件。

完成条件：类型检查和生产构建通过；页面可加载并完成一次真实保存/选择/弹窗交互。

## Phase 4：Codex + iPhone 串行执行契约

- [x] 创建项目级 `boss-codex-delivery` Skill。
- [x] 编写 Codex 调用示例和请求顺序说明。
- [x] 验证从 Agent Key 获取当前用户上下文。
- [x] 确认 BOSS iPhone 端推荐/附近/最新及筛选项的真实结构。
- [x] 通过隔离 API 测试验证单岗快照、分析、投递和结果回传。
- [x] 验证岗位身份二次核对、幂等与不确定停止（后端自动化测试）。
- [ ] 以目标投递数 1 做安全 E2E 验收（实际发送前遵循用户当次授权）。

真实手机 E2E 需要当次明确投递授权；开发验收不会擅自发送求职消息。

完成条件：一次运行可从创建走到明确终态，页面数据与手机操作结果一致。

## Phase 5：完整回归与交付

- [x] 运行后端完整测试集或记录无法运行的外部依赖。
- [x] 运行前端类型检查和生产构建。
- [x] 验证旧自动投递页面和核心 API 不受影响。
- [x] 检查 Git diff，确认未覆盖用户已有改动。
- [x] 更新本计划中的完成状态和验证记录。

## 建议提交拆分

1. `docs: define codex delivery requirements and architecture`
2. `feat: add codex delivery storage and agent authentication`
3. `feat: expose codex delivery agent APIs`
4. `feat: add codex delivery management page`
5. `test: verify isolated codex delivery workflow`

当前任务不自动提交；只有用户明确要求时才创建 commit 或 PR。

## 风险与应对

| 风险 | 应对 |
| --- | --- |
| BOSS UI 或筛选项动态变化 | 保存 label + code；遇到未知结构暂停并回传证据 |
| 重复发送 | 平台岗位 ID 去重、步骤幂等 Key、发送前身份二次核对 |
| 结果不可确认 | 标记 `uncertain`，默认停止，不自动重试发送 |
| Agent Key 泄漏 | 只显示一次、摘要存储、过期、撤销、最小权限、HTTPS |
| 影响旧流程 | 新命名空间、新表、新状态机；共享模块只读复用 |
| 前端组件空渲染 | 按 AGENTS.md 检查注册、构建、DOM 和真实交互 |

## 验证记录

2026-10-14：

- 后端新增专项测试：`4 passed`，包含多用户隔离。
- 后端完整测试：`219 passed`，仅有既存依赖弃用警告。
- 后端 Ruff：新增模块、入口和专项测试全部通过。
- 前端 `vue-tsc --noEmit`：通过。
- 前端 Vite 生产构建：通过；仅有既存的大 chunk 提示。
- 项目 Skill：官方 `quick_validate.py` 校验通过。
- 真实 UI：打开 `/codex-delivery`，确认 `.ant-btn` 可见；真实选择经验、学历、公司规模并成功保存配置；成功生成一次仅显示一次的隔离测试 Agent Key。
- 旧流程回归：完整测试通过；UI 登录后旧 `/automation` 路由和旧状态 API 正常加载；专项测试确认新运行不会创建 `automation_runs`。
- 后端修正后完整测试：`220 passed`；新增验证串行步骤锁、岗位身份核对、发送可见证据、结果幂等与不确定停止。
- 已通过 Docker Compose 在本机 `127.0.0.1:8765` 重建并启动 `web`、`local-service`、`automation-runner`；Web 与后端健康检查通过，OpenAPI 中可见全部新增路由和 `/prepare`。
- 部署后的 `/codex-delivery` 路由目前跳转登录页；需用户在浏览器自行登录后补做已部署页面的 DOM、筛选交互与保存验证，不把独立测试环境的验收等同于此次部署验收。
- 用户提供的 Agent Key 在已部署服务上通过只读验证：`/v1/agent/me` 与 `/v1/agent/configs/default` 均返回 200，具备 `agent:read` 和 `agent:run` 权限；`/v1/agent/context` 可访问用户资料、项目、简历和规则，默认配置引用的简历存在。
- 已部署 Agent API 无发送联调：创建测试运行 `#1`，测试岗位 `codex-qa-1791973296` 完成快照采集与本地匹配（评分 84）；随后明确回传 `skipped` 并将运行结束为 `stopped`。数据库核对计数：扫描 1、采集 1、分析 1、跳过 1、投递 0。此步骤未操作 BOSS，也不是手机端 E2E。
- 真实 iPhone 验收运行 `#2`：BOSS“推荐”页在北京应用公司规模 0–20/20–99 人和 BOSS 今日活跃筛选，采集分析 3 个真实岗位。第 1 岗标题截断导致问候语缺字；第 2 岗薪资和职责不合适；第 3 岗要求硕士而用户档案为本科，服务端却误判 100 分可投。3 岗全部安全跳过，运行停止，投递 0。
- 依据真实验收修正新流程：学历硬条件单独否决；手机采集同时写入 PC 端职位快照，复用 PC 端同一问候语生成器，结果同步至投递记录；Skill 不再要求分享/复制链接。隔离测试覆盖快照、问候语、投递记录与硬条件。
- Codex 新流程增加独立发送门槛：学历硬性不符、岗位标题疑似截断、匹配分数或定制可信度未达用户配置阈值均不能自动发送；不改变旧网页投递决策。
- 修正后后端完整测试 `227 passed`，前端 `vue-tsc` 与 Vite 生产构建通过；本机 Docker Compose 已重建并启动 `web`、`local-service`、`automation-runner`，三者均健康。部署后 Agent Key 的 `/v1/agent/me`、默认配置、用户档案接口验证成功。
- 手机解锁后沿用 iPhone Use 启动任务恢复连接；在 BOSS“推荐”页应用 0–20/20–99 人、今日活跃筛选。真实运行 `#3` 采集“北京通明湖信息技术应用创新中心 / 端侧智能体工程师”，快照入库 `job_postings.id=2167`，复用 PC 端问候语生成器，接口返回可投；问候语中的具体经历已在用户资料库核实。
- 发送前二次核对职位身份成功，点击“立即沟通”进入李青青的聊天页。但 BOSS 自定义输入框不作为可编辑控件暴露给 iPhone Use：键盘能打开，`type_text` 两次返回未输入，聊天页无问候语气泡。运行 `#3` 按 `failed` 回传并停止，扫描/分析各 1，成功投递 0，失败 1。SQLite 只读核对：职位快照 `source=codex-phone`、问候语已保存、`has_communicated=0`；投递记录状态 `failed`，关联 `runId=3` 和快照 `2167`。
- 真实发送及发送后确认仍未完成；不能把“打开立即沟通”或生成问候语计为投递成功。需要解决 BOSS 聊天输入框可编辑性后，再做目标 1 的完整 E2E。
- Codex 页面把原“匹配分”改为“资料相似度”，避免把检索相似度 100 错当作 JD 条件 100% 满足；本地网页重新构建通过，Docker Compose 的 Web 和 API 均健康。已部署页面登录后的真实 DOM/交互未在本次重新验收。
- 补核快照 `#2167` 的任职要求时发现 JD 明确写有 Linux 环境使用经验，但用户档案/项目/简历无 Linux 证据；该岗实际不应自动投递。新流程加入这一硬条件的缺证据拦截，专项测试覆盖 API 判定。既有运行 `#3` 仍如实保留当时的分析和失败记录，不伪造回溯投递结果。
- 用户明确授权测试 Mac/iPhone 通用剪贴板：Mac 写入无敏感标记 `JSA-剪贴板联通测试-勿发送` 后，iPhone BOSS 原生“粘贴”菜单成功把完整标记写入未发送草稿，控件树出现 `TextView` 且值完全一致；随后将草稿替换为空格并删除，手机页面恢复空输入框，Mac 原文本剪贴板已尝试恢复。未点击发送。Skill 新增此路径为需用户明确授权的备用输入方式；不得用来绕过分享链接限制。
- Linux 硬条件拦截补充路由集成测试后，后端完整测试 `229 passed`、Ruff 通过；最新 local-service 已在 Docker Compose 重建并处于 healthy，Web 仍 healthy。
