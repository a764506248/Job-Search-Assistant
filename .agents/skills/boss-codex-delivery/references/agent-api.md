# Agent API

所有请求使用：

```http
Authorization: Bearer <Agent Key>
Content-Type: application/json
```

## 初始化

1. `GET /v1/agent/me`：验证 Key 与当前用户。
2. `GET /v1/agent/context`：读取档案、项目、简历、规则和求职目标。
3. `GET /v1/agent/configs/default`：读取筛选及投递计划。
4. 展示前三个只读接口返回的执行方案、资料依据及手机入口，等待用户明确确认。确认前不创建运行，也不开始手机导航或筛选；完整确认要求见 [SKILL.md](../SKILL.md#启动与授权)。
5. 用户确认且手机 READY 后，`POST /v1/agent/runs`，body 为 `{}` 或 `{ "configId": 1 }`：创建运行。

`jobIntentions` 不是手机搜索词，`sourceTabs` 指定首页来源页签。例如 `["最新"]` 对应首页「最新 → 筛选」，不对应搜索结果「最新优先」。搜索路径需要用户另行明确要求并确认。

## 单岗循环

检查：

```http
POST /v1/agent/runs/{runId}/jobs/check

{"platformJobId":"...","sourceTab":"最新","listPosition":1}
```

采集：

```http
POST /v1/agent/runs/{runId}/jobs/capture

{
  "platformJobId":"...",
  "sourceTab":"最新",
  "listPosition":1,
  "snapshot":{
    "title":"...",
    "companyName":"...",
    "description":"...",
    "skills":[],
    "salaryText":"...",
    "experience":"...",
    "education":"...",
    "companySize":"...",
    "location":"...",
    "recruiterName":"...",
    "recruiterTitle":"...",
    "recruiterActiveText":"..."
  }
}
```

`title`、`companyName`、`description` 必填。手机详情页未展示原生岗位 ID 时，`platformJobId` 可使用标题、公司、招聘者、地点、薪资等可见字段生成的稳定指纹；在 `snapshot.identitySource` 标记 `visible-fingerprint`，不要通过分享/剪贴板取链接。响应中的 `id` 是 `stepId`，`snapshot.pcSnapshotId` 是同步写入 PC 端“职位快照”的记录 ID。

**公司名称的采集口径（硬性）**：

- `companyName` 只取**控件树**中招聘者卡片「公司名 · 职位」对应的可见文本，不读截图、不写工商全称、不自行补全；控件树与截图不一致时以控件树为准。
- `capture` 的 `snapshot.companyName` 与 `prepare` 的 `observedCompanyName` 应取同一页面字段、保持逐字相同。后端虽允许常见法定后缀的简称/全称归一化，不应依赖它纠正采集错误；不同公司的名称仍会返回 409。
- 同一原则适用于 `title`：只取控件树中详情页标题节点的文本。

`capture` 后、`analyze` 前应核对快照字段；步骤分析后锁定，不能再对该步骤重跑 `capture/analyze`。

分析：

```http
POST /v1/agent/runs/{runId}/jobs/{stepId}/analyze
```

读取响应中的 `shouldDeliver`、`decisionReasons`、`score`、`greetingConfidence` 与 `greeting`。问候语使用 PC 端同一生成器，生成内容也保存在职位快照中。结合 JD 的主要职责判断整体相关性，不要求全部技能、工具、年限或加分项逐条匹配；明确禁投规则及真实且不可协商的条件冲突仍需遵守。选岗时先看可见名称，优先相关岗位，略过明显跨行业/职责无关项，详见 [选岗与相关性判断](../SKILL.md#选岗与相关性判断)。

资料遗漏造成的误判与真实不匹配分开报告。此判断策略不改变 API 状态机：`shouldDeliver=false` 时不能自行发送，`prepare` 仍必须返回 `opening_chat`；仅修改 Skill 不会自动修复或改变后端判定逻辑。

发送前二次核对：

```http
POST /v1/agent/runs/{runId}/jobs/{stepId}/prepare

{
  "platformJobId":"...",
  "observedTitle":"详情页当前岗位标题",
  "observedCompanyName":"详情页当前公司名称",
  "userConfirmed":true
}
```

`prepare` **只校验本次上报的 `observedTitle` / `observedCompanyName` 与该步骤已锁定的快照是否一致，不校验快照本身是否真实**。因此它能发现中途换页或岗位不一致，不能发现采集时就把两边写成相同错误值。调用前先回到详情页顶部，确认当前页面就是目标岗位，再从控件树取这两个值上报；真正的正确性保障在采集阶段，见「公司名称的采集口径（硬性）」。

只有响应状态为 `opening_chat` 才能发送。`confirmationMode=per_job` 时，只有取得本岗位用户明确确认后才能传 `userConfirmed=true`；自动模式可省略。接口会将公司常见法定后缀规范化后核对，简称与对应全称可以通过；岗位 ID、标题或规范化后的公司名不同仍返回 409。已分析步骤不能重跑 `capture/analyze`。核对不通过时记录该岗位失败，不要发送。

结果：

```http
POST /v1/agent/runs/{runId}/jobs/{stepId}/result

{
  "outcome":"delivered|skipped|failed|uncertain",
  "idempotencyKey":"run-{runId}-job-{platformJobId}-send-v1",
  "evidence":{
    "messageVisible":true,
    "inputMethod":"first_common_phrase",
    "sentText":"手机当前会话中实际发送的完整文案",
    "resumeOutcome":"sent|failed|not_available",
    "resumeVisible":true,
    "resumeError":null
  },
  "errorMessage":null
}
```

**无论 `outcome` 为何值，`evidence` 都必须是对象，不能为 `null`**（传 `null` 会返回 422）。未发送时可写：

```json
"evidence": {"messageVisible": false, "inputMethod": "none", "sentText": ""}
```

`delivered` 必须有 `messageVisible=true` 的已发送页面证据。`inputMethod` 按实际方式填写 `pua_type_text`、`wda_keys`、`universal_clipboard` 或 `first_common_phrase`，`sentText` 填实际全文；使用第一条常用语时不能填 PC 端生成的问候语。`wda_keys` 仅用于 [iPhone 输入与回读](iphone-input.md) 所述的已聚焦自定义输入框兜底，不表示发送动作。配置要求发送简历时还必须报告 `resumeOutcome`；只有 `sent` 需要 `resumeVisible=true`。结果接口同步写入 PC 端投递记录；确认发送后职位快照显示“已沟通”。发送结果不可确认时用 `uncertain`，不能将其记为成功或自动再次发送。同一运行一次只允许一个尚未结束的岗位。非终态结果后，打开下一岗位前至少等待配置的 `intervalSeconds`。

## 控制与状态

- `GET /v1/agent/runs/{runId}`：读取运行、步骤和是否已经终止。
- `POST /v1/agent/runs/{runId}/pause`：安全暂停。
- `POST /v1/agent/runs/{runId}/finish`：body 为 `{ "status": "completed|stopped|failed|uncertain", "reason": "..." }`。

401 表示 Key 无效、过期、撤销或权限不足；409 表示状态冲突，不要以发送动作重试来绕过；422 表示请求或岗位快照字段不完整。
