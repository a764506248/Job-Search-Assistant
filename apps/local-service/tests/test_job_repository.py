import sqlite3
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


def test_repository_upserts_changed_content_into_stable_job_snapshot(tmp_path) -> None:
    repository = JobRepository(tmp_path / "jobs.sqlite3")

    assert repository.save_many([make_job()]) == ["job-123"]
    assert repository.save_many([make_job()]) == []
    assert repository.save_many([make_job("负责 Agent 和 RAG 应用研发")]) == []
    assert repository.count() == 1
    jobs = repository.list_recent()
    assert jobs[0].description == "负责 Agent 和 RAG 应用研发"
    assert jobs[0].skills == ["Python", "RAG"]

    assert repository.delete(jobs[0].id) is True
    assert repository.delete(jobs[0].id) is False
    assert repository.count() == 0


def test_repository_normalizes_private_use_salary_on_write_and_historical_read(
    tmp_path,
) -> None:
    database_path = tmp_path / "jobs.sqlite3"
    repository = JobRepository(database_path)
    raw_salary = "\ue033\ue031-\ue035\ue031K·\ue032\ue035薪"

    repository.save_many([make_job().model_copy(update={"salary_text": raw_salary})])
    with sqlite3.connect(database_path) as connection:
        persisted = connection.execute("SELECT salary_text FROM job_postings").fetchone()[0]
        assert persisted == "20-40K·14薪"
        connection.execute("UPDATE job_postings SET salary_text = ?", (raw_salary,))

    assert repository.list_recent()[0].salary_text == "20-40K·14薪"


def test_repository_does_not_replace_readable_salary_with_unknown_private_use_text(
    tmp_path,
) -> None:
    repository = JobRepository(tmp_path / "jobs.sqlite3")
    repository.save_many([make_job().model_copy(update={"salary_text": "25-35K"})])

    repository.save_many(
        [make_job().model_copy(update={"salary_text": "\ue100-\ue101K"})]
    )

    assert repository.list_recent()[0].salary_text == "25-35K"
