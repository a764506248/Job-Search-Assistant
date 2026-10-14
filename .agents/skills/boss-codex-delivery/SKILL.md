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
5. 调用 `jobs/capture` 保存到本次步骤及 PC 端“职位快照”，再调用该步骤的 `analyze`。分析复用 PC 端的资料检索与问候语生成器；接口分数只是资料检索相似度，不代表 JD 条件 100% 满足。逐项核对学历、经验、技术硬要求与资料证据；任一明确要求缺少证据时，即使 `shouldDeliver=true` 也不得发送，应记录跳过并报告缺口。问候语截断、不实或语病明显时同样跳过。
6. `shouldDeliver=false` 时记录 `skipped` 并处理下一个岗位。
7. `shouldDeliver=true` 且问候语可用时，发送前再次读取同一详情页标题、公司与岗位标识，调用 `jobs/{stepId}/prepare` 完成二次核对。API 返回 `opening_chat` 后：
   - 点击“立即沟通”；
   - 按以下顺序准备单条消息，前一种无法得到可核对的完整草稿时才进入下一种：① 用 iPhone Use `pua_type_text` 一次输入 API 返回的完整 `greeting`，优先定位输入框；若定位不到，先点击可见输入框再无 selector 输入。输入不完整时先读回已有内容，只补缺失部分，不重发全文。② 尝试已授权的 Mac→iPhone 通用剪贴板：仅在内存中暂存 Mac 原纯文本剪贴板，复制完整 `greeting`，在 iPhone 聊天输入框点原生“粘贴”，从手机读回草稿，然后恢复 Mac 剪贴板；不要复制职位分享链接。③ 若前两种均失败，打开 BOSS“常用语”，检查第一条的完整内容；仅在它适用于当前岗位、没有不实或敏感信息时使用第一条。若不可用，不发送，记录 `failed` 并说明原因。
   - 发送前核对当前会话对应的招聘者/岗位以及完整文案。`pua_type_text` 与粘贴须读回输入框草稿；常用语须在点击前读清第一条全文，并确认选择它是填入草稿还是直接发送。若直接发送，只有上述核对完成后才点一次；不得为了测试发送或重复点击。
   - 发送后确认消息确实出现在当前会话；回传 `evidence.messageVisible=true`、`evidence.inputMethod`（`pua_type_text`、`universal_clipboard` 或 `first_common_phrase`）及 `evidence.sentText`（实际发送全文）。第三种文案不等于 PC 端生成的 `greeting` 时，不得声称发送了生成文案；API 仍保留原生成文案供对照。
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
