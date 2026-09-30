# BOSS 踩坑全记录

本文档收录所有已知技术陷阱、回避策略和解决方案。
**每条经验均来自实际失败/排查，不可忽略。**

---

## B28 — 子进程僵尸：杀 session 时 pipeline 不受控继续跑

**严重等级: 🔴 高**

**现象**: 杀掉 sub-agent 或关闭终端后，`pipeline_quick.py` 仍在后台运行。
多次启动导致 4 个进程同时跑同一批候选（PID 12360/17600/15452/17328）。

**根因**: OpenClaw 的 exec/sub-agent 使用的是 kill 父进程（python3），
但 Windows 不做进程树级联杀，导致孩子进程（pipeline_quick）变成孤儿。
孤儿进程读到 state 文件后自动 --resume，与新的正常进程争用。

**修复**:
    - `pipeline_quick.py` 已加入 PID 锁机制 (`acquire_lock()`)
    - 锁文件: `%TEMP%/boss_pipeline_locks/pipeline_MMDD.lock`
    - 启动时检测已有实例 → 拒绝启动（exit 1）
    - 正常退出 / SafeInterrupt / atexit 均释放锁
    - 过期锁（>3h 或 PID 不存在）自动清理

**人工清理**:
    ```powershell
    # 查僵尸进程
    Get-Process python* | Where-Object {$_.Path -match "python"} | ft Id,StartTime
    # 清理锁文件
    ls $env:TEMP\boss_pipeline_locks\
    del $env:TEMP\boss_pipeline_locks\pipeline_*.lock
    ```

**教训**: 永远不要用 `sessions_spawn` 来跑 pipeline_quick。
直接用 `exec` + background + process poll 自己做监控。

---

## B27 — 滚动懒加载间歇失效（误判为「无更多数据」）

**严重等级: 🟡 中**

**现象**: 某些关键词滚动后 `extract_jobs_via_js()` 返回与 pg1 相同的 15 条，
    `累计新增=0`，误认为懒加载未触发。

**根因**: 有两种情况：
    1. **真实无更多数据**（约 30% 的小众关键词，如「茶社」「乡村运营」杭州全量仅 1-15 条）
    2. **SPA 渲染延迟**（`navigate` 后 Vue SPA 可能未完全初始化懒加载监听器）

**验证方法**: 检查 `document.body.scrollHeight` 是否增长

    # 在页面上执行
    [document.querySelectorAll('li').length, document.body.scrollHeight]
    # 等待 3-4 秒后再次执行——如果数量不变且高度不变 → 无更多数据

**修复**:
    - 不依赖单一关键词，使用 30+ 关键词交叉覆盖
    - 每个关键词滚动 5 次，能加载说明懒加载正常
    - 增加关键词「度假」「餐饮管理」「店长」等大流量词（实测可滚动至 75+ 条/关键词）

---

## B26 — daemon.pid 残锁文件导致 WebBridge 拒绝启动

**严重等级: 🟡 中**

**现象**: `kimi-webbridge.exe start` 输出 `daemon started` 但立即退出（exit code 0），
daemon 日志显示 `Error: write pid: open C:\Users\W\.kimi-webbridge\daemon.pid: The file exists.`

**根因**: daemon 在启动时创建 `daemon.pid` 锁文件。异常崩溃/强杀后锁文件残留，
新 daemon 认为已有实例在运行，自动退出。

**解决**:
```powershell
Remove-Item -Path "$env:USERPROFILE\.kimi-webbridge\daemon.pid" -Force
```
删除后重新 `kimi-webbridge.exe start` 即可。

**预防**: 在启动脚本前自动清理：
```python
pid_file = os.path.expanduser('~/.kimi-webbridge/daemon.pid')
if os.path.exists(pid_file):
    os.remove(pid_file)
```

---

## B1 — WebBridge 无登录态 / 其他工具无登录态

**严重等级: 🔴 致命**

**现象:** 用 CDP 直连/xbrowser/内置 browser 投递时，跳转详情页显示登录界面，投递全部失败。

