#!/usr/bin/env python3
"""
模块 F: 投递执行引擎（推荐页/搜索页内原地投递 + 智能页面反馈监测）

★ v5.0 新增:
  - check_delivery_target() — 流程图"总投递数量是否满足要求"节点
  - DAILY_TARGET 常量 — 每日投递目标（默认150）

核心创新（融合参考skill v6.3+ 和本机 v2 反馈检测）:
  1. 全程停留在当前页面（推荐页/搜索页），不 navigate 到 job_detail URL
  2. 在右侧面板点击「立即沟通」-> 处理原地弹窗 -> 点「留在此页」
  3. 保留 v2 智能反馈检测: FATAL_PATTERNS + _check_fatal_patterns
  4. 致命错误优先检测: 在处理弹窗之前检测上限提示
  5. 连续 3 次未知状态 -> 熔断暂停

★ v4.2 修复:
  1. 点击 .op-btn-chat 前先 scrollIntoView 确保按钮在视口内
  2. 每步操作后立即检测状态
  3. 正确处理原地弹窗
  4. 成功判断基于累计证据
  5. ProgressManager API 修正

独立可运行:
    python deliver_engine.py jobs_to_deliver.json --progress stream_progress.json --max 50

也可被其他模块 import:
    from scripts.deliver_engine import deliver_inplace, check_delivery_target
"""

import json
import time
import random
import re
import sys
import os

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_DIR)

from scripts.profile_loader import WORK_DIR, DAILY_TARGET, GREETING_TEXT, SEND_RESUME_IMAGE
from scripts.local_service_client import download_default_resume_image

from scripts.webbridge_client import (
    SESSION, api, evaluate, navigate, handle_popup,
    ensure_active_tab, health_check,
    ProgressManager, register_signal_guard, SafeInterrupt,
)
from scripts.jd_reader import click_card_inplace

# ═══════════════════════════════════════════════════════════
# ★ v5.0 投递目标常量 — 从 user_profile.json 读取 (profile_loader 导入)
# ═══════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════
# 页面反馈检测常量 (从 v2 迁移)
# ═══════════════════════════════════════════════════════════

FATAL_PATTERNS = [
    "今日沟通次数已达上限",
    "今日沟通已达上限",
    "今日已达上限",
    "沟通次数已达上限",
    "今日投递已达上限",
    "每天最多沟通",
    "今日沟通额度已用完",
    "达到沟通上限",
    "沟通上限",
    "您今天已与",
    "休息一下，明天再来",
    "已达今日沟通上限",
]

LOGIN_PATTERNS = [
    "请先登录",
    "登录已过期",
    "扫码登录",
    "BOSS直聘登录",
    "安全验证",
]

SKIP_PATTERNS = [
    "已经沟通过",
    "已沟通过该职位",
    "职位已关闭",
    "职位不存在",
    "职位已下线",
    "该职位已失效",
]

MAX_CONSECUTIVE_UNKNOWN = 3


# ═══════════════════════════════════════════════════════════
# ★ v5.0 投递目标检查 — 流程图"总投递数量是否满足要求"节点
# ═══════════════════════════════════════════════════════════

def check_delivery_target(progress_file=None):
    """★ 流程图节点: 总投递数量是否满足要求

    读取投递进度文件，判断成功投递总数是否达到 DAILY_TARGET。

    参数:
        progress_file: 进度文件路径（默认使用工作目录下的 stream_progress.json）

    返回:
        dict: {
            "target_met": bool,       # 是否达标
            "delivered_count": int,   # 已投递成功数
            "target": int,            # 目标数
            "remaining": int,         # 还差多少
        }
    """
    if progress_file is None:
        progress_file = os.path.join(WORK_DIR, "stream_progress.json")

    pm = ProgressManager(progress_file)
    pm.load()

    delivered_count = getattr(pm, 'delivered_count', 0) or len(getattr(pm, 'delivered', []))
    target_met = delivered_count >= DAILY_TARGET
    remaining = max(0, DAILY_TARGET - delivered_count)

    result = {
        "target_met": target_met,
        "delivered_count": delivered_count,
        "target": DAILY_TARGET,
        "remaining": remaining,
    }

    print(f"[目标] 已投递 {delivered_count}/{DAILY_TARGET}" +
          (f" ★ 已达标！" if target_met else f" (还差 {remaining})"))

    return result


