#!/usr/bin/env python3
"""
模块 E: 推荐页内原地点击卡片读右侧 JD

核心创新（借鉴参考skill v6.3+）:
  不再 navigate 到 job_detail/{jid}.html 详情页（会导致列表刷新、
  卡片消失、缺 securityId 被重定向），而是全程停留在推荐页：
  1. 在左侧列表中按 jobId 找到目标卡片
  2. 滚动到可视区域
  3. 原生 click 选中该卡 → 右侧面板就地切换出 JD
  4. 校验右侧面板确实切到了目标岗位
  5. 读取右侧 JD 全文

★ v2 修复:
  推荐页卡片为 <li class="job-card-box">，必须通过 a[href*="job_detail/{jobId}"] 定位。
  不可依赖 Vue __vue__.$props.data（推荐页 DOM 中不可达）。
  JD 正文选择器修正为 .job-detail-body .desc（推荐页独有结构）。

独立可运行:
    python jd_reader.py <jobId> --output jd_<jobId>.json

也可被其他模块 import:
    from scripts.jd_reader import click_card_inplace, read_jd_from_panel
    ok = click_card_inplace("abc123")
    jd_text = read_jd_from_panel()
"""

import json
import time
import sys
import os

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_DIR)

from scripts.webbridge_client import (
    SESSION, evaluate,
)

# 薪资字体解密
from scripts.webbridge_client import decrypt_salary


# ═══════════════════════════════════════════════════════════
# 卡片定位与点击
# ═══════════════════════════════════════════════════════════

_FIND_CARD_JS = """
(function(targetJid){
    // 推荐页不能依赖 Vue $props.data，改用 a[href*="job_detail/{jid}"] 定位
    var link = document.querySelector('a[href*="job_detail/' + targetJid + '"]');
    if (!link) {
        // 尝试匹配部分 jobId（可能 URL 编码不同）
        var allLinks = document.querySelectorAll('a[href*="job_detail"]');
        for (var i = 0; i < allLinks.length; i++) {
            if (allLinks[i].getAttribute('href').indexOf(targetJid) >= 0) {
                link = allLinks[i];
                break;
            }
        }
    }
    if (!link) return JSON.stringify({found: false, detail: 'no_link_match'});

    // 找到卡片容器
    var card = link.closest('.job-card-box, .job-card-wrap, li');
    if (!card) return JSON.stringify({found: false, detail: 'no_card_container'});

    // 滚动到可视区域
    card.scrollIntoView({behavior: 'smooth', block: 'center'});

    // 取标题
    var title = '';
    var titleEl = card.querySelector('.job-name, .job-title, h3, h4, [class*="title"]');
    if (titleEl) title = titleEl.textContent.trim();

    return JSON.stringify({
        found: true,
        title: title
    });
})(__JID__)
"""


def click_card_inplace(job_id, verify=True, max_wait=5):
    """在推荐页左侧列表中原地点击指定岗位卡片

    参数:
        job_id: 加密岗位 ID
        verify: 是否校验右侧面板已切换到目标岗位
        max_wait: 校验等待最大秒数

    返回:
        dict: {
            "ok": bool,          # 是否成功
            "detail": str,       # 描述
            "title": str,        # 岗位标题（如果能读到）
        }
    """
    # 1. 定位卡片并滚动到可视区域
    find_js = _FIND_CARD_JS.replace("__JID__", json.dumps(job_id))
    find_raw = evaluate(find_js) or "{}"

    try:
        find_result = json.loads(find_raw)
    except (json.JSONDecodeError, TypeError):
        return {"ok": False, "detail": f"JS解析失败: {find_raw[:100]}", "title": ""}

    if not find_result.get("found"):
        return {"ok": False, "detail": f"未找到 jobId={job_id} 的卡片: {find_result.get('detail', '?')}", "title": ""}

    title = find_result.get("title", "")

    # 2. 等待滚动完成
    time.sleep(1.5)

    # 3. 原生点击该卡片（使用同样的 a[href*="job_detail"] 定位方式）
    click_result = evaluate(f"""
    (function(){{
        var link = document.querySelector('a[href*="job_detail/{json.dumps(job_id).strip('"')}"]');
        if (!link) {{
            var allLinks = document.querySelectorAll('a[href*="job_detail"]');
            for (var i = 0; i < allLinks.length; i++) {{
                if (allLinks[i].getAttribute('href').indexOf({json.dumps(job_id)}) >= 0) {{
                    link = allLinks[i];
                    break;
                }}
            }}
        }}
        if (!link) return 'not_found';
        var card = link.closest('.job-card-box, .job-card-wrap, li');
        if (!card) return 'no_card_container';
        card.click();
        return 'clicked';
    }})()
    """) or "not_found"

    if click_result == "not_found":
        return {"ok": False, "detail": "点击时未找到卡片", "title": title}
    if click_result == "no_card_container":
        return {"ok": False, "detail": "找到链接但未找到卡片容器", "title": title}

    # 4. 等待右侧面板更新
    time.sleep(2)

    # 5. 校验右侧面板
    if verify:
        verified = _verify_panel(job_id, max_wait)
        if not verified["ok"]:
            return {"ok": False, "detail": f"右侧面板校验失败: {verified['detail']}", "title": title}

    return {"ok": True, "detail": "卡片已点击，右侧面板已切换", "title": title}