**根因:** Boss 直聘登录态存储在 Chrome Cookie 和 localStorage 中。CDP/xbrowser/Playwright 启动新 profile 或隔离 session，没有登录态。

**解决方案:**
- ✅ 始终用 Kimi WebBridge（端口 10086）
- ❌ 禁止 CDP 直连、xbrowser、内置 browser 工具
- 如果 WebBridge 不可用，先修复 WebBridge，**绝不可换用其它工具**

**真实教训:**
> 2026-06-12：因 compaction 后丢失上下文，改用 CDP+xbrowser+内置 browser，8 条岗位全部因未登录失败。此后写入 MEMORY.md 四项防复发规则。

---

## B2 — 中文 body 编码崩溃（UnicodeEncodeError）

**严重等级: 🔴 致命**

**现象:** `http.client` 发送含中文 JSON 时触发 `UnicodeEncodeError: 'latin-1' codec can't encode characters`

**根因:** `http.client` 默认用 `latin-1` 编码 `str` 类型 body，中文无法编码。

**解决方案:**
```python
# 正确：encode 为 bytes
body = json.dumps({"action": action, "args": args, "session": self.session}).encode("utf-8")
conn.request("POST", "/command", body=body, headers={"Content-Type": "application/json"})

# 错误：传 str
body = json.dumps(...)
conn.request("POST", ...)  # UnicodeEncodeError
```

> `webbridge_client.py` 已内置此修复。所有脚本通过 import 复用即可。

---

## B3 — snapshot 返回不完整/空树

**严重等级: 🟡 中等**

**现象:** `snapshot` 返回空树或不完整的 accessibility tree。

**根因:** Boss 直聘是 Vue SPA，accessibility tree 在 SPA 渲染后可能不可用。

**解决方案:**

| 操作 | 推荐方法 |
|------|---------|
| 读取页面内容 | `evaluate("document.body.innerText")` |
| 提取结构化数据 | `evaluate` 执行 JS 返回 JSON |
| 定位"立即沟通"按钮 | `snapshot` → 找 `@e` ref → `click(@eXX)` |
| 点击按钮 | `click({selector: "@e18"})` |

---

## B4 — 薪资字体加密（2026-06-15 修正）

**严重等级: 🔴 致命（旧版所有薪资偏移+1）**

**现象:** 提取的薪资字段为乱码（如 `\ue039-\ue032\ue031K`）。

**根因:** Boss 直聘自定义 font-face 将 0-9 映射到 **U+E031~U+E03A**，不是 U+E030~U+E039。

### 旧版错误（2026-06-15 前）

旧版使用 `ord(ch) - 0xE030`，导致**每位数字偏移+1**。

| 加密原文 | 旧版结果 | 正确结果 |
|---------|---------|---------|
| `\ue036-\ue037K` | 6-7K ❌ | 5-6K ✅ |
| `\ue039-\ue032\ue033K` | 9-23K ❌ | 8-12K ✅ |

影响：之前所有提取的薪资数据均偏高。

### 正确解密

**公式:** `ord(ch) - 0xE031`
**范围:** 0xE031 ~ 0xE03A → 数字 0~9

```python
def decrypt_salary(text):
    result = []
    for ch in text:
        cp = ord(ch)
        if 0xE031 <= cp <= 0xE03A:
            result.append(str(cp - 0xE031))
        else:
            result.append(ch)
    return ''.join(result)
```

### 映射表

| Unicode | 正确值 | 旧版错误 |
|---------|-------|---------|
| U+E031 | 0 | (旧: 1) |
| U+E032 | 1 | (旧: 2) |
| ... | ... | ... |
| U+E03A | 9 | — |

### 已修复文件
- `scripts/phase1_extract.py`
- `scripts/phase3_jd.py`
- `references/salary_decrypt.md`

> 旧 JSON 文件中的薪资数据是错的，需重新提取。

---

## B5 — 批量脚本失控投递垃圾岗

**严重等级: 🔴 致命**

**现象:** 自动脚本无脑投递大量实习、日结、主播等低端岗位。

**根因:** 过滤规则过于简单，无法处理复杂语义。