# ═══════════════════════════════════════════════════════════
# 弹窗处理
# ═══════════════════════════════════════════════════════════

def handle_greet_popup(greeting_text=None):
    """处理打招呼弹窗，点击"发送"按钮完成投递

    BOSS直聘点击"立即沟通"后原地弹出打招呼确认框，
    需要点击"发送"按钮发送招呼语。

    返回:
        'sent:xxx' | 'no_popup'
    """
    encoded_greeting = json.dumps(str(greeting_text or '').strip(), ensure_ascii=False)
    popup_script = """
    (function(){
        var greeting = __GREETING__;
        var dialogSelectors = '.dialog-wrap, .greet-pop, .dialog-container, .layer-dialog, .modal, .ant-modal-wrap, .layer-ext';
        var dialogs = document.querySelectorAll(dialogSelectors);
        for (var i = 0; i < dialogs.length; i++) {
            var d = dialogs[i];
            var rect = d.getBoundingClientRect();
            var style = window.getComputedStyle(d);
            if (rect.width > 0 && rect.height > 0 && style.display !== 'none') {
                if (greeting) {
                    var input = d.querySelector('textarea, input[type="text"], [contenteditable="true"]');
                    if (!input) return 'custom_input_not_found';
                    input.focus();
                    if (input.isContentEditable) input.textContent = greeting;
                    else input.value = greeting;
                    input.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:greeting}));
                    var actual = input.isContentEditable ? input.textContent : input.value;
                    if ((actual || '').trim() !== greeting) return 'custom_input_failed';
                }
                var btns = d.querySelectorAll('a, button, .btn, .dialog-btn, span.btn');
                for (var j = 0; j < btns.length; j++) {
                    var text = btns[j].textContent.trim();
                    if (text === '发送' || text === '确定' || text === '发送招呼' || text === '好' || text === '发送消息') {
                        btns[j].click();
                        return 'sent:' + text;
                    }
                }
            }
        }

        if (greeting) return 'no_popup';
        var allBtns = document.querySelectorAll('a, button, .btn, .dialog-btn, .btn-sure, .layer-btn-confirm');
        for (var k = 0; k < allBtns.length; k++) {
            var el = allBtns[k];
            var text = el.textContent.trim();
            if (text === '发送' || text === '发送招呼' || text === '发送消息') {
                var rect = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                if (rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden') {
                    el.click();
                    return 'sent:fallback_' + text;
                }
            }
        }

        var sureBtn = document.querySelector('.btn-sure');
        if (sureBtn) {
            var rect = sureBtn.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) {
                sureBtn.click();
                return 'sent:btn-sure';
            }
        }

        return 'no_popup';
    })()
    """
    popup_result = evaluate(popup_script.replace('__GREETING__', encoded_greeting))
    return popup_result if popup_result else 'no_popup'


def click_stay_on_page():
    """点击"留在此页"按钮

    投递成功后 BOSS 原地弹出确认弹窗，含"留在此页"和"继续沟通"两个按钮。
    必须点"留在此页"（留在当前页面），绝不点"继续沟通"（会跳转聊天页）。

    返回:
        'clicked:留在此页' | 'not_found'
    """
    result = evaluate("""
    (function(){
        var btns = document.querySelectorAll('button, a');
        for (var i = 0; i < btns.length; i++) {
            var el = btns[i];
            var text = (el.textContent || '').trim();
            if (text === '留在此页') {
                var rect = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                if (rect.width > 0 && rect.height > 0 && style.display !== 'none') {
                    el.click();
                    return 'clicked:留在此页';
                }
            }
        }
        return 'not_found';
    })()
    """)
    return result or 'not_found'


