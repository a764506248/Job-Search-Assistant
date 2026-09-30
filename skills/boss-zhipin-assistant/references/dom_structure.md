# Boss 直聘 DOM 实测结构（2026-06-13 验证）

## ⚠️ 核心教训

Boss 直聘 DOM 命名有误导性，**必须先探测再写选择器**：

```javascript
// 先看实际 HTML
const card = document.querySelector(".job-card-wrap");
return card.innerHTML.substring(0, 3000);
```

---

## 列表页岗位卡片

```html
<li class="job-card-box">
  <div class="job-info">
    <div class="job-title clearfix">
      <a href="/job_detail/xxx.html" class="job-name">产品内容策划</a>
      <span class="job-salary"><!-- 薪资字体加密 --></span>
    </div>
    <ul class="tag-list">
      <li>1-3年</li>
      <li>本科</li>
    </ul>
  </div>
  <div class="job-card-footer">
    <a href="/gongsi/xxx.html" class="boss-info">
      <div class="boss-logo"><img src="..."></div>
      <span class="boss-name">骏辉食品</span>  <!-- ← 公司名在这！ -->
    </a>
    <span class="company-location">杭州·滨江区·长河</span>  <!-- ← 地区在这！ -->
  </div>
</li>
```

## 选择器对照表（⚠️ 已验证，勿盲改）

### 列表页

| 数据 | ❌ 错误选择器 | ✅ 正确选择器 | 说明 |
|------|-------------|-------------|------|
| 岗位卡片 | `li[class*="job-card"]` | `.job-card-wrap li.job-card-box` | 列表项 |
| 岗位标题 | `h3`, `.job-title` | `.job-name`（a 标签） | 同时含 href |
| 薪资 | `[class*="salary"]` | `.job-salary` | 字体加密，需解密 |
| 公司名 | `.company-name` | **`.boss-name`** | ⚠️ 最容易猜错！ |
| 工作地区 | `.job-area` | **`.company-location`** | 不是 `.job-area`！ |
| 经验/学历 | `.tag-list li` | `.tag-list li` | 这个倒是对的 |
| 详情链接 | `a[href*="job_detail"]` | `.job-name`（即标题 a 标签） | href 格式 `/job_detail/{jobId}.html` |

### 详情页

| 数据 | 选择器 | 备注 |
|------|--------|------|
| 岗位标题 | `h1`, `.name` | 详情页比列表页更准 |
| 薪资 | `.salary` | 字体加密，同理解密 |
| 公司名 | `.company-name a`, `.name-wrap a` | 详情页反而有 `.company-name` |
| JD 正文 | `.job-sec-text` | 首选 |
| JD 正文 fallback | `[class*="job-sec"]` | 二选 |
| JD 正文 fallback 2 | `document.body.innerText` 找 "职位描述" | 三选 |

---

## 提取 JS（Phase 1 使用）

```javascript
(() => {
    let jobs = [], seen = new Set();
    let items = document.querySelectorAll('.search-job-result li, .job-list-box li, [class*="search-job"] li');
    if (items.length === 0) items = document.querySelectorAll('ul li[class]');

    for (let item of items) {
        let titleLink = item.querySelector('a[href*="job_detail"]');
        if (!titleLink) continue;
        let title = titleLink.innerText.trim().split('\n')[0];
        let href = titleLink.getAttribute('href');
        let jobId = (href.match(/\/job_detail\/([^.?]+)/) || [])[1] || '';
        let salary = (item.querySelector('.salary, [class*="salary"]') || {}).innerText?.trim() || '';
        let company = (item.querySelector('.boss-name') || {}).innerText?.trim() || '';
        let location = (item.querySelector('.company-location') || {}).innerText?.trim() || '';
        let tagEls = item.querySelectorAll('.tag-list li, [class*="tag-list"] li');
        let tags = []; for (let t of tagEls) { let txt = t.innerText.trim(); if (txt) tags.push(txt); }
        if (title && jobId && !seen.has(jobId)) {
            seen.add(jobId);
            jobs.push({title, salary, company, location, tags, href, jobId});
        }
    }
    return JSON.stringify(jobs);
})()
```

---

## 投递按钮定位（Phase 5 使用）

**方法 1（推荐）：snapshot @e ref**
- `snapshot` → 搜索"立即沟通"对应 `@e` 编号 → `click({selector: "@eXX"})`
- 实测 `@e18` 通常对应"立即沟通"

**方法 2（fallback）：CSS 选择器**
- `click({selector: ".btn-startchat"})`
- 或 JS 遍历 `a.op-btn` / `button.op-btn` 中含"立即沟通"的元素

---

## snapshot vs evaluate 使用场景

| 场景 | snapshot | evaluate |
|------|---------|---------|
| 读列表页内容 | ❌ 可能空树 | ✅ `document.body.innerText` |
| 读详情页内容 | ⚠️ 偶尔不完整 | ✅ 完整可靠 |
| 定位投递按钮 | ✅ `@e` ref 更稳定 | ⚠️ 需写 JS 遍历 |
| 提取结构化数据 | ❌ | ✅ JS 返回 JSON |