**解决方案:**
- ✅ 停止批量全自动投递
- ✅ 改为 **AI 逐条判断 + 用户决策**
- ✅ 不要用 `background:true` 启动脚本

**真实教训:**
> 2026-06-12：用户强烈批评无脑投递垃圾岗。此后改为五步流程，Phase 2/4 均由 AI 逐条把关。

---

## B6 — 行业排除过杀

**严重等级: 🟡 中等**

**现象:** "保险"排除词误杀含"五险一金"的 JD。

**解决方案:**
- ✅ 标题排除用窄词：保险、外卖、网约车、快递、地推、拉新、纯销售
- ✅ 正文排除更精确：医美、口腔、婚恋、纯金融、P2P、保健品会销
- ❌ 不在正文排除中使用宽泛词（保险、投资、金融、培训）

---

## B7 — PowerShell 写 JSON 带 BOM

**严重等级: 🟢 低**

- ✅ 统一用 Python `json.dump(..., ensure_ascii=False)` 写 JSON
- ❌ 不用 PowerShell 写 JSON 文件

---

## B8 — 岗位已关闭未确认

**严重等级: 🟢 低**

```python
text = wb.evaluate("document.body.innerText")
if "职位已关闭" in text or "停止招聘" in text:
    continue  # 跳过
if "继续沟通" in text:
    continue  # 已沟通过
```

---

## B9 — Chrome 连接丢失（WebSocket 403）

**严重等级: 🟡 中等**

- ✅ Chrome 启动需 `--remote-allow-origins=*`（WebBridge 自动处理）
- ✅ 检查顺序：daemon 状态 → 扩展连接 → 登录态
- ✅ 如 Chrome 被 kill → 重启 Chrome → 等待 WebBridge 自动重连

---

## B10 — Boss Vue SPA 渲染延迟

**严重等级: 🟡 中等**

- ✅ navigate 后等待 `random.uniform(5, 8)` 秒
- ✅ 首次失败后额外等待 3 秒重试
- ✅ 不要过早提取（等待不足 3 秒必失败）

---

## B11 — DOM 选择器猜错：公司名不在 .company-name

**严重等级: 🔴 致命**

**根因:** Boss 直聘列表页公司名在 `.boss-name`，不是 `.company-name`。

```javascript
// 错误（永远拿不到）
const company = card.querySelector(".company-name a")?.innerText;  // 空

// 正确
const company = card.querySelector(".boss-name")?.innerText;  // "骏辉食品"
```

> 任何新选择器使用前，必须先 `innerHTML` 探测实际 DOM 结构。

---

## B12 — DOM 选择器猜错：地区不在 .job-area

**严重等级: 🟡 中等**

**根因:** Boss 直聘地区在 `.company-location`，不是 `.job-area`。

```javascript
// 错误
const location = card.querySelector(".job-area")?.innerText;  // 空

// 正确
const location = card.querySelector(".company-location")?.innerText;  // "杭州·滨江区·长河"
```

---

## B13 — 搜索关键词选择影响岗位质量

**严重等级: 🟡 中等**

**现象:** 用"住宿运营"搜索，结果全是低质量岗（运营助理/小白/包住宿/直播/网红）。

- ✅ 使用精准关键词：酒店经理、民宿管家、酒店运营、酒店总经理、文旅运营、民宿店长
- ❌ 避免宽泛词：住宿运营、运营管理
- ✅ 多关键词组合（6个）比单一关键词覆盖面更广

---

## B14 — 日薪/时薪岗位伪装高薪

**严重等级: 🟢 低**

```python
EXCLUDE_SALARY = ['元/天', '元/时', '元/周']
if any(kw in salary for kw in EXCLUDE_SALARY):
    continue  # 排除非月薪岗位
```

---

## B15 — WebBridge daemon 被终止后需手动重启

**严重等级: 🟡 中等**

**现象:** 上次运行后 daemon 被 terminated，端口 10086 无监听。

```bash
# 检查
python3 -c "from scripts.webbridge_client import WebBridge; wb=WebBridge(); print(wb.health_check())"

# 启动
Start-Process "C:\Users\W\.kimi-webbridge\bin\kimi-webbridge.exe" -ArgumentList "start"
Start-Sleep -Seconds 5
```