# ═══════════════════════════════════════════════════════════
# 状态检测辅助函数
# ═══════════════════════════════════════════════════════════

def _check_fatal_patterns():
    """检测页面是否有致命错误/登录过期/跳过模式

    返回:
        (status, detail): 匹配到模式时返回对应 status，无匹配返回 (None, '')
    """
    page_text = evaluate("""
    (function(){
        var texts = [];
        texts.push(document.body.innerText || '');
        var dialogs = document.querySelectorAll(
            '.dialog-wrap, .dialog-container, .greet-pop, .layer-dialog, ' +
            '.modal, .toast, .message, .ant-message, .ant-modal, ' +
            '.dialog-body, .dialog-content, .pop-content, .tips-content'
        );
        for (var i = 0; i < dialogs.length; i++) {
            var d = dialogs[i];
            var rect = d.getBoundingClientRect();
            var style = window.getComputedStyle(d);
            if (rect.width > 0 && rect.height > 0 && style.display !== 'none') {
                texts.push(d.innerText || '');
            }
        }
        return texts.join('\\n').substring(0, 3000);
    })()
    """) or ""

    current_url = evaluate("window.location.href") or ""
    if "login" in current_url or "passport" in current_url:
        return 'login_expired', f"页面跳转登录: {current_url[:80]}"

    for pattern in FATAL_PATTERNS:
        if pattern in page_text:
            return 'fatal_limit', f"触发每日上限: {pattern}"

    for pattern in LOGIN_PATTERNS:
        if pattern in page_text:
            return 'login_expired', f"登录过期: {pattern}"

    for pattern in SKIP_PATTERNS:
        if pattern in page_text:
            return 'skip', f"跳过: {pattern}"

    return None, ''


def _get_chat_button_text():
    """获取当前沟通按钮的文字"""
    return evaluate("""
    (function(){
        var btn = document.querySelector('.op-btn-chat, .btn-startchat, .job-chat-btn');
        return btn ? btn.textContent.trim() : '';
    })()
    """) or ""


def _visible_message_count(text):
    """统计右侧当前会话中可见的完全相同消息，排除左侧联系人摘要。"""
    encoded = json.dumps(text, ensure_ascii=False)
    return int(evaluate(f"""
    (function(){{
        var expected = {encoded};
        var nodes = Array.from(document.querySelectorAll('*'));
        return nodes.filter(function(el){{
            if (el.children.length !== 0 || (el.textContent || '').trim() !== expected) return false;
            var r = el.getBoundingClientRect();
            var s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && r.left > window.innerWidth * 0.28 &&
                   s.display !== 'none' && s.visibility !== 'hidden';
        }}).length;
    }})()
    """) or 0)


def _restore_source_page(source_url):
    """从聊天页恢复到本次投递前的搜索列表。

    只允许返回 BOSS 岗位列表 URL，避免将页面导航到未验证的外部地址。
    """
    source_url = str(source_url or '').strip()
    if '/web/geek/jobs' not in source_url:
        return False, '投递前页面不是可恢复的岗位列表'
    result = navigate(source_url, wait_range=(3, 5))
    if not result.get('ok'):
        return False, '返回搜索页的导航请求失败'
    restored_url = str(evaluate('window.location.href') or '')
    if '/web/geek/jobs' not in restored_url:
        return False, f'返回后仍不在搜索页: {restored_url}'
    return True, '已返回搜索页'


def _normalize_company_name(value):
    """将工商全称和 BOSS 聊天页品牌简称归一化。"""
    value = re.sub(r'[\(（].*?[\)）]', '', str(value or ''))
    value = re.sub(r'(?:北京|上海|广州|深圳|杭州)(?:市)?', '', value)
    value = re.sub(r'(?:股份)?有限公司|有限责任公司|集团|科技|网络', '', value)
    return re.sub(r'[^\w\u4e00-\u9fff]', '', value).lower()


