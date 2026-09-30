import os
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))
os.environ.setdefault("BOSS_PROFILE_FILE", str(SKILL_DIR / "user_profile.example.json"))

from scripts import deliver_engine


def test_company_match_accepts_brand_and_legal_name() -> None:
    assert deliver_engine._company_names_match(
        "北京易森动力无限科技有限公司",
        "易森动力",
    )


def test_company_match_rejects_different_company() -> None:
    assert not deliver_engine._company_names_match("易森动力", "农信数智")


def test_restore_source_page_requires_jobs_url(monkeypatch) -> None:
    called = False

    def fake_navigate(*_args, **_kwargs):
        nonlocal called
        called = True
        return {"ok": True}

    monkeypatch.setattr(deliver_engine, "navigate", fake_navigate)
    restored, _ = deliver_engine._restore_source_page("https://www.zhipin.com/web/geek/chat")

    assert restored is False
    assert called is False


def test_restore_source_page_navigates_and_verifies(monkeypatch) -> None:
    monkeypatch.setattr(deliver_engine, "navigate", lambda *_args, **_kwargs: {"ok": True})
    monkeypatch.setattr(
        deliver_engine,
        "evaluate",
        lambda _code: "https://www.zhipin.com/web/geek/jobs?query=AI&city=101010100",
    )

    restored, detail = deliver_engine._restore_source_page(
        "https://www.zhipin.com/web/geek/jobs?query=AI&city=101010100"
    )

    assert restored is True
    assert detail == "已返回搜索页"


def _verified_chat_identity() -> dict[str, object]:
    return {
        "url": "https://www.zhipin.com/web/geek/chat",
        "titleOk": True,
        "visibleTexts": ["目标公司"],
    }


def test_send_verified_greeting_rejects_empty_chat_after_click(monkeypatch) -> None:
    monkeypatch.setattr(deliver_engine, "_validate_chat_identity", lambda *_args: (True, ""))
    monkeypatch.setattr(deliver_engine, "webbridge_fill", lambda *_args: True)
    monkeypatch.setattr(deliver_engine, "_click_visible_send_button", lambda: True)
    monkeypatch.setattr(deliver_engine, "_visible_message_count", lambda _text: 0)
    monkeypatch.setattr(deliver_engine, "_wait_for_greeting_delivery", lambda *_args: False)
    monkeypatch.setattr(deliver_engine, "_chat_input_text", lambda: "")

    ok, detail = deliver_engine._send_verified_greeting(
        {"title": "目标岗位", "company": "目标公司"},
        "测试问候语",
    )

    assert ok is False
    assert detail == "点击发送后20秒内未观察到问候语送达（输入框已清空但未识别到消息气泡）"


def test_send_verified_greeting_requires_cleared_editor(monkeypatch) -> None:
    monkeypatch.setattr(deliver_engine, "_validate_chat_identity", lambda *_args: (True, ""))
    monkeypatch.setattr(deliver_engine, "webbridge_fill", lambda *_args: True)
    monkeypatch.setattr(deliver_engine, "_click_visible_send_button", lambda: True)
    monkeypatch.setattr(deliver_engine, "_visible_message_count", lambda _text: 0)
    monkeypatch.setattr(deliver_engine, "_wait_for_greeting_delivery", lambda *_args: False)
    monkeypatch.setattr(deliver_engine, "_chat_input_text", lambda: "")

    ok, detail = deliver_engine._send_verified_greeting(
        {"title": "目标岗位", "company": "目标公司"},
        "测试问候语",
    )

    assert ok is False
    assert detail == "点击发送后20秒内未观察到问候语送达（输入框已清空但未识别到消息气泡）"


def test_send_verified_greeting_accepts_new_bubble_and_cleared_editor(monkeypatch) -> None:
    monkeypatch.setattr(deliver_engine, "_validate_chat_identity", lambda *_args: (True, ""))
    monkeypatch.setattr(deliver_engine, "webbridge_fill", lambda *_args: True)
    monkeypatch.setattr(deliver_engine, "_click_visible_send_button", lambda: True)
    monkeypatch.setattr(deliver_engine, "_visible_message_count", lambda _text: 0)
    monkeypatch.setattr(deliver_engine, "_wait_for_greeting_delivery", lambda *_args: True)

    ok, detail = deliver_engine._send_verified_greeting(
        {"title": "目标岗位", "company": "目标公司"},
        "测试问候语",
    )

    assert ok is True
    assert detail == "问候语已发送并在目标会话中验证"