---

## B16 — 标题中混入薪资文字

**严重等级: 🟢 低**

```javascript
let title = titleLink.innerText.trim().split('\n')[0]; // 只取第一行
```

---

## B17 — 猎头职位误投

**严重等级: 🔴 致命**

**Phase 2 粗筛排除公司名关键词：**
```python
HEADOUT_COMPANY_KEYWORDS = ['人力', '咨询', '猎头', '人才', 'RPO', '猎聘', '劳务', '外包']
if any(kw in company for kw in HEADOUT_COMPANY_KEYWORDS):
    continue
```

**Phase 4 精筛排除：**
- JD 正文含 "为客户寻找"、"代招"、"受客户委托"、"外包"、"派遣" → 不投
- 发布者身份为猎头顾问/招聘顾问 → 不投

**同时排除金融类：** 不良资产、贷款、放贷、信贷、金融外包、担保、抵押、典当

---

## B18 — 空搜索优先 + 懒加载操作方法

**严重等级: 🟡 中等**

### 懒加载机制

Boss 直聘空搜索页和关键词搜索页使用**相同的懒加载机制**：

| 属性 | 值 |
|------|----|
| 初始卡片数 | 15-17 张 |
| 每次追加 | ~15 张 |
| scrollH 增量 | ~2250px/次 |
| 加载上限 | ~450 张（约30次滚动） |
| 加载方式 | 页面级滚动 + IntersectionObserver |

### 正确滚动方法

```python
import time
from scripts.webbridge_client import WebBridge

wb = WebBridge(session="boss-YYYYMMDD")
wb.navigate("https://www.zhipin.com/web/geek/job?city=101210100", wait=8)

while True:
    cards = int(wb.evaluate("document.querySelectorAll('a[href*=\"job_detail\"]').length"))
    if cards >= 100:
        break
    wb.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3.5)
```

**关键参数：**
- 每次 `scrollTo` 后必须等 **3-4 秒**（2 秒不够，IntersectionObserver 未触发）
- 监听到新卡片追加再继续下一次滚动
- **不限制滚动次数**，直到停止追加新内容或卡片数达标

### 空搜索 vs 关键词搜索

| | 空搜索 | 关键词搜索 |
|---|--------|-----------|
| URL | `?city=101210100` | `?city=101210100&query=酒店经理` |
| 懒加载 | 有 | 有 |
| 上限 | ~450 条 | ~450 条 |
| 匹配度 | 推荐算法，泛匹配 | 精准匹配标题 |
| 推荐策略 | **优先空搜索**，不满再关键词补充 |

### 坑：空搜索无懒加载的假象

**现象：** 点击"查看更多信息"链接后 scrollTo 无响应，认为空搜索只有 15 条。

**根因：** 实际上是 WebBridge session 无标签页 → evaluate 静默返回空 → scroll 执行了但无法验证结果。

**修复：** 先用 `navigate()` 建立 session 后再操作。参见 B19。

---

## B19 — WebBridge session 无标签页 → evaluate 静默返回空

**严重等级: 🔴 致命**

**现象:** navigate 后 `evaluate("1+1")` 返回空字符串（而非 `"2"`）。所有数据提取/滚动验证都静默返回空。

**根因:** WebBridge daemon 重启后，session 自行创建的标签页丢失。`webbridge_client.py` 的 `evaluate()` 实现：`r.get("data", {}).get("value", "")` — 当后端返回 `{"ok": false}` 时，`data` 不存在，返回空字符串。

**诊断方法：**
```python
# 直接调用 API 看真实响应
import json, http.client
conn = http.client.HTTPConnection('127.0.0.1', 10086, timeout=30)
body = json.dumps({'action':'evaluate','args':{'code':'1+1'},'session':'boss-0613'}).encode('utf-8')
conn.request('POST', '/command', body=body)
resp = conn.getresponse()
print(resp.read().decode())
# 正常: {"ok":true,"data":{"value":"2"}}
# 异常: {"ok":false,"error":{"code":"tool_error","message":"session \"boss-0613\" has no tab"}}
```

