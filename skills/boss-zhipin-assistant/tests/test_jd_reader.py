import json
import os
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))
os.environ.setdefault("BOSS_PROFILE_FILE", str(SKILL_DIR / "user_profile.example.json"))

from scripts import jd_reader


def test_click_card_recovers_job_after_lazy_loading(monkeypatch) -> None:
    responses = iter([
        json.dumps({"found": False, "detail": "no_link_match"}),
        json.dumps({"found": False, "detail": "no_link_match"}),
        "30",
        json.dumps({"found": True, "title": "目标岗位"}),
        "clicked",
    ])
    scrolls = []

    monkeypatch.setattr(jd_reader, "evaluate", lambda _code: next(responses))
    monkeypatch.setattr(jd_reader, "scroll_page", lambda: scrolls.append(True))
    monkeypatch.setattr(jd_reader.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        jd_reader,
        "_verify_panel",
        lambda *_args, **_kwargs: {"ok": True, "detail": ""},
    )

    result = jd_reader.click_card_inplace("job-id")

    assert result["ok"] is True
    assert result["title"] == "目标岗位"
    assert len(scrolls) == 2


def test_lazy_load_recovery_stops_after_stable_card_count(monkeypatch) -> None:
    monkeypatch.setattr(
        jd_reader,
        "_find_card",
        lambda _job_id: {"found": False, "detail": "no_link_match"},
    )
    monkeypatch.setattr(jd_reader, "evaluate", lambda _code: "15")
    monkeypatch.setattr(jd_reader, "scroll_page", lambda: None)
    monkeypatch.setattr(jd_reader.time, "sleep", lambda _seconds: None)

    result = jd_reader._recover_card_by_lazy_loading("missing", max_scrolls=12)

    assert result == {
        "found": False,
        "detail": "no_link_match_after_lazy_load:15",
    }