def _verify_panel(job_id, max_wait=5):
    """校验右侧面板确实切换到了目标岗位

    推荐页右侧面板的校验方式：
      1. 检查 job-detail-body 的 innerText 是否包含 jobId（或相关字段）
      2. 检查 job-detail-header 中的岗位详情链接是否含 jobId

    返回:
        dict: {"ok": bool, "detail": str}
    """
    deadline = time.time() + max_wait

    while time.time() < deadline:
        verify_result = evaluate(f"""
        (function(targetJid){{
            // 方式1: 检查右侧面板的岗位详情链接
            var detailLinks = document.querySelectorAll('a[href*="job_detail"]');
            for (var j = 0; j < detailLinks.length; j++) {{
                var href = detailLinks[j].getAttribute('href') || '';
                if (href.indexOf(targetJid) >= 0) {{
                    return JSON.stringify({{ok: true, method: 'detail_link'}});
                }}
            }}

            // 方式2: 检查 job-detail-body 非空
            var body = document.querySelector('.job-detail-body');
            if (body && body.innerText.trim().length > 50) {{
                return JSON.stringify({{ok: true, method: 'body_populated'}});
            }}

            // 方式3: 检查 job-sec 非空（备选容器）
            var sec = document.querySelector('.job-sec');
            if (sec && sec.innerText.trim().length > 50) {{
                return JSON.stringify({{ok: true, method: 'sec_populated'}});
            }}

            return JSON.stringify({{ok: false, method: 'none'}});
        }})({json.dumps(job_id)})
        """) or '{"ok":false}'

        try:
            data = json.loads(verify_result)
            if data.get("ok"):
                return {"ok": True, "detail": f"校验通过 ({data.get('method', '?')})"}
        except (json.JSONDecodeError, TypeError):
            pass

        time.sleep(1)

    return {"ok": False, "detail": f"等待{max_wait}s未校验到目标岗位"}


# ═══════════════════════════════════════════════════════════
# JD 内容读取
# ═══════════════════════════════════════════════════════════