**解决方案：**
1. 检查 session 是否有标签页：`wb.navigate(url, wait=...)` → 必须返回 `ok=True`
2. 不要假设 daemon 重启后 session 自动恢复
3. WebBridge 重启后先用简单 evaluate 验证连通性（`1+1` → `"2"`）
4. 每次 session 中断后必须重新 navigate

> 之前的 `health_check()` 只检查 daemon 连通性（list_tabs），不保证 session 有标签页。

> ✅ **新方案**：`webbridge_client.py` 新增 `ensure_active_tab()` 和 `verify_login()` 方法，一站式完成 session 初始化 + 标签页验证 + 登录态检查。

---

## B20 — Phase 5 投递后状态检测文本不全

**严重等级: 🟡 中等**

**现象:** 13 个岗位全部点击"立即沟通"成功，但脚本全部返回"已点击(需验证)"，没有标记为"沟通成功"。

**根因:** 状态检测只检查了 `已向BOSS发送` 和 `继续沟通`，但 Boss 直聘不同场景返回不同文案。

**2026-06-15 修正：**

```python
SUCCESS_TEXTS = [
    "已向BOSS发送",   # 首次沟通成功
    "继续沟通",       # 已沟通过
    "沟通成功",       # 另一种成功文案
    "发送成功",       # 另一种成功文案
    "感兴趣",         # 点击后按钮上出现
]
```

同时新增 `body_with_retry()` 函数：先读 body，若 < 200 chars 则等 5s 重试一次。解决 SPA 渲染慢导致的检测失败。

---

## B21 — CDP/WebBridge  连续导航缓存失效

**严重等级: 🟡 中等**

**现象:** Phase 3 提取第 1-5 个 JD 正常，第 6 个之后 body 全部返回相同内容（约 2819 chars 缓存内容），薪资变为 `?`。

**根因:** WebBridge 的 `navigate` 在连续 5+ 次调用后，Vue SPA 的路由缓存机制导致页面不重新渲染，`evaluate` 返回缓存的 body。

**解决方案（2026-06-15）：**

```python
# 每 5 次导航后重置到搜索页
SEARCH_PAGE = "https://www.zhipin.com/web/geek/job?city=101210100"

for i, job in enumerate(target):
    navigate(job_url)
    # ... 提取 JD ...

    # 每 5 次重置一次
    if (i + 1) % 5 == 0:
        navigate(SEARCH_PAGE, wait_range=(3, 5))
```

Boss 直聘搜索页在每次 navigate 后完整刷新 DOM，可作为"重置"锚点。

---

## B22 — AI 精筛排除词粒度不足（标题 vs 正文）

**严重等级: 🟡 中等**

**现象:** 排除词在 JD 正文匹配导致误杀好岗位。

| 排除词 | 被误杀的 JD | 为什么匹配 |
|--------|------------|-----------|
| 保洁 | 航天五院园区运营岗 16-30K | JD 正文提到"保洁服务" |
| 保险 | 含"五险一金"的任何 JD | 五险一金含"险"字 |
| 投资 | 无投资要求的 JD | "投资建设/投资运营"等 |
| 金融 | 金融科技公司的运营岗 | 公司行业含"金融" |

**解决方案（2026-06-15）：**

排除词按匹配层级分三档：
- **T 级（标题）**：硬排除，仅匹配岗位标题
- **C 级（公司名）**：硬排除，仅匹配公司名称
- **B 级（正文）**：标记不淘汰，AI 综合判断

详见 `references/filtering.md` 排除词分档规则。

---

## B23 — SPA 渲染等待时间不足

**严重等级: 🟡 中等**

**现象:** navigate 后 body 为空或 `< 200 chars`，`evaluate("document.body.innerText")` 没有内容。

**根因:** Boss 直聘 Vue SPA 需要下载 JS bundle（~2MB）→ 解析 → 渲染。高峰期或 Chrome 缓存未命中时，8s 不够。

**修复（2026-06-15）：**
- ✅ navigate 后等待 **8-12s**（旧值 5-8s）
- ✅ body 为空时等 5s 再重试一次
- ✅ SKILL.md 和 operations.md 中的 wait 参数已更新

