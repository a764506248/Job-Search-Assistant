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
from scripts.webbridge_client import (
    SESSION, api, click as webbridge_click, fill as webbridge_fill, evaluate, navigate, handle_popup,
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
    """统计当前聊天记录中可见的完全相同消息。

    输入框位于右侧区域，旧实现会把尚未真正发送的编辑器文本也计为消息，
    从而把空会话误报为发送成功。这里只接受位于编辑器上方、且不属于
    输入控件/按钮/常用语面板的叶子节点。
    """
    encoded = json.dumps(text, ensure_ascii=False)
    return int(evaluate(f"""
    (function(){{
        var normalize = function(value) {{
            return (value || '').replace(/\\s+/g, ' ').trim();
        }};
        var expected = normalize({encoded});
        var input = document.querySelector('#chat-input[contenteditable="true"]');
        var inputRect = input ? input.getBoundingClientRect() : null;
        // ★ 只在右侧会话区范围内查找：左侧会话列表会渲染各会话最后一条消息的
        // 预览（.last-msg-text），全局查找会把别的会话里已发送过的相同问候语
        // 误判为"当前会话已发送"，从而跳过发送并谎报成功。
        var conv = document.querySelector('.chat-conversation');
        var scope = conv || document;
        var preferred = Array.from(scope.querySelectorAll(
            '.message-content, .message-text, .chat-message, .item-myself .text, ' +
            '[class*="message"] [class*="text"], [class*="message"] [class*="content"]'
        ));
        var nodes = preferred.length ? preferred : Array.from(scope.querySelectorAll('*'));
        var matches = nodes.filter(function(el){{
            if (normalize(el.innerText || el.textContent) !== expected) return false;
            if (el === input || el.closest(
                '#chat-input, [contenteditable="true"], textarea, input, button, ' +
                '.sentence-panel, .chat-editor, .chat-input, .chat-operate, ' +
                '.user-list, .friend-content, .friend-content-warp'
            )) return false;
            var r = el.getBoundingClientRect();
            var s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && r.left > window.innerWidth * 0.28 &&
                   (!inputRect || r.bottom < inputRect.top - 4) &&
                   s.display !== 'none' && s.visibility !== 'hidden';
        }});
        // 同一气泡可能同时命中父子容器，只保留最内层节点。
        return matches.filter(function(el){{
            return !matches.some(function(other) {{
                return other !== el && el.contains(other);
            }});
        }}).length;
    }})()
    """) or 0)


def _chat_input_text():
    """读取聊天编辑器当前文本，用于确认发送后编辑器已清空。"""
    return str(evaluate("""
    (function(){
        var input = document.querySelector('#chat-input[contenteditable="true"]');
        return input ? (input.innerText || input.textContent || '').trim() : '';
    })()
    """) or '').strip()


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


def _read_chat_identity(title, company):
    """读取当前聊天会话身份，供填写前后重复校验。"""
    expected_title = json.dumps(title, ensure_ascii=False)
    identity = evaluate(f"""
    (function(){{
        var title = {expected_title};
        var leaves = Array.from(document.querySelectorAll('*')).filter(function(el) {{
            if (el.children.length !== 0) return false;
            var r = el.getBoundingClientRect();
            var s = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && r.left > window.innerWidth * 0.28 &&
                   s.display !== 'none' && s.visibility !== 'hidden';
        }});
        return {{
            url: location.href,
            titleOk: leaves.some(function(el) {{
                return (el.textContent || '').trim() === title;
            }}),
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
    return identity


def _validate_chat_identity(title, company):
    identity = _read_chat_identity(title, company)
    if '/web/geek/chat' not in str(identity.get('url', '')):
        return False, '尚未进入聊天页，无法安全发送问候语'
    if not identity.get('titleOk') or not identity.get('companyOk'):
        return False, (
            f"目标会话校验失败: title={identity.get('titleOk')}, "
            f"company={identity.get('companyOk')}, matched={identity.get('companyMatch', '')}"
        )
    return True, ''


def _click_visible_send_button(max_wait=5.0):
    """等待发送按钮解除业务禁用态，再交给 WebBridge click 执行。"""
    selector = '[data-boss-automation-action="send-greeting"]'
    attempts = max(1, int(max_wait / 0.25))
    prepared = False
    for _ in range(attempts):
        state = evaluate("""
        (function(){
            var old = document.querySelector('[data-boss-automation-action="send-greeting"]');
            if (old) old.removeAttribute('data-boss-automation-action');
            var buttons = Array.from(document.querySelectorAll('button')).filter(function(el){
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                return (el.textContent || '').trim() === '发送' &&
                       r.width > 0 && r.height > 0 &&
                       s.display !== 'none' && s.visibility !== 'hidden';
            });
            if (buttons.length !== 1) return {ready:false, reason:'count', count:buttons.length};
            var btn = buttons[0];
            var disabled = btn.disabled || btn.classList.contains('disabled') ||
                           btn.getAttribute('aria-disabled') === 'true' ||
                           window.getComputedStyle(btn).pointerEvents === 'none';
            if (disabled) return {ready:false, reason:'disabled', className:btn.className};
            btn.setAttribute('data-boss-automation-action', 'send-greeting');
            return {ready:true, className:btn.className};
        })()
        """) or {}
        if isinstance(state, dict) and state.get('ready'):
            prepared = True
            break
        time.sleep(0.25)
    if not prepared:
        return False
    try:
        return bool(webbridge_click(selector))
    finally:
        evaluate("""
        (function(){
            var el = document.querySelector('[data-boss-automation-action="send-greeting"]');
            if (el) el.removeAttribute('data-boss-automation-action');
            return true;
        })()
        """)


def _delivered_status_count():
    """统计会话内状态为「送达/已读」的消息数。

    BOSS 前端在点击发送后会先乐观渲染一条本地气泡（此时还没有 [送达] 标记），
    真正的落库由随后的 XHR 完成。只看到气泡就判定成功会把尚未发出的消息
    记成已发送；必须等到状态标记出现，才算服务端已接收。
    """
    return int(evaluate("""
    (function(){
        var conv = document.querySelector('.chat-conversation');
        if (!conv) return 0;
        return Array.from(conv.querySelectorAll('.message-status')).filter(function(el){
            var t = (el.innerText || el.textContent || '').replace(/\\s+/g, '');
            return t.indexOf('送达') >= 0 || t.indexOf('已读') >= 0;
        }).length;
    })()
    """) or 0)


def _wait_for_greeting_delivery(greeting, before, max_wait=25.0, min_wait=3.0):
    """等待目标消息气泡出现，并确认编辑器已清空、服务端已标记送达。

    min_wait: 点击发送后的最小停留时间。过早返回会让调用方立刻导航回搜索页，
    从而中断尚未完成的发送 XHR —— 表现为脚本报成功、HR 侧却收不到消息。
    """
    started = time.time()
    before_status = _delivered_status_count()
    while time.time() - started < max_wait:
        if time.time() - started >= min_wait:
            if (_visible_message_count(greeting) > before
                    and _delivered_status_count() > before_status
                    and not _chat_input_text()):
                return True
        time.sleep(0.5)
    return False


def _send_verified_greeting(job_info, greeting_text=None):
    """仅在当前聊天明确对应目标岗位时，发送且只发送一次问候语。"""
    job_info = job_info or {}
    title = str(job_info.get('title') or '').strip()
    company = str(job_info.get('company') or '').strip()
    if not title or not company:
        return False, '缺少岗位标题或公司，拒绝发送问候语'

    identity_ok, identity_detail = _validate_chat_identity(title, company)
    if not identity_ok:
        return False, identity_detail

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

    filled = webbridge_fill('#chat-input[contenteditable="true"]', greeting)
    if not filled:
        return False, '问候语写入输入框失败'

    identity_ok, identity_detail = _validate_chat_identity(title, company)
    if not identity_ok:
        return False, f'填写后{identity_detail}'

    sent = _click_visible_send_button()
    if not sent:
        return False, '发送按钮不可用'

    if not _wait_for_greeting_delivery(greeting, before):
        remaining = _chat_input_text()
        state = '输入框仍有内容' if remaining else '输入框已清空但未识别到消息气泡'
        return False, f'点击发送后20秒内未观察到问候语送达（{state}）'
    return True, '问候语已发送并在目标会话中验证'


def _send_default_resume_image(enabled=None):
    """通过已安装的 Chrome 测试插件发送默认简历首页图。"""
    if enabled is None:
        enabled = SEND_RESUME_IMAGE
    if not enabled:
        return True, '简历图片发送未启用'

    prepared = evaluate("""
    (function(){
        var host = document.querySelector('#job-search-assistant-image-test-host');
        var root = host && host.shadowRoot;
        if (!root) return {ok:false, reason:'plugin_missing'};
        var version = (host.dataset && host.dataset.version) || '0.0.0';
        var parts = version.split('.').map(function(value){ return parseInt(value, 10) || 0; });
        var compatible = parts[0] > 0 || parts[1] > 2 || (parts[1] === 2 && parts[2] >= 3);
        if (!compatible) return {ok:false, reason:'plugin_too_old', version:version};
        var load = root.querySelector('button.load');
        var send = root.querySelector('button.send');
        if (!load || !send) return {ok:false, reason:'plugin_incompatible'};
        load.click();
        return {ok:true, version:version};
    })()
    """) or {}
    if not prepared.get('ok'):
        reason = prepared.get('reason', 'unknown')
        return False, f'简历图片插件不可用（{reason}），请加载 v0.2.3 或更高版本并刷新 BOSS 页面'

    ready = False
    load_error = ''
    for _ in range(20):
        time.sleep(0.5)
        state = evaluate("""
        (function(){
            var host = document.querySelector('#job-search-assistant-image-test-host');
            var root = host && host.shadowRoot;
            var status = root && root.querySelector('.status');
            var send = root && root.querySelector('button.send');
            var text = status ? status.textContent.trim() : '';
            return {ready:!!send && !send.disabled && text.indexOf('尚未发送') >= 0, text:text};
        })()
        """) or {}
        if state.get('ready'):
            ready = True
            break
        load_error = str(state.get('text', ''))
    if not ready:
        return False, f'默认简历图片预览加载失败: {load_error or "等待超时"}'

    sent = evaluate("""
    (function(){
        var host = document.querySelector('#job-search-assistant-image-test-host');
        var root = host && host.shadowRoot;
        var send = root && root.querySelector('button.send');
        if (!send || send.disabled) return false;
        send.click();
        return true;
    })()
    """)
    if not sent:
        return False, '插件确认发送按钮不可用'

    for _ in range(20):
        time.sleep(0.5)
        status_text = str(evaluate("""
        (function(){
            var host = document.querySelector('#job-search-assistant-image-test-host');
            var root = host && host.shadowRoot;
            var status = root && root.querySelector('.status');
            return status ? status.textContent.trim() : '';
        })()
        """) or '')
        if '已将图片交给 BOSS 发送' in status_text:
            return True, f"默认简历图片已通过插件发送（v{prepared.get('version', 'unknown')}）"
        if '没有执行发送' in status_text:
            return False, status_text
    return False, '插件已点击发送，但未取得发送状态'


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

    clicked = any(
        webbridge_click(selector)
        for selector in ('.op-btn-chat', '.btn-startchat', '.job-chat-btn')
    )

    if not clicked:
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
        # 发送后必须给 XHR 留出落地时间再离开页面：提前导航会中断请求，
        # 前端气泡是乐观渲染的，页面一卸载消息就丢了。
        time.sleep(3)
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

    # 7. 综合判断。旧弹窗分支无法看到目标聊天中的消息气泡，因此不能把
    # DOM click、按钮文案变化或「留在此页」单独视为 v5.9.1 的成功证据。
    if '继续沟通' in btn_text:
        return 'unknown', '已建立沟通，但旧弹窗分支无法验证目标问候语消息气泡'

    if sent_greeting or stayed_on_page:
        return 'unknown', (
            f'已触发弹窗操作但未验证目标问候语消息气泡: '
            f'popup={popup}, stay={stay_result}'
        )

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
