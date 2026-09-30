#!/usr/bin/env python3
"""
Phase 5: 统一投递执行 (v2 — 智能页面反馈监测版)

核心改进:
  1. 点击沟通按钮后，读取页面反馈文本，判断实际结果
  2. 检测"今日沟通次数已达上限"→ 立即停止整批投递
  3. 检测登录过期/页面跳转 → 停止并报警
  4. 检测"已沟通过" → 跳过该岗位
  5. 连续3次未知失败 → 暂停并提示人工介入
  6. 不再盲目假设点击=成功

用法:
    cd <WORK_DIR>
    python phase5_deliver.py jobs_to_deliver.json [--progress stream_progress.json]
"""

import json
import time
import random
import sys
import os

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_DIR)

from scripts.webbridge_client import (
    SESSION, navigate, evaluate, handle_popup,
    ensure_active_tab, health_check, clean_pid_files,
    ProgressManager, register_signal_guard, SafeInterrupt,
)

# ═══════════════════════════════════════════════════════════
# 页面反馈检测常量
# ═══════════════════════════════════════════════════════════

# 致命错误 — 检测到立即停止整批投递
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
    "您今天已与",        # "您今天已与150位BOSS沟通"
    "休息一下，明天再来",
    "已达今日沟通上限",
]

# 登录/会话过期 — 需要重新登录
LOGIN_PATTERNS = [
    "请先登录",
    "登录已过期",
    "扫码登录",
    "BOSS直聘登录",
    "安全验证",
]

# 可跳过 — 该岗位无法投递但不影响后续
SKIP_PATTERNS = [
    "已经沟通过",
    "已沟通过该职位",
    "职位已关闭",
    "职位不存在",
    "职位已下线",
    "该职位已失效",
]

# 成功指标
SUCCESS_PATTERNS = [
    "立即沟通",
    "开始聊天",
    "发送成功",
    "已发送",
    "打招呼成功",
]

# 连续未知失败上限
MAX_CONSECUTIVE_UNKNOWN = 3


def handle_greet_popup():
    """
    处理打招呼弹窗，点击发送/确定按钮。
    BOSS直聘点击"立即沟通"后会弹出打招呼确认框，
    需要点击"发送"按钮才能完成投递。

    返回:
      'sent:xxx' | 'no_popup'
    """
    popup_result = evaluate("""
    (function(){
        // 1. 在弹窗容器内查找发送按钮
        var dialogSelectors = '.dialog-wrap, .greet-pop, .dialog-container, .layer-dialog, .modal, .ant-modal-wrap, .layer-ext';
        var dialogs = document.querySelectorAll(dialogSelectors);
        for (var i = 0; i < dialogs.length; i++) {
            var d = dialogs[i];
            var rect = d.getBoundingClientRect();
            var style = window.getComputedStyle(d);
            if (rect.width > 0 && rect.height > 0 && style.display !== 'none') {
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

        // 2. 全页面回退搜索 — 查找可见的"发送"按钮
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

        // 3. 查找 .btn-sure (BOSS常见确认按钮class)
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
    """)
    return popup_result if popup_result else 'no_popup'


