---
name: boss-zhipin-deliver
description: |
  BOSS直聘自动化投递技能 v5.10.0 — 本地 API 原子分析职位，Kimi WebBridge 负责浏览器读取与点击，默认简历图片通过本地 Chrome 测试插件安全发送。
  依赖 Kimi WebBridge（端口 10086）控制已登录 Chrome，从目标关键词搜索页采集岗位并投递。
  支持环境自检、投递断点续传、每日目标检测、HTML 汇报生成和本地数据库同步。
  ★ v5.10.0: 接入简历图片测试插件的预览与确认发送流程，绕过 WebBridge 本地文件权限限制。
metadata:
  version: "5.10.0"
---

# BOSS直聘自动化投递 Skill v5.10.0

> 本技能加载后，Agent 将按三层循环架构执行 BOSS直聘自动化投递。
> 依赖 Kimi WebBridge（端口 10086）控制已登录 Chrome。
>
> **核心设计**：Job Search Assistant 本地服务是业务数据唯一事实源；Kimi WebBridge 只做浏览器 I/O。
> `user_profile.json` 只保存浏览器会话、账号校验、城市编码和本地服务地址等连接信息。

---

## 核心原则

1. **执行脚本**：使用 `python_executor` 运行 `<SKILL_DIR>/scripts/` 下的 .py 文件
2. **原子决策**：完整 JD 必须交给 `/v1/jobs/analyze-and-plan`，由数据库档案、规则和 RAG 证据共同决策
3. **WORK_DIR**：默认使用 Marvis 当前会话的 output 目录，可通过 `BOSS_WORK_DIR` 环境变量覆盖
4. **Kimi WebBridge**：所有浏览器操作通过 `use_skill("kimi-webbridge")` 完成，禁止 CDP 直连

---

## 架构总览

```
scripts/
├── profile_loader.py      — 连接配置 + 本地服务自动化配置加载器
├── env_check.py           — 环境自检 + 自动修复
├── webbridge_client.py    — WebBridge HTTP 客户端（端口 10086）
├── recommend_loader.py    — 推荐页/搜索页导航 + 分批懒加载
├── surface_cache.py       — 精简字段缓存（7 核心字段）
├── jd_reader.py           — 页面内原地点卡读 JD
├── deliver_engine.py      — 投递执行 + 目标检查
├── report_builder.py      — HTML 汇报生成
├── keyword_evolver.py     — AI 关键词进化 + 搜索导航
├── serial_loop.py         — 三层循环主控制器
```

信号文件（位于 WORK_DIR）：
- `page_state.json` — 页面级进度
- `batch_state.json` — 分批级进度
- `surface_cache.json` — 全量缓存
- `jd_to_read.json` — AI 筛选后待读取列表
- `current_jd.json` — 当前 JD（供 Agent 阅读）
- 最终决策不再写 `decision.json`，直接使用本地原子 API 返回的投递计划
- `stream_progress.json` — 投递断点续传

---

## 执行流程

### 步骤 0：确定 WORK_DIR

使用 Marvis 当前会话的 output 目录，或设置环境变量：
```
BOSS_WORK_DIR = <当前会话 output 目录>
```

### 步骤 1：初始化并先搜索（`--step init`）

```
python_executor: 运行 <SKILL_DIR>/scripts/serial_loop.py --step init
```

脚本会检查 WebBridge、重置状态文件，并使用 `search_keywords[0]` 进入目标城市的搜索结果页。`search_keywords` 为空时必须停止，禁止回退为直接消费推荐页。

> ⚠️ **检索红线（必须遵守）**：首次采集前必须看到搜索关键词已出现在搜索状态或 URL 中，并确认页面标题含目标城市。禁止从未带目标关键词的推荐列表直接选择岗位。

**失败处理**：若 WebBridge 不可达，先调用 `use_skill("kimi-webbridge")` 确保 daemon 运行。

### 步骤 1.5：确认投递方向

> ⚠️ **必须执行**：本 skill 面向所有用户发布，Agent **严禁**跳过此步骤直接开始投递。

Agent 必须读取 `GET /v1/automation/config`，展示目标岗位、城市、薪资、阈值、规则和简历图片开关并等待用户确认后，才能进入步骤 2：

- **用户姓名**：`user_name`
- **目标城市**：`target_city`（编码: `city_code`）
- **最低薪资**：`min_salary_k`（单位：K，0 表示不限制）
- **日投递目标**：`daily_target`（份）
- **目标领域描述**：`domain_description`（若未填则展示 prefer/avoid 列表）
- **偏好岗位**：`prefer` 列表
- **排除岗位**：`avoid` 列表
- **额外规则**：是否排除大厂（`prefer_no_big_company`）、是否排除猎头（`prefer_no_headhunter`）
- **搜索关键词**：`search_keywords` 列表（前 10 个）
- **默认简历图片**：根据 `defaultResumeImageAvailable` 显示“已配置”或“未配置”
- **随投递发送简历图片**：`sendResumeImage` 显示“已开启”或“未开启”；开启但默认图片未配置时必须停止图片发送并明确提示