**实测数据：**
- 登录页（首页）：~8s 渲染完成
- 详情页：~10s 渲染完成（含 API 请求 JD 数据）
- 搜索页（空搜索/关键词）：~6s

---

## B24 — Boss 直聘求职者消息中心路由未知

**严重等级: 🟢 低**

**现象:** `/chat/geek/` 和 `/web/geek/message` 都会重定向到首页。

**猜测:** Boss 直聘求职端消息中心可能在 SPA 内部路由中，路径未知。

**待确认：** 手动登录 Boss 直聘 Web 端，实际打开消息页面后，查看浏览器 URL 并记录。

---

## B25 — Kimi WebBridge pid 锁文件残留阻塞启动

**严重等级: 🔴 致命**

**现象:** `kimi-webbridge restart` 或 `start` 输出 `"daemon started (pid XXXX)"`，但 `status` 返回：

```json
{"note":"PID file exists but HTTP probe failed — daemon may be starting or stuck","pid":6004,"running":false}
```

**根因:** daemon 异常退出（如系统重启、进程被 kill 后未执行 stop），`~/.kimi-webbridge/daemon.pid` 文件残留。新 daemon 启动时检测到该文件，认为已有实例在运行，不写入自己的 pid 也无法正常监听端口。

**现场还原（2026-06-15）：**
- 旧 daemon（pid 6004）已死
- 执行 `kimi-webbridge stop` → `Post .../shutdown: connection refused`（旧进程已死，当然拒绝）
- 执行 `kimi-webbridge start` → `daemon started (pid 10448)`
- 执行 `status` → 仍读取 pid 6004 的文件，返回 `running: false`
- 新 daemon（pid 10448）因为 pid 文件被占，无法完成初始化

**解决方案：**

> **优先用 Python 删除 pid 文件**，因为 PowerShell `Remove-Item` 可能被安全策略拦截。

```bash
python3 -c "import os
for f in ['daemon.pid','daemon.pid.bak','daemon.pid.bak2']:
    p = os.path.join(os.path.expanduser('~/.kimi-webbridge'), f)
    if os.path.exists(p): os.remove(p); print(f'Removed: {f}')
"
```

然后重启 daemon：

```bash
~/.kimi-webbridge/bin/kimi-webbridge start
```

**预防措施：**
1. daemon 异常退出后，执行 `kimi-webbridge stop` 先尝试优雅关闭
2. 如果 `stop` 返回 connection refused（旧 pid 已死），用 Python 清理 pid 文件
3. 不要用 PowerShell `Remove-Item` 删除 pid 文件（可能触发安全策略）

**诊断命令：**
```python
import os, glob
conflicting = glob.glob(os.path.expanduser('~/.kimi-webbridge/daemon*'))
for c in conflicting:
    print(c, os.path.getsize(c))
```

---

---

## B27 — SIGKILL 中断丢失进度

**严重等级: 🟡 中等**

**现象:** Phase 3 或 Phase 5 中途被 Exec 工具 SIGKILL，已处理的几十条数据丢失（如果没有增量保存）。

**v2 解决方案：**

1. **信号处理器**：`register_signal_guard()` 捕获 SIGTERM → 抛出 `SafeInterrupt` → `except SafeInterrupt:` 保存状态

```python
from scripts.webbridge_client import register_signal_guard, SafeInterrupt

register_signal_guard()
try:
    for job in jobs:
        ...
except SafeInterrupt:
    save_progress()
    raise
```

2. **pipeline_quick.py**：每个岗位处理完立即写入 state.json，SIGKILL 只丢失当前一条

3. **增量保存**：传统 phase 脚本仍保留每 5 条保存一次的机制

---

## B28 — B21 缓存错位导致 JD 内容错误

**严重等级: 🔴 致命**

**现象:** Phase 3 导航到 job_detail/X.html 后显示 A 岗位的 JD 内容。

**根因:** Boss 直聘 Vue SPA 路由缓存，连续导航后 DOM 不刷新。

**v2 检测方案：**