def _company_names_match(expected, candidate):
    expected = _normalize_company_name(expected)
    candidate = _normalize_company_name(candidate)
    if not expected or not candidate:
        return False
    if expected == candidate:
        return True
    return min(len(expected), len(candidate)) >= 4 and (
        expected in candidate or candidate in expected
    )


def _send_verified_greeting(job_info, greeting_text=None):
    """仅在当前聊天明确对应目标岗位时，发送且只发送一次问候语。"""
    job_info = job_info or {}
    title = str(job_info.get('title') or '').strip()
    company = str(job_info.get('company') or '').strip()
    if not title or not company:
        return False, '缺少岗位标题或公司，拒绝发送问候语'

    expected_title = json.dumps(title, ensure_ascii=False)
    expected_company = json.dumps(company, ensure_ascii=False)
    identity = evaluate(f"""
    (function(){{
        var title = {expected_title};
        var company = {expected_company};
        var visibleLeaves = function() {{
            return Array.from(document.querySelectorAll('*')).filter(function(el) {{
                if (el.children.length !== 0) return false;
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && r.left > window.innerWidth * 0.28 &&
                       s.display !== 'none' && s.visibility !== 'hidden';
            }});
        }};
        var leaves = visibleLeaves();
        var visibleExact = function(text) {{
            return leaves.some(function(el) {{ return (el.textContent || '').trim() === text; }});
        }};
        return {{
            url: location.href,
            titleOk: visibleExact(title),
            visibleTexts: leaves.map(function(el) {{ return (el.textContent || '').trim(); }})
        }};
    }})()
    """) or {}
    company_match = next(
        (
            candidate for candidate in identity.get('visibleTexts', [])
            if _company_names_match(company, candidate)
        ),
        '',
    )
    identity['companyOk'] = bool(company_match)
    identity['companyMatch'] = company_match
    if '/web/geek/chat' not in str(identity.get('url', '')):
        return False, '尚未进入聊天页，无法安全发送问候语'
    if not identity.get('titleOk') or not identity.get('companyOk'):
        return False, (
            f"目标会话校验失败: title={identity.get('titleOk')}, "
            f"company={identity.get('companyOk')}, matched={identity.get('companyMatch', '')}"
        )

    greeting = str(greeting_text or GREETING_TEXT or '').strip()
    if not greeting:
        greeting = str(evaluate("""
        (function(){
            var panel = document.querySelector('.sentence-panel');
            if (!panel) {
                var trigger = document.querySelector('[aria-label="常用语"]');
                if (trigger) trigger.click();
                panel = document.querySelector('.sentence-panel');
            }
            var first = panel && panel.querySelector('li');
            return first ? first.textContent.trim() : '';
        })()
        """) or '').strip()
    if not greeting:
        return False, '未配置 greeting_text，且无法读取第一条常用语'

    before = _visible_message_count(greeting)
    if before > 0:
        return True, '问候语已存在，跳过重复发送'

    encoded_greeting = json.dumps(greeting, ensure_ascii=False)
    filled = evaluate(f"""
    (function(){{
        var input = document.querySelector('#chat-input[contenteditable="true"]');
        if (!input) return false;
        input.focus();
        input.textContent = {encoded_greeting};
        input.dispatchEvent(new InputEvent('input', {{bubbles:true, inputType:'insertText', data:{encoded_greeting}}}));
        return (input.innerText || input.textContent || '').trim() === {encoded_greeting};
    }})()
    """)
    if not filled:
        return False, '问候语写入输入框失败'

    sent = evaluate("""
    (function(){
        var buttons = Array.from(document.querySelectorAll('button'));
        var btn = buttons.find(function(el){ return (el.textContent || '').trim() === '发送'; });
        if (!btn || btn.disabled) return false;
        btn.click();
        return true;
    })()
    """)
    if not sent:
        return False, '发送按钮不可用'

    time.sleep(1.5)
    after = _visible_message_count(greeting)
    if after <= before:
        return False, '点击发送后未观察到问候语送达'
    return True, '问候语已发送并在目标会话中验证'


