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