```python
from scripts.webbridge_client import title_similarity

similarity = title_similarity(detail_title, phase1_title)
if similarity < 0.5:
    job["_b21_low_confidence"] = True  # Phase 4 降级
```

Phase 4 v2 根据 `_b21_low_confidence` 扣分降级：
- 评分减 10 分
- "推荐" 降级为 "可考虑 (B21不确定)"

---

## B29 — Phase 2 无关岗位过多

**严重等级: 🟡 中等**

**现象:** Phase 2 过筛率 ~90%，大量无关岗位（如销售代表、运营助理）进入 Phase 3，浪费提取时间。

**v2 解决方案：**

Phase 2 v2 新增标题行业词检测：
- 标题必须含 `酒店/民宿/文旅/景区/度假/运营/店长/经理/主管` 中至少一个词
- 且薪资必须 < 10K（高薪岗位保留，无论标题）
- 不符合的跳过

---

## B30 — 中间文件堆积

**严重等级: 🟢 低**

**现象:** 每次运行产生 5-12 个 JSON/MD 文件。

**解决方案：**

```python
from scripts.webbridge_client import cleanup_output_files
cleanup_output_files(days_keep=0)  # 归档旧文件到 logs/archive/
```

配置在 run_pipeline.py 的 --quick 模式中自动执行。

---

## B29 — 广谱提取关键词太多导致噪音过高

**严重等级: 🟡 中**

**现象**: 38 关键词提取 1624 条，但住宿/文旅类仅约 88 条（~5%），大量商业综合体、写字楼物业、茶饮门店混入。

**根因**: 关键词"商业""运营""综合体"过于宽泛，匹配到大量非住宿业态。

**解决方案**:
- Phase 2 机械预筛时严格过滤 T 级（标题）和 C 级（公司名）排除词
- Phase 3 AI 筛选时逐条判断，住宿/文旅优先，餐饮/商业次之
- 每轮根据产出质量调整关键词权重

---

## B30 — Phase 5 投递脚本索引对齐 bug

**严重等级: 🟡 中**

**现象**: 投递脚本逐条 navigate 后点击"立即沟通"，但偶尔投到错误的岗位。

**根因**: 脚本按 jobId 列表逐一 navigate，但 SPA 页面异步渲染时上一个岗位的"立即沟通"按钮状态残留，导致 click 事件错位。

**解决方案**:
- 每次 navigate 后等待 8-12 秒（Vue SPA 完全渲染）
- navigate 后用 `evaluate` 验证页面标题匹配
- 投递前检查按钮是否存在且可点击

---

## B31 — B21 缓存错位导致 JD 与搜索列表不匹配

**严重等级: 🟡 中**

**现象**: Phase 4 提取的 JD 标题与 Phase 1 搜索列表标题不一致。

**根因**: Boss 直聘 SPA 连续 navigate 5 次后，Vue Router 缓存劫持，navigate 到 jobId A 但页面渲染的是上一次的 jobId B 的内容。

**解决方案**:
- phase3_jd.py 已内置：每 5 次 navigate 重置到搜索页
- B21 标记位 `_b21_low_confidence` + `_title_match_ratio` 供 Phase 5 参考
- Phase 5 判断时对 B21 岗位从严处理（JD 与标题不符的直接跳过）
- 已确认为 Vue 缓存问题，不影响投递逻辑（投递时 navigate 正确详情页）

---

## B32 — PID 锁机制

**严重等级: 🔴 高（无锁后果：僵尸进程吞噬资源）**

**现象**: `sessions_spawn` 启动的子 session 中运行 pipeline，kill 主 session 后子进程不受控继续跑，变成僵尸进程。

**根因**: OpenClaw sub-agent 进程与 pipeline Python 进程无父子关系绑定。

**解决方案**（已在 phase5_apply.py 实现）:
```python
import os, sys
PID_FILE = "boss_pipeline.pid"

def acquire_pid_lock():
    if os.path.exists(PID_FILE):
        with open(PID_FILE) as f:
            old_pid = int(f.read().strip())
        try:
            os.kill(old_pid, 0)  # 检查进程是否存在
            print(f"PID 锁被占用 (pid={old_pid})，退出")
            sys.exit(1)
        except OSError:
            os.remove(PID_FILE)  # 僵尸锁，清理
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

def release_pid_lock():
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)

# 在 main() 中使用
acquire_pid_lock()
try:
    main()
finally:
    release_pid_lock()
```