def _send_default_resume_image(enabled=None):
    """发送用户明确启用且在简历库中选中的默认简历首页图。"""
    if enabled is None:
        enabled = SEND_RESUME_IMAGE
    if not enabled:
        return True, '简历图片发送未启用'

    image_path, detail = download_default_resume_image()
    if not image_path:
        return False, detail
    try:
        prepared = evaluate("""
        (function(){
            var inputs = Array.from(document.querySelectorAll('input[type="file"]'));
            var candidates = inputs.filter(function(el){
                var accept = (el.getAttribute('accept') || '').toLowerCase();
                return accept.indexOf('image') >= 0 || accept.indexOf('.png') >= 0;
            });
            var target = candidates.find(function(el){
                return !!el.closest('.chat-input, .chat-editor, .chat-operate, .chat-conversation, .conversation');
            }) || candidates[0];
            if (!target) return {ok:false, count:inputs.length};
            target.id = 'jsa-default-resume-image-input';
            return {ok:true, accept:target.getAttribute('accept') || ''};
        })()
        """) or {}
        if not prepared.get('ok'):
            return False, f"聊天区未找到图片上传控件（文件控件 {prepared.get('count', 0)} 个）"

        result = api("upload", {
            "selector": "#jsa-default-resume-image-input",
            "files": [image_path],
        })
        if not result.get("success"):
            return False, f"简历图片写入上传控件失败: {result}"

        time.sleep(1.5)
        confirmation = evaluate("""
        (function(){
            var visible = function(el){
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
            };
            var dialogs = Array.from(document.querySelectorAll(
                '.dialog-wrap, .dialog-container, .modal, .ant-modal-wrap, .image-preview, .upload-preview'
            )).filter(visible);
            for (var i = 0; i < dialogs.length; i++) {
                var button = Array.from(dialogs[i].querySelectorAll('button, a')).find(function(el){
                    var text = (el.textContent || '').trim();
                    return visible(el) && !el.disabled && (text === '发送' || text === '确定');
                });
                if (button) { button.click(); return 'clicked:' + (button.textContent || '').trim(); }
            }
            return 'auto';
        })()
        """) or 'auto'
        time.sleep(2)
        return True, f"默认简历图片已提交（{confirmation}）"
    finally:
        try:
            os.unlink(image_path)
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════
# 核心投递逻辑
# ═══════════════════════════════════════════════════════════