def test_click_send_waits_for_business_enabled_state(monkeypatch) -> None:
    states = iter([
        {"ready": False, "reason": "disabled", "className": "btn-send disabled"},
        {"ready": True, "className": "btn-send"},
        True,
    ])
    monkeypatch.setattr(deliver_engine, "evaluate", lambda _code: next(states))
    monkeypatch.setattr(deliver_engine, "webbridge_click", lambda _selector: True)
    monkeypatch.setattr(deliver_engine.time, "sleep", lambda _seconds: None)

    assert deliver_engine._click_visible_send_button(max_wait=1) is True


def test_send_verified_greeting_revalidates_identity_after_fill(monkeypatch) -> None:
    identities = iter([(True, ""), (False, "目标会话校验失败")])
    monkeypatch.setattr(deliver_engine, "_validate_chat_identity", lambda *_args: next(identities))
    monkeypatch.setattr(deliver_engine, "webbridge_fill", lambda *_args: True)
    monkeypatch.setattr(deliver_engine, "_visible_message_count", lambda _text: 0)

    clicked = False

    def fake_click():
        nonlocal clicked
        clicked = True
        return True

    monkeypatch.setattr(deliver_engine, "_click_visible_send_button", fake_click)

    ok, detail = deliver_engine._send_verified_greeting(
        {"title": "目标岗位", "company": "目标公司"},
        "测试问候语",
    )

    assert ok is False
    assert detail == "填写后目标会话校验失败"
    assert clicked is False


def test_deliver_inplace_uses_webbridge_click_for_chat_button(monkeypatch) -> None:
    monkeypatch.setattr(
        deliver_engine,
        "click_card_inplace",
        lambda *_args, **_kwargs: {"ok": True, "detail": ""},
    )
    responses = iter([
        "https://www.zhipin.com/web/geek/jobs?query=AI",
        "scrolled:立即沟通",
        "https://www.zhipin.com/web/geek/chat",
    ])
    monkeypatch.setattr(deliver_engine, "evaluate", lambda _code: next(responses))
    monkeypatch.setattr(deliver_engine, "_check_fatal_patterns", lambda: (None, ""))
    monkeypatch.setattr(deliver_engine, "_send_verified_greeting", lambda *_args: (False, "测试停止"))
    monkeypatch.setattr(deliver_engine, "_restore_source_page", lambda _url: (True, "已返回搜索页"))
    monkeypatch.setattr(deliver_engine.time, "sleep", lambda _seconds: None)

    selectors = []

    def fake_click(selector):
        selectors.append(selector)
        return selector == ".op-btn-chat"

    monkeypatch.setattr(deliver_engine, "webbridge_click", fake_click)

    status, _ = deliver_engine.deliver_inplace(
        "job-id",
        {"title": "目标岗位", "company": "目标公司"},
        "测试问候语",
    )

    assert status == "fail"
    assert selectors == [".op-btn-chat"]


def test_send_default_resume_image_uses_extension_preview_then_send(monkeypatch) -> None:
    responses = iter([
        {"ok": True, "version": "0.2.2"},
        {"ready": True, "text": "已在扩展内加载 resume.png，尚未发送。"},
        True,
        "已将图片交给 BOSS 发送，请在聊天记录中确认图片消息已出现。",
    ])
    monkeypatch.setattr(deliver_engine, "evaluate", lambda _code: next(responses))
    monkeypatch.setattr(deliver_engine.time, "sleep", lambda _seconds: None)

    ok, detail = deliver_engine._send_default_resume_image(True)

    assert ok is True
    assert detail == "默认简历图片已通过插件发送（v0.2.2）"


def test_send_default_resume_image_does_not_fallback_when_plugin_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        deliver_engine,
        "evaluate",
        lambda _code: {"ok": False, "reason": "plugin_missing"},
    )

    ok, detail = deliver_engine._send_default_resume_image(True)

    assert ok is False
    assert "plugin_missing" in detail
    assert "v0.2.3" in detail


def test_send_default_resume_image_rejects_old_plugin(monkeypatch) -> None:
    monkeypatch.setattr(
        deliver_engine,
        "evaluate",
        lambda _code: {"ok": False, "reason": "plugin_too_old", "version": "0.2.2"},
    )

    ok, detail = deliver_engine._send_default_resume_image(True)

    assert ok is False
    assert "plugin_too_old" in detail
    assert "v0.2.3" in detail