**限制**: PID 锁仅在同一机器进程级生效，无法阻止 sub-agent 层级的重复启动。

---

## 防复发规则（更新 2026-06-21）

1. **优先恢复已验证路径**：WebBridge 已验证可用时，绝不切换到未验证的工具
2. **登录态硬约束**：任何涉及投递/登录态的操作，只用 WebBridge
3. **连续 2 次工具失败立即回溯**：不再尝试第三个工具，回溯诊断
4. **关键决策写入文件**：不再依赖"记忆"，写入 MEMORY.md 和 SKILL.md
5. **排除词分三档**：T 级/标题、C 级/公司名、B 级/正文标记，不再混为一谈
6. **SPA 等待 8-12s**（Vue 渲染时间实测）
7. **B21 缓存错位标记**：Phase 4 提取后比较标题相似度，Phase 5 降级处理
8. **每 5 次 navigate 重置搜索页**：防止 Vue 缓存劫持
9. **PID 锁**：防止僵尸进程，投递脚本启动时获取锁
10. **每轮用尽候选池，不预存旧池**：避免对已过期岗位的无效投递
11. **Phase 3 逐条 AI 判断 + 用户人工筛选**：取代脚本关键词匹配，提高准确率

## B33 — FATAL_PATTERNS 未覆盖BOSS实际页面提示词

**严重等级: 🔴 高**

**现象**: Phase 5 v2投递脚本在达到每日150份上限后，仍返回"unknown"状态而非"fatal_limit"，导致连续3次unknown后误停。

**根因**: FATAL_PATTERNS列表只包含推测的提示词变体（如"今日沟通次数已达上限"），但BOSS直聘实际页面弹窗显示的文本是：
- "您已达到沟通上限"
- "您今天已与150位BOSS沟通，休息一下，明天再来吧～"

这些实际提示词不在匹配列表中。

**修复**: 在FATAL_PATTERNS中添加实际页面提示词：
`python
FATAL_PATTERNS = [
    # ... 原有推测词 ...
    "达到沟通上限",      # 实际页面提示
    "沟通上限",          # 宽匹配
    "您今天已与",        # "您今天已与150位BOSS沟通"
    "休息一下，明天再来", # 实际页面提示
    "已达今日沟通上限",
]
`

**教训**: FATAL_PATTERNS的初始值是基于推测而非实际页面观察。应该先用debug脚本捕获实际弹窗文本，再编写匹配规则。

---

## B34 — 致命错误检测顺序错误：弹窗关闭后丢失上限提示

**严重等级: 🔴 致命**

**现象**: 即使FATAL_PATTERNS包含正确提示词，脚本仍返回unknown。因为handle_greet_popup()会点击弹窗中的"确定"按钮关闭上限提示弹窗，导致后续detect_page_feedback()无法检测到上限文本。

**根因**: 原始代码流程：
`
点击"立即沟通" → handle_greet_popup()点击"确定"关闭弹窗 → detect_page_feedback()检测页面文本 → 无上限文本 → unknown
`
上限提示弹窗被handle_greet_popup关闭后，页面文本中不再包含"达到沟通上限"等关键词。

**修复**: 调整检测顺序，在处理弹窗之前先检测致命错误：
`
点击"立即沟通" → 等待2s → 读取弹窗文本检测FATAL_PATTERNS
  ├─ 触发上限 → return fatal_limit (不处理弹窗)
  ├─ 登录过期 → return login_expired (不处理弹窗)
  └─ 正常 → handle_greet_popup()发送招呼 → detect_page_feedback()检测成功
`

**代码变更**: click_chat()函数中，在handle_greet_popup()调用之前插入pre_check_text检测块。

**教训**: 任何会修改页面状态（关闭弹窗、点击按钮）的操作，必须在操作之前先读取并检测页面状态。检测→操作，不可操作→检测。

---
