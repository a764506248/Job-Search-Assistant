# Boss 直聘运营手册

## 日常操作速查

### 启动检查（每次必做）

```python
from scripts.webbridge_client import WebBridge

# 用当天日期作为 session 名
from datetime import datetime
session_name = "boss-" + datetime.now().strftime("%m%d")

wb = WebBridge(session=session_name)

# ensure_active_tab 一站式搞定：连通性检查 + 标签页 + evaluate 验证
assert wb.ensure_active_tab(timeout_wait=10), "WebBridge 不可用"

# 登录态验证（含 SPA 渲染等待）
assert wb.verify_login("王浩"), "Boss直聘未登录"
```

> **2026-06-15 更新：** 使用 `ensure_active_tab()` 替代手动 health_check → navigate → evaluate 三步。
> 不再依赖特定 session 名称（见 B19/SKILL.md 更新）

### 完整一轮投递（2026-06-15 更新）

```
Phase 1: python3 scripts/phase1_extract.py              # ~2分钟
Phase 2: AI 粗筛（读 phase1_raw → 排除 → 保存 filtered） # ~5分钟
Phase 3: python3 scripts/phase3_jd.py candidates.json 5  # ~3分钟/5岗（含每5次重置）
Phase 4: AI 精筛（读 JD → 判断 → 保存 approved）         # ~5分钟
Phase 5: python3 scripts/phase5_apply.py approved.json   # ~45秒/岗（含12s等待）
```

### Phase 3 注意点

```python
# 每 5 次导航后重置到搜索页（防 CDP 缓存 B21）
navigate(SEARCH_PAGE, wait_range=(3, 5))
```

### Phase 5 注意点

```python
# SPA 渲染等待 8-12s（不是 5-8s）
navigate(url, wait_range=(8, 12))

# body 为空时等 5s 重试一次
body = body_with_retry()
```

### 懒加载滚动操作（Phase 1 关键步骤）

空搜索和关键词搜索使用**相同的懒加载机制**。

```python
# 导航到空搜索页（或关键词搜索页）
wb.navigate("https://www.zhipin.com/web/geek/job?city=101210100", wait=8)

# 循环滚动直到卡片数达标
import time
while True:
    raw = wb.evaluate("document.querySelectorAll('a[href*=\"job_detail\"]').length")
    cards = int(raw)
    if cards >= 100:
        break
    wb.evaluate('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(3.5)
```

**关键参数：**
- 每次 `scrollTo` 后必须等 **3-4 秒**（2 秒不够）
- 不要限制滚动次数，上限约 450 条（30 轮）
- 如果 card count 没有增长 → 继续滚动，不要过早放弃

### 常见故障处理

| 故障 | 症状 | 修复 |
|------|------|------|
| WebBridge 未运行 | 端口 10086 无监听 | `Start-Process kimi-webbridge -Arg "start"` |
| Session 无标签页 | evaluate("1+1") → "" (空) | 先 `navigate()` 建立 session |
| 扩展未连接 | extension_connected=false | 重启 Chrome |
| 未登录 | 页面无"王浩" | 用户手动登录 Chrome Boss 直聘 |
| 提取数据为空 | company/location 全空 | 选择器可能变化，先 innerHTML 探测 |
| 薪资乱码 | `\ue036` 等 | decrypt_salary() 自动处理 |
| 投递失败 | "立即沟通"未点击成 | 优先用 snapshot @e ref |

### DOM 选择器速查（已验证）

```javascript
// 列表页
.job-name           // 岗位标题（<a> 标签，含 href）
.salary             // 薪资（字体加密）
.boss-name          // 公司名 —— 不是 .company-name！
.company-location   // 工作地区 —— 不是 .job-area！
.tag-list li        // 经验/学历标签

// 详情页
h1 / .name          // 岗位标题
.salary             // 薪资（字体加密）
.company-name a     // 公司名（详情页有 .company-name）
.job-sec-text       // JD 正文
```