def deliver_inplace(job_id, job_info=None, greeting_text=None, send_resume_image=None):
    """当前页面内原地投递单个岗位

    流程:
      1. 点击卡片（右侧面板就地切 JD）
      2. scrollIntoView + 点击「立即沟通」(.op-btn-chat)
      3. 等2s -> 立即检测致命错误
      4. 处理打招呼弹窗（点击"发送"）
      5. 等1s -> 点击「留在此页」
      6. 等1s -> 检测最终状态
      7. 根据累计证据返回 status

    参数:
        job_id: 加密岗位 ID
        job_info: 可选的岗位信息 dict

    返回:
        (status, detail)
        status: 'success' | 'fatal_limit' | 'login_expired' | 'skip' | 'fail' | 'unknown'
    """
    title = (job_info or {}).get('title', '')[:25] if job_info else job_id
    source_url = str(evaluate('window.location.href') or '')

    # 1. 点击卡片
    click_result = click_card_inplace(job_id, verify=True, max_wait=5)
    if not click_result["ok"]:
        return 'fail', f"卡片定位失败: {click_result['detail']}"

    time.sleep(1)

    # 2. scrollIntoView + 点击
    scroll_result = evaluate("""
    (function(){
        var btn = document.querySelector('.op-btn-chat');
        if (!btn) btn = document.querySelector('.btn-startchat, .job-chat-btn');
        if (!btn) return 'not_found';
        var text = btn.textContent.trim();
        if (text.indexOf('继续沟通') >= 0) return 'already:' + text;
        btn.scrollIntoView({block: 'center'});
        return 'scrolled:' + text;
    })()
    """)

    if scroll_result.startswith('already:'):
        return 'skip', f'已沟通过: {scroll_result}'

    if scroll_result == 'not_found':
        body_text = evaluate("document.body.innerText") or ""
        if any(p in body_text for p in ['职位已关闭', '职位不存在', '已下线']):
            return 'skip', '职位已关闭/下线'
        return 'fail', '沟通按钮未找到'

    time.sleep(0.5)

    click_result = evaluate("""
    (function(){
        var btn = document.querySelector('.op-btn-chat');
        if (!btn) btn = document.querySelector('.btn-startchat, .job-chat-btn');
        if (!btn) return 'not_found';
        btn.click();
        return 'clicked';
    })()
    """)

    if click_result == 'not_found':
        return 'fail', '点击时按钮消失'

    # 3. 等待弹窗 → 检测致命错误
    time.sleep(2)
    fatal_status, fatal_detail = _check_fatal_patterns()
    if fatal_status:
        return fatal_status, fatal_detail

    # 新版 BOSS 可能不弹打招呼框，而是直接跳转聊天页。此时必须先锁定
    # 目标公司和岗位，再做去重并发送常用语；任何身份不一致都停止。
    current_url = str(evaluate("window.location.href") or '')
    if '/web/geek/chat' in current_url:
        time.sleep(1)
        greeting_ok, greeting_detail = _send_verified_greeting(job_info, greeting_text)
        if not greeting_ok:
            status, detail = 'fail', greeting_detail
        else:
            image_ok, image_detail = _send_default_resume_image(send_resume_image)
            status = 'success' if image_ok else 'fail'
            detail = f"{greeting_detail}；{image_detail}"
        restored, restore_detail = _restore_source_page(source_url)
        if not restored and status == 'success':
            detail = f"{detail}；警告: {restore_detail}"
        elif not restored:
            detail = f"{detail}；{restore_detail}"
        else:
            detail = f"{detail}；{restore_detail}"
        return status, detail

    # 4. 处理打招呼弹窗
    popup = handle_greet_popup(greeting_text)
    if popup in {'custom_input_not_found', 'custom_input_failed'}:
        return 'fail', f'定制问候语未能安全写入弹窗: {popup}'
    sent_greeting = str(popup).startswith('sent:')

    if sent_greeting:
        time.sleep(1.5)

    # 5. 点击「留在此页」
    stay_result = click_stay_on_page()
    stayed_on_page = (stay_result == 'clicked:留在此页')

    if stayed_on_page:
        time.sleep(1)
    elif not sent_greeting:
        handle_popup()
        time.sleep(1)

    # 6. 检测最终状态
    fatal_status, fatal_detail = _check_fatal_patterns()
    if fatal_status:
        return fatal_status, fatal_detail

    btn_text = _get_chat_button_text()

    # 7. 综合判断
    if '继续沟通' in btn_text:
        return 'success', '投递成功(按钮已变为继续沟通)'

    if sent_greeting and stayed_on_page:
        return 'success', '投递成功(发送招呼+留在此页)'

    if sent_greeting:
        return 'success', '投递成功(已发送招呼)'

    # v5.1 修复: "留在此页"被点击本身就是投递成功的强证据
    # "留在此页"按钮只在招呼语发送成功后的确认弹窗中出现
    if stayed_on_page:
        return 'success', '投递成功(留在此页已点击,招呼弹窗可能自动发送)'

    return 'unknown', f'未确认成功: popup={popup}, stay={stay_result}, btn={btn_text[:20]}'


