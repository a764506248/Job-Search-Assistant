from datetime import UTC, datetime

from job_search_assistant.domain.models import CapturedJob
from job_search_assistant.repositories import JobRepository


def make_job(description: str = "负责 RAG 应用研发") -> CapturedJob:
    return CapturedJob(
        platform="boss",
        platform_job_id="job-123",
        url="https://www.zhipin.com/job_detail/job-123.html",
        title="AI 应用开发工程师",
        company_name="示例公司",
        description=description,
        skills=["Python", "RAG"],
        captured_at=datetime(2026, 9, 28, tzinfo=UTC),
        source="dom",
    )


def test_repository_keeps_changed_job_snapshots(tmp_path) -> None:
    repository = JobRepository(tmp_path / "jobs.sqlite3")

    assert repository.save_many([make_job()]) == ["job-123"]
    assert repository.save_many([make_job()]) == []
    assert repository.save_many([make_job("负责 Agent 和 RAG 应用研发")]) == ["job-123"]
    assert repository.count() == 2
