from pathlib import Path

from job_search_assistant.knowledge import KnowledgeSearchService
from job_search_assistant.repositories import LibraryRepository


def test_searches_structured_local_facts_without_an_index(tmp_path: Path) -> None:
    library = LibraryRepository(tmp_path / "jobs.sqlite3")
    library.save_profile(
        {
            "strengths": [{"content": "熟悉 Python 后端和 FastAPI"}],
            "techStackGroups": [{"name": "后端", "items": ["Python", "FastAPI"]}],
        }
    )
    library.create(
        "projects",
        "智能客服",
        {
            "summary": "使用 Python 与 LangGraph 构建智能客服",
            "technologies": ["Python", "LangGraph"],
        },
    )

    service = KnowledgeSearchService(library)
    results = service.search("Python FastAPI 后端工程师", 5)

    assert results
    assert results[0]["keywordScore"] > 0
    assert all("vectorScore" not in item for item in results)


def test_returns_no_evidence_when_local_facts_do_not_overlap(tmp_path: Path) -> None:
    library = LibraryRepository(tmp_path / "jobs.sqlite3")
    library.create("projects", "前端后台", {"summary": "Vue 管理页面"})

    assert KnowledgeSearchService(library).search("Rust 系统工程师", 5) == []