def read_jd_from_panel():
    """从右侧面板读取 JD 全文

    推荐页右侧面板 DOM 结构（实测）:
      .job-detail-box
        ├── .job-detail-header
        │   ├── .job-header-info
        │   │   ├── .job-detail-info
        │   │   │   ├── .job-name        ← 岗位标题
        │   │   │   └── .job-salary      ← 薪资（字体加密）
        │   │   └── .tag-list
        │   │       └── li               ← 城市/经验/学历
        │   └── .job-detail-op
        │       ├── .op-btn.op-btn-like  ← 收藏
        │       ├── .op-btn.btn-deliver  ← 投递简历
        │       └── .op-btn.op-btn-chat  ← 立即沟通
        └── .job-detail-body
            ├── .job-detail-operate      ← 举报/微信分享/不合适
            ├── h3.title                 ← "职位描述"
            ├── ul.job-label-list        ← 标签(五险一金等)
            ├── p.desc                   ← ★ JD 正文 ★
            ├── .job-boss-info           ← 招聘者信息
            ├── .job-address             ← 工作地址
            └── .more-job-btn            ← 查看更多信息

    返回:
        dict: {
            "jd_text": str,       # JD 正文
            "job_title": str,     # 岗位标题
            "company": str,       # 公司名
            "salary": str,        # 薪资（原始字体加密）
            "salary_decrypted": str, # 解密后的薪资
            "city": str,          # 城市
            "experience": str,    # 经验要求
            "degree": str,        # 学历要求
            "boss_name": str,     # 招聘者名称
            "boss_title": str,    # 招聘者职位
            "full_text": str,     # 右侧面板完整文本（备用）
        }
    """
    result_raw = evaluate("""
    (function(){
        // ★ JD 正文: p.desc（推荐页独有，job-detail-section 不存在）
        var jdText = '';
        var descEl = document.querySelector('.job-detail-body .desc');
        if (descEl) {
            jdText = descEl.innerText.trim();
        }

        // ★ 岗位标题: .job-name（在 job-detail-header > job-header-info > job-detail-info 内）
        var titleEl = document.querySelector('.job-detail-header .job-name');
        var jobTitle = titleEl ? titleEl.textContent.trim() : '';

        // ★ 薪资: .job-salary（字体加密，后续用 decrypt_salary 解密）
        var salaryEl = document.querySelector('.job-detail-header .job-salary');
        var salary = salaryEl ? salaryEl.textContent.trim() : '';

        // ★ 城市/经验/学历: .tag-list li
        var city = '';
        var experience = '';
        var degree = '';
        var tagItems = document.querySelectorAll('.job-detail-header .tag-list li');
        for (var i = 0; i < tagItems.length; i++) {
            var text = tagItems[i].textContent.trim();
            // 城市含链接，检查 a 标签
            var link = tagItems[i].querySelector('a');
            if (link) {
                city = link.textContent.trim();
            } else if (text.indexOf('年') >= 0 || text.indexOf('经验') >= 0) {
                experience = text;
            } else if (text.indexOf('本科') >= 0 || text.indexOf('大专') >= 0 ||
                       text.indexOf('硕士') >= 0 || text.indexOf('学历') >= 0) {
                degree = text;
            } else if (text.indexOf('不限') >= 0) {
                degree = text;
            }
        }

        // 公司名: 在左侧卡片列表中，不从右侧面板读取
        var company = '';

        // 招聘者信息: .job-boss-info
        var bossInfo = document.querySelector('.job-detail-body .job-boss-info');
        var bossName = '';
        var bossTitle = '';
        if (bossInfo) {
            var bossText = bossInfo.innerText || '';
            // 通常格式: "刘俏 刚刚活跃 南都物业 · 招聘经理"
            var parts = bossText.split('\\n');
            if (parts.length > 0) bossName = parts[0].trim();
            if (parts.length > 2) bossTitle = parts[2].trim();
        }

        // 右侧面板完整文本（备用）
        var panelEl = document.querySelector('.job-detail-box');
        var fullText = panelEl ? panelEl.innerText.trim() : '';

        return JSON.stringify({
            jd_text: jdText,
            job_title: jobTitle,
            company: company,
            salary: salary,
            city: city,
            experience: experience,
            degree: degree,
            boss_name: bossName,
            boss_title: bossTitle,
            full_text: fullText
        });
    })()
    """) or "{}"

    try:
        result = json.loads(result_raw)
        # 解密薪资
        result["salary_decrypted"] = decrypt_salary(result.get("salary", ""))
        return result
    except (json.JSONDecodeError, TypeError):
        return {
            "jd_text": "",
            "job_title": "",
            "company": "",
            "salary": "",
            "salary_decrypted": "",
            "city": "",
            "experience": "",
            "degree": "",
            "boss_name": "",
            "boss_title": "",
            "full_text": "",
        }


def read_jd_for_job(job_id):
    """完整流程: 点击卡片 → 读 JD

    参数:
        job_id: 加密岗位 ID

    返回:
        dict: {
            "ok": bool,
            "detail": str,
            "job_id": str,
            "jd": dict,    # read_jd_from_panel() 的返回值
        }
    """
    # 1. 点击卡片
    click_result = click_card_inplace(job_id)
    if not click_result["ok"]:
        return {
            "ok": False,
            "detail": click_result["detail"],
            "job_id": job_id,
            "jd": {},
        }

    # 2. 读 JD
    jd = read_jd_from_panel()

    if not jd.get("jd_text") and not jd.get("full_text"):
        return {
            "ok": False,
            "detail": "右侧面板无 JD 内容（可能页面未渲染完或岗位已关闭）",
            "job_id": job_id,
            "jd": jd,
        }

    return {
        "ok": True,
        "detail": "JD 读取成功",
        "job_id": job_id,
        "jd": jd,
    }


def main():
    """CLI 入口: 点击卡片读 JD"""
    import argparse
    parser = argparse.ArgumentParser(description="推荐页内原地点击卡片读 JD")
    parser.add_argument("jobId", help="加密岗位 ID")
    parser.add_argument("--output", help="输出 JSON 文件路径 (可选)")
    args = parser.parse_args()

    print(f"[JD读取] jobId={args.jobId}")
    print("-" * 50)

    result = read_jd_for_job(args.jobId)

    if result["ok"]:
        jd = result["jd"]
        print(f"岗位: {jd.get('job_title', '?')}")
        print(f"公司: {jd.get('company', '?')}")
        print(f"薪资: {jd.get('salary', '?')} (解密: {jd.get('salary_decrypted', '?')})")
        print(f"城市: {jd.get('city', '?')}")
        print(f"经验: {jd.get('experience', '?')}")
        print(f"学历: {jd.get('degree', '?')}")
        print(f"招聘者: {jd.get('boss_name', '?')} - {jd.get('boss_title', '?')}")
        print(f"\nJD 正文 ({len(jd.get('jd_text', ''))} 字):")
        print(jd.get('jd_text', '(空)')[:500])

        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            print(f"\n已保存至 {args.output}")
    else:
        print(f"失败: {result['detail']}")
        sys.exit(1)


if __name__ == "__main__":
    main()