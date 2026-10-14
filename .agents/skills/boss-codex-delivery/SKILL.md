---
name: boss-codex-delivery
description: 使用 Job Search Assistant 的 Agent API 与 iPhone Use，在用户明确要求启动手机投递时读取其配置和资料，逐个采集、分析并安全投递 BOSS 职位。用于 Codex 单岗投递，不用于旧网页自动投递或普通求职建议。
---

# BOSS Codex 单岗投递

## 适用边界

只在用户明确要求启动、继续、暂停或查看 Codex 手机投递任务时使用。本 Skill 编排手机和 API，不修改旧网页自动投递任务、浏览器扩展状态或 `automation_runs`。

启动前需要：

- Job Search Assistant Base URL；同机默认尝试 `http://127.0.0.1:8765`。
- 具有 `agent:read` 与 `agent:run` 权限的 Agent Key。
- iPhone Use 服务 READY，手机已解锁且 BOSS 已登录。

Key、验证码、密码和会话信息不得写入项目文件、长期日志或聊天总结。若缺少 Key，引导用户在“Codex 投递”页面生成；不要代替用户创建网页登录身份。

调用接口时读取 [Agent API](references/agent-api.md)。

## 启动与授权

读取 `/v1/agent/me`、`/v1/agent/context` 和 `/v1/agent/configs/default`，向用户简要确认将使用的来源、筛选条件、目标投递数和确认模式。

用户明确要求“开始投递”即授权本次任务在保存的计划边界内提交职位：

- `automatic`：符合规则的岗位可直接发送，直到停止条件成立。
- `per_job`：每个岗位发送前必须等待用户确认。

读取配置或预览岗位不构成发送授权。授权不扩展到修改简历、个人资料、筛选配置或旧任务。

## 串行执行

1. 通过 Agent API 创建运行，保存 `run_id`。
2. 用 iPhone Use 打开 BOSS，按 `sourceTabs` 顺序进入推荐、附近、最新，并应用当前配置。动态筛选优先按 label 定位；code 只作辅助。
3. 每次只处理一个可见职位：打开详情，采集标题、公司、完整 JD、薪资、经验、学历、公司规模、地点、技能、招聘者及活跃状态。不要为取得岗位 ID 使用分享或复制链接；若详情页未显示原生 ID，以这些可见字段生成稳定的本次去重指纹，并在快照中标记 `identitySource=visible-fingerprint`。
4. 携带岗位标识、来源和列表位置调用 `jobs/check`；重复岗位直接跳过。
5. 调用 `jobs/capture` 保存到本次步骤及 PC 端“职位快照”，再调用该步骤的 `analyze`。分析复用 PC 端的资料检索与问候语生成器；以接口返回的 `shouldDeliver`、决策理由及 `greeting` 为准，不自行拼接模板。若屏幕硬条件与个人档案明显冲突，或问候语截断、不实、语病明显，即使评分通过也记录跳过并报告问题。
6. `shouldDeliver=false` 时记录 `skipped` 并处理下一个岗位。
7. `shouldDeliver=true` 且问候语可用时，发送前再次读取同一详情页标题、公司与岗位标识，调用 `jobs/{stepId}/prepare` 完成二次核对。API 返回 `opening_chat` 后：
   - 点击“立即沟通”；
   - 输入 API 返回的 `greeting`；
   - 发送；
   - 只有看到可验证的已发送消息或成功状态，才以 `evidence.messageVisible=true` 记录 `delivered`。
8. 通过 `jobs/{stepId}/result` 回传结果；接口同步 PC 端职位快照跟进和投递记录。结果明确失败记录 `failed`；无法确认是否已经发送则记录 `uncertain`，不得自动重发。
9. 每个 result 使用稳定且唯一的 `idempotencyKey`。API 返回任务终态后立即停止。

一个岗位形成明确结果前，不得打开下一个岗位或并行操作。

## 安全停止

出现以下任一情况立即暂停或结束并向用户说明：

- 登录失效、验证码、Face ID、密码或风控；
- 页面结构变化导致岗位身份无法核对；
- 发送结果不确定；
- Agent Key 失效或被撤销；
- 达到目标投递数、最大扫描数或 API 返回终态；
- 用户要求暂停或停止。

验证码、密码和 Face ID 由用户接管。不要猜测认证信息，不要绕过平台安全措施。

## 完成汇报

任务结束后从运行接口读取最终统计，汇报任务状态、扫描/分析/符合/成功/跳过/失败/不确定数量及停止原因。不要把“已分析”描述成“已投递”。