def detect_page_feedback():
    """
    点击沟通按钮后，读取页面反馈，判断投递结果。

    返回:
      (status, detail)
      status: 'success' | 'fatal_limit' | 'login_expired' | 'skip' | 'unknown'
      detail: 人类可读的描述
    """
    time.sleep(2.5)

    # 读取页面完整文本（含弹窗、对话框、提示信息）
    page_text = evaluate("""
    (function(){
        var texts = [];

        // 1. 检查 body innerText（覆盖全页）
        var bodyText = document.body.innerText || '';
        texts.push(bodyText);

        // 2. 检查所有可见弹窗/对话框
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

        // 3. 检查 .error-tip, .err-tip, .tips 等错误提示
        var tips = document.querySelectorAll('.error-tip, .err-tip, .tips, .tip-text, .error-msg');
        for (var i = 0; i < tips.length; i++) {
            texts.push(tips[i].innerText || '');
        }

        return texts.join('\\n');
    })()
    """) or ""

    # 截取前2000字符用于匹配（避免太长）
    page_text = page_text[:2000]

    # 检查当前URL — 是否被跳转到登录页
    current_url = evaluate("window.location.href") or ""
    if "login" in current_url or "signin" in current_url or "passport" in current_url:
        return 'login_expired', f"页面跳转到登录: {current_url[:80]}"

    # 1. 检测每日上限
    for pattern in FATAL_PATTERNS:
        if pattern in page_text:
            return 'fatal_limit', f"触发每日上限: {pattern}"

    # 2. 检测登录过期
    for pattern in LOGIN_PATTERNS:
        if pattern in page_text:
            return 'login_expired', f"登录过期: {pattern}"

    # 3. 检测可跳过岗位
    for pattern in SKIP_PATTERNS:
        if pattern in page_text:
            return 'skip', f"跳过: {pattern}"

    # 4. 检测成功指标
    # 成功的标志：沟通按钮变成了"继续沟通"或出现了聊天对话框
    chat_dialog_visible = evaluate("""
    (function(){
        var chatBox = document.querySelector('.chat-container, .chat-box, .chat-wrap, #chat-wrap');
        if (chatBox) {
            var rect = chatBox.getBoundingClientRect();
            if (rect.width > 0 && rect.height > 0) return true;
        }
        // 按钮文字变为"继续沟通"
        var btn = document.querySelector('.btn-startchat, .job-chat-btn');
        if (btn && btn.textContent.indexOf('继续沟通') >= 0) return true;
        // 出现"立即沟通"模态框且可见
        var greet = document.querySelector('.greet-pop, .dialog-wrap');
        if (greet) {
            var rect = greet.getBoundingClientRect();
            if (rect.width > 100 && rect.height > 100) return true;
        }
        return false;
    })()
    """) or ""

    if chat_dialog_visible == 'true':
        # 有弹窗或对话框出现，说明沟通已发起
        return 'success', '检测到沟通对话框/弹窗'

    # 5. 如果按钮文字是"继续沟通"，说明之前已经沟通过
    btn_text = evaluate("""
    (function(){
        var btn = document.querySelector('.btn-startchat, .job-chat-btn');
        return btn ? btn.textContent.trim() : '';
    })()
    """) or ""

    if '继续沟通' in btn_text:
        return 'success', '按钮变为继续沟通'

    # 6. 无法确定 — 返回未知，附带页面片段用于调试
    snippet = page_text.replace('\n', ' ').strip()[:150]
    return 'unknown', f'未知状态, 按钮文字: {btn_text[:20]}, 页面片段: {snippet}'