# ═══════════════════════════════════════════════════════════
# 批量投递（兼容旧接口）
# ═══════════════════════════════════════════════════════════

def run_batch(jobs_file, progress_file="stream_progress.json", max_count=0):
    """批量投递（兼容旧接口，v5.0推荐使用serial_loop.py串行控制）"""
    register_signal_guard()

    if not health_check():
        print("WebBridge 不可达，请先运行 env_check.py")
        return None

    if not ensure_active_tab():
        print("无法建立标签页")
        return None

    with open(jobs_file, 'r', encoding='utf-8') as f:
        jobs = json.load(f)

    unapproved = [j for j in jobs if j.get('decision') != 'APPROVE']
    if unapproved:
        print(f"AI 审核守卫: 发现 {len(unapproved)} 条未通过 AI 审核的岗位，拒绝投递")
        return None

    pm = ProgressManager(progress_file)
    pm.load()

    to_deliver = [j for j in jobs if not pm.is_done(j.get('jobId', ''))]
    max_to_deliver = max_count if max_count > 0 else len(to_deliver)
    actual_to_deliver = min(len(to_deliver), max_to_deliver)

    print(f"SESSION: {SESSION}")
    print(f"本批 {len(jobs)} 条，已投 {pm.delivered_count} 条，待投 {len(to_deliver)} 条，本批上限 {max_to_deliver}")
    print("=" * 60)

    stats = {
        "success": 0, "skip": 0, "fail": 0, "fatal_limit": 0,
        "login_expired": 0, "unknown": 0, "total": 0,
    }
    consecutive_unknown = 0

    for idx, job in enumerate(to_deliver[:actual_to_deliver]):
        job_id = job.get("jobId", "")
        job_title = job.get("title", "?")[:25]

        if not job_id:
            continue

        print(f"[{idx+1}/{actual_to_deliver}] 投递 {job_title} ({job_id}) ...", end=" ")

        status, detail = deliver_inplace(job_id, job_info=job)

        if status == 'success':
            pm.add_delivered(job_id, job)
        else:
            pm.add_failed(job_id, job, detail)
        pm.save()

        stats["total"] += 1
        stats[status] = stats.get(status, 0) + 1

        print(f"{status.upper()}: {detail[:60]}")

        if status == 'unknown':
            consecutive_unknown += 1
            if consecutive_unknown >= MAX_CONSECUTIVE_UNKNOWN:
                print(f"\n连续 {MAX_CONSECUTIVE_UNKNOWN} 次未知状态，熔断暂停")
                break
        else:
            consecutive_unknown = 0

        if status in ('fatal_limit', 'login_expired'):
            print(f"\n致命错误，整批停止")
            break

        # ★ v5.0 投递目标检查
        target_check = check_delivery_target(progress_file)
        if target_check["target_met"]:
            print(f"\n★ 投递目标 {DAILY_TARGET} 份已达成！停止投递")
            break

        time.sleep(random.uniform(2, 3.5))

    print("\n" + "=" * 60)
    print(f"投递完成: 成功 {stats['success']} / 跳过 {stats['skip']} / 失败 {stats['fail']}")
    print(f"         上限 {stats['fatal_limit']} / 登录过期 {stats['login_expired']} / 未知 {stats['unknown']}")
    print("=" * 60)

    stats["delivered_total"] = pm.delivered_count
    return stats


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="投递执行引擎")
    parser.add_argument("jobs_file", help="待投递岗位 JSON 文件")
    parser.add_argument("--progress", default="stream_progress.json", help="进度文件")
    parser.add_argument("--max", type=int, default=0, help="本批最多投递数量")
    args = parser.parse_args()

    run_batch(args.jobs_file, args.progress, args.max)