展示后询问用户：是使用这些默认规则，还是需要调整？用户确认后进入步骤 2。

### 步骤 2：中层循环 — 滚动加载（`--step next-batch`）

```
python_executor: 运行 <SKILL_DIR>/scripts/serial_loop.py --step next-batch
```

加载一批约 50 条岗位，追加到 `surface_cache.json`。输出岗位列表供 Agent 初筛。

**Agent 初筛**：Agent 读取输出中的岗位列表，基于 `user_profile.json` 的筛选规则（prefer/avoid/search_keywords/domain_description），将合资格岗位追加写入 `jd_to_read.json`（JSON 数组，每个元素含 page_order、jobId、title 等）。

### 步骤 3：内层循环 — 逐条读 JD + 决策 + 投递

对 `jd_to_read.json` 中每条岗位（按 page_order 顺序）：

**3a. 读取 JD**：
```
python_executor: 运行 <SKILL_DIR>/scripts/serial_loop.py --step read --index N
```
脚本将 JD 写入 `current_jd.json`。

**3b. 本地原子分析**：

`--step decide` 会把 `current_jd.json` 发送给 `POST /v1/jobs/analyze-and-plan`，一次完成快照幂等落库、档案与规则读取、RAG 检索、阈值判断和问候语计划。适合度低于阈值时拒绝；适合度达标但定制可信度不足时使用默认材料。

禁止人工创建 `decision.json` 覆盖数据库规则。若本地服务不可用或 JD 缺少标题、公司、正文，必须停止本条流程，不得点击“立即沟通”。

**3c. 执行决策**：
```
python_executor: 运行 <SKILL_DIR>/scripts/serial_loop.py --step decide --index N
```
APPROVE 时自动投递并检查目标；脚本内置投递目标检查（DAILY_TARGET）。

发送问候语时必须遵守以下事务性守卫：

1. 点击「立即沟通」后，重新读取当前页面，不沿用旧的元素引用。
2. 当前聊天必须同时匹配目标公司和岗位标题；任一不匹配立即停止，禁止发送。
3. `greeting_text` 非空时使用该文本；否则读取常用语列表第一条，但只能读取，禁止通过点击常用语条目触发隐式发送。
4. 仅检查当前右侧会话中的消息；若相同问候语已存在，则视为已完成并跳过发送。
5. 填入后再次校验公司和岗位，再点击一次发送按钮。
6. 只有在目标会话中观察到该问候语新增或已存在时，才能记录为成功；“已建立沟通”或跳转聊天页不能单独视为问候语已发送。
7. `send_resume_image` 默认关闭。只有用户明确开启且 `defaultResumeImageAvailable=true` 时才发送；确认配置时必须显示“默认简历图片：已配置”。未配置时停止图片发送并明确报告，禁止回退到其他文件。
8. 图片发送使用页面右下角 `Job Search Assistant - 简历图片测试版` 插件：先点击“仅加载图片预览”，等待状态包含“尚未发送”，再点击“确认并发送给当前联系人”。BOSS 在文件注入后会立即发送，不再寻找或点击页面上的第二个“发送”按钮。
9. 图片发送前沿用目标公司和岗位双重校验；插件缺失、版本低于 v0.2.3、预览失败或发送状态不明确时，本条投递记为失败，不得回退到 WebBridge `upload`。面板折叠或拖动不得影响 `.load` / `.send` 调用。

**3d. 检查终止条件**：
- 投递目标达标 → **强制跳到步骤 5**
- 致命错误（每日上限）→ **强制跳到步骤 5**
- 本批处理完 → 继续步骤 2 下一批

### 步骤 4：外层循环 — 关键词进化（`--step evolve`）

页面穷尽后：
```
python_executor: 运行 <SKILL_DIR>/scripts/serial_loop.py --step evolve
```

脚本评估投递结果，获取下一个搜索关键词。Agent 确认关键词后：
```
python_executor: 运行 <SKILL_DIR>/scripts/serial_loop.py --step navigate-search --keyword "关键词"
```

回到步骤 2 继续。

**关键词穷尽（无新关键词）→ 强制跳到步骤 5**。不允许在没有新关键词时继续卡在步骤 4。

### 步骤 5：生成汇报 — ★ 强制执行（`--step finish`）