def click_chat(job_id):
    """
    进入详情页，点击沟通按钮，并检测页面反馈。

    返回:
      (status, detail)
      status: 'success' | 'fatal_limit' | 'login_expired' | 'skip' | 'fail' | 'unknown'
    """
    navigate(f"https://www.zhipin.com/job_detail/{job_id}.html",
             wait_range=(3, 5))

    # 检查页面是否正常加载（非404、非登录跳转）
    current_url = evaluate("window.location.href") or ""
    if "login" in current_url or "passport" in current_url:
        return 'login_expired', f'详情页跳转登录: {current_url[:80]}'

    # 检查页面是否有内容（非404）
    body_len = evaluate("document.body.innerText.length") or "0"
    if int(body_len) < 100:
        return 'fail', f'页面内容过少({body_len}), 可能404'

    # 尝试点击 .btn-startchat
    click_result = evaluate("""
    (function(){
        var btn = document.querySelector('.btn-startchat');
        if (btn) {
            var text = btn.textContent.trim();
            btn.click();
            return 'clicked:' + text;
        }
        btn = document.querySelector('.job-chat-btn');
        if (btn) {
            var text = btn.textContent.trim();
            btn.click();
            return 'clicked:' + text;
        }
        // 检查是否有"继续沟通"按钮（说明已沟通过）
        var btns = document.querySelectorAll('button, a');
        for (var i = 0; i < btns.length; i++) {
            var t = btns[i].textContent.trim();
            if (t === '继续沟通' || t === '继续打招呼') {
                return 'already:' + t;
            }
        }
        return 'not_found';
    })()
    """)

    if click_result.startswith('already:'):
        return 'skip', f'已沟通过: {click_result}'

    if click_result == 'not_found':
        # 可能页面未加载完或职位已关闭
        body_text = evaluate("document.body.innerText") or ""
        if any(p in body_text for p in ['职位已关闭', '职位不存在', '已下线']):
            return 'skip', '职位已关闭/下线'
        return 'fail', '沟通按钮未找到'

    # ★★★ 关键：先检测致命错误（每日上限/登录过期），再处理弹窗 ★★★
    # 点击"立即沟通"后，如果达到上限，BOSS会弹出"您已达到沟通上限"弹窗
    # 必须在关闭弹窗之前检测到这个提示，否则弹窗被关闭后就检测不到了
    time.sleep(2)

    # 读取页面文本（含弹窗内容），检查致命错误
    pre_check_text = evaluate("""
    (function(){
        var texts = [];
        texts.push(document.body.innerText || '');
        var dialogs = document.querySelectorAll('.dialog-wrap, .greet-pop, .dialog-container, .layer-dialog, .modal, .ant-modal-wrap');
        for (var i = 0; i < dialogs.length; i++) {
            var rect = dialogs[i].getBoundingClientRect();
            var style = window.getComputedStyle(dialogs[i]);
            if (rect.width > 0 && rect.height > 0 && style.display !== 'none') {
                texts.push(dialogs[i].innerText || '');
            }
        }
        return texts.join('\\n').substring(0, 3000);
    })()
    """) or ""

    # 检测每日上限 — 在处理弹窗之前！
    for pattern in FATAL_PATTERNS:
        if pattern in pre_check_text:
            return 'fatal_limit', f"触发每日上限: {pattern}"

    # 检测登录过期
    for pattern in LOGIN_PATTERNS:
        if pattern in pre_check_text:
            return 'login_expired', f"登录过期: {pattern}"

    # 检测可跳过
    for pattern in SKIP_PATTERNS:
        if pattern in pre_check_text:
            return 'skip', f"跳过: {pattern}"

    # ★ 未触发致命错误，处理打招呼弹窗（发送招呼）
    popup = handle_greet_popup()
    if popup != 'no_popup':
        time.sleep(1.5)
        # 二次检测弹窗
        popup2 = handle_greet_popup()
        if popup2 != 'no_popup':
            time.sleep(0.5)

    # 处理第120份投递弹窗等
    handle_popup()
    time.sleep(1)

    # 弹窗处理完毕后，检测页面反馈
    status, detail = detect_page_feedback()

    return status, detail


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Phase 5: 投递执行 (v2 智能监测)")
    parser.add_argument("input", help="待投递岗位 JSON 文件")
    parser.add_argument("--progress", default="stream_progress.json", help="进度文件")
    parser.add_argument("--max", type=int, default=0, help="本批最多投递数量 (0=不限)")
    args = parser.parse_args()

    # 信号安全
    register_signal_guard()

    # 环境检查
    if not health_check():
        print("WebBridge 未运行，尝试清理 PID...")
        cleaned = clean_pid_files()
        if cleaned:
            print(f"已清理 PID 文件: {cleaned}")
        print("请手动运行: kimi-webbridge start")
        sys.exit(1)

    print(f"SESSION: {SESSION} (全局唯一)")
    print(f"版本: v2 智能页面反馈监测版")
    print("=" * 60)

    if not ensure_active_tab():
        print("无法建立 WebBridge 标签页，请检查浏览器和登录状态")
        sys.exit(1)

    # 加载岗位
    with open(args.input, 'r', encoding='utf-8') as f:
        jobs = json.load(f)

    # 加载进度
    pm = ProgressManager(args.progress)
    pm.load()

    # 过滤已投递
    to_deliver = [j for j in jobs if not pm.is_done(j.get('jobId', ''))]

    max_to_deliver = args.max if args.max > 0 else len(to_deliver)
    actual_to_deliver = min(len(to_deliver), max_to_deliver)

    print(f"本批 {len(jobs)} 条，已投 {pm.delivered_count} 条，待投 {len(to_deliver)} 条，本批上限 {max_to_deliver}")
    print("=" * 60)

    success_count = 0
    fail_count = 0
    skip_count = 0
    consecutive_unknown = 0
    stop_reason = None

    try:
        for i, job in enumerate(to_deliver, 1):
            # 检查是否达到本批上限
            if success_count + fail_count + skip_count >= max_to_deliver:
                stop_reason = f"达到本批上限 {max_to_deliver}"
                break

            jid = job.get('jobId', '')
            title = job.get('title', '')[:25]
            company = job.get('company', '')[:15]
            salary = job.get('salary', '')

            total_count = pm.delivered_count + i
            print(f"[{i}/{len(to_deliver)}] (累计{total_count}) {title} | {salary} | {company}")

            try:
                status, detail = click_chat(jid)

                if status == 'success':
                    print(f"  ✓ 投递成功 — {detail}")
                    pm.add_delivered(jid, job)
                    success_count += 1
                    consecutive_unknown = 0

                elif status == 'fatal_limit':
                    # ★★★ 致命：每日上限，立即停止 ★★★
                    print(f"  ✗✗✗ 每日上限触发 — {detail}")
                    print(f"  ✗✗✗ 立即停止投递！BOSS今日投递额度已用完")
                    stop_reason = f"每日上限: {detail}"
                    break

                elif status == 'login_expired':
                    # ★★★ 登录过期，立即停止 ★★★
                    print(f"  ✗✗✗ 登录过期 — {detail}")
                    print(f"  ✗✗✗ 请重新登录BOSS直聘后再运行")
                    stop_reason = f"登录过期: {detail}"
                    break

                elif status == 'skip':
                    print(f"  → 跳过 — {detail}")
                    # 跳过的岗位也标记为已完成，避免重复尝试
                    pm.add_delivered(jid, job)
                    skip_count += 1
                    consecutive_unknown = 0

                elif status == 'fail':
                    print(f"  ✗ 失败 — {detail}")
                    pm.add_failed(jid, job, detail[:80])
                    fail_count += 1
                    consecutive_unknown = 0

                elif status == 'unknown':
                    print(f"  ? 未知状态 — {detail}")
                    pm.add_failed(jid, job, f"unknown: {detail[:60]}")
                    fail_count += 1
                    consecutive_unknown += 1

                    if consecutive_unknown >= MAX_CONSECUTIVE_UNKNOWN:
                        print(f"\n{'!'*60}")
                        print(f"连续 {MAX_CONSECUTIVE_UNKNOWN} 次未知状态，可能页面异常或需要人工检查")
                        print(f"{'!'*60}")
                        stop_reason = f"连续{MAX_CONSECUTIVE_UNKNOWN}次未知状态"
                        break

                else:
                    print(f"  ? 未预期状态: {status} — {detail}")
                    pm.add_failed(jid, job, f"{status}: {detail[:60]}")
                    fail_count += 1

            except SafeInterrupt:
                print(f"\n收到中断信号，保存进度...")
                pm.save()
                raise

            except Exception as e:
                print(f"  ✗ 异常: {e}")
                pm.add_failed(jid, job, str(e)[:80])
                fail_count += 1

            # 每投一条立即保存
            pm.save()

            # 随机间隔（避免过于频繁）
            time.sleep(random.uniform(2, 4))

    except SafeInterrupt:
        print(f"\n中断保存完成。成功 {success_count}，失败 {fail_count}，跳过 {skip_count}")
        sys.exit(130)

    # 最终汇总
    print(f"\n{'=' * 60}")
    if stop_reason:
        print(f"停止原因: {stop_reason}")
    print(f"本批: 成功 {success_count}，失败 {fail_count}，跳过 {skip_count}")
    print(f"累计: 成功 {pm.delivered_count}，失败 {pm.failed_count}")
    if stop_reason and ('上限' in stop_reason or '登录' in stop_reason):
        print(f"\n⚠️ 需要人工介入: {stop_reason}")


if __name__ == "__main__":
    main()