> **拦截性强制步骤。以下任意条件触发时必须立即执行，不得跳过：**
> - 投递目标达标
> - 致命错误（每日上限）
> - 所有页面穷尽且无新关键词
> - 用户主动要求停止投递

```
python_executor: 运行 <SKILL_DIR>/scripts/serial_loop.py --step finish
```

生成 `投递汇总.html` 到 WORK_DIR。报告只包含投递统计和明细，不包含赞赏或二维码区块。

每条成功、失败或跳过结果会调用 `POST {local_service_url}/v1/deliveries` 写入本地 SQLite。
若本地服务暂时不可用，记录会写入 WORK_DIR 下的 `delivery_outbox.json`，下一次同步时自动重试。

---

## 随时查看进度

```
python_executor: 运行 <SKILL_DIR>/scripts/serial_loop.py --step status
```

---

## 环境检查

```
python_executor: 运行 <SKILL_DIR>/scripts/env_check.py
```
包括账户匹配检测（user_profile.json 的用户名/城市 vs 实际登录账户）。

---

## 配置说明

### user_profile.json 字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `user_name` | string | 否 | 登录账号校验与本地报告展示，不参与职位匹配 |
| `target_city` | string | 否 | 本地 API 不可用时的环境自检提示；正式目标城市来自数据库 |
| `city_code` | string | 是 | BOSS 搜索 URL 使用的城市编码 |
| `session_name` | string | 否 | Kimi WebBridge 会话名，默认 `boss-main` |
| `local_service_url` | string | 否 | Job Search Assistant 本地服务地址，默认 `http://127.0.0.1:8765` |

岗位目标、关键词、薪资阈值、每日目标、风险规则、默认问候语及简历图片开关都在管理后台维护，由 `GET /v1/automation/config` 提供。

### 城市编码获取方式

1. 在浏览器中打开 https://www.zhipin.com/
2. 顶部选择目标城市
3. 查看 URL：`https://www.zhipin.com/web/geek/job?city=XXXXXX` → `city=` 后的数字即为 city_code

---

## 重要约束

1. **搜索优先**：必须先使用 `search_keywords` 搜索，再采集岗位；不得从无目标关键词的推荐列表开始。
2. 绝不 navigate 到 job_detail URL（在原页面点卡读 JD）
3. 绝不点击「继续沟通」（投递后点「留在此页」）
4. 投递后必须验证实际结果
5. 每日上限判定为致命错误，立即停止
6. 所有浏览器操作必须通过 Kimi WebBridge，不可 CDP 直连
7. **强制 finish**：投递流程无论以何种方式终止，都必须执行 `--step finish` 生成投递汇总.html。禁止跳过此步骤。
8. **防串会话与去重**：发送前后均校验目标公司和岗位；相同问候语在当前会话已存在时禁止再次发送。

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v5.10.0 | 2026-09-30 | 接入 Chrome 简历图片测试插件：先预览后确认注入；移除 WebBridge upload 回退；确认页显示默认简历图片配置状态 |
| v5.9.3 | 2026-09-30 | 保留岗位卡片 company_size，详情页补采公司规模，并兼容旧 scale 字段写入职位快照 |
| v5.9.2 | 2026-09-30 | 改用 WebBridge fill 写入问候语；等待发送按钮移除 `.disabled`；发送后最长 10 秒轮询验证消息气泡与输入框清空 |
| v5.9.1 | 2026-09-30 | 修复聊天输入框被计入消息列表导致空会话误报成功；发送成功必须同时满足目标消息气泡新增和输入框清空 |
| v5.9 | 2026-09-30 | 本地 API 成为业务唯一事实源；新增原子分析计划，移除 decision.json 最终决策链路 |
| v5.8 | 2026-09-30 | 接入简历库默认首页图片；默认关闭，明确启用后才随问候语发送 |
| v5.7 | 2026-09-29 | 移除报告赞赏二维码；新增 `/v1/deliveries` 数据库同步与本地失败队列 |
| v5.6 | 2026-09-28 | 强制关键词优先搜索；新增目标会话校验、常用语显式发送和重复消息守卫 |
| v5.5 | 2026-08-05 | decision.json 写入改为 shell_executor + Python 一行覆写，消除 delete+write_file 触发的循环确认弹窗 |
| v5.4 | 2026-08-04 | 100% 收尾保证：step_decide target_met / fatal_limit 自动 finish；step_evolve target_met 自动 finish；新增 atexit 兜底钩子确保任何退出路径均生成投递汇总 |
| v5.3 | 2026-08-04 | 面向 GitHub 通用发布：去除所有硬编码用户画像，user_profile.json 为唯一数据源；LLM prompt 由 domain_description 驱动；排除列表支持用户自定义；修复 keyword_evolver 城市名硬编码 |
| v5.2 | 2026-08-04 | Marvis 适配版 |
