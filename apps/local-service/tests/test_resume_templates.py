import re

from fastapi.testclient import TestClient

from job_search_assistant.main import create_app


def test_resume_template_catalog_and_sample_pdf(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))

    catalog = client.get("/v1/resume-templates")
    assert catalog.status_code == 200
    assert catalog.json()["items"][0]["id"] == "teal-professional"
    assert catalog.json()["sampleData"]["name"] == "林晓舟"

    pdf = client.get("/v1/resume-templates/teal-professional/sample.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert len(re.findall(rb"/Type /Page\b", pdf.content)) == 3


def test_unknown_resume_template_returns_404(tmp_path) -> None:
    client = TestClient(create_app(tmp_path / "jobs.sqlite3"))
    response = client.get("/v1/resume-templates/not-found/sample.pdf")
    assert response.status_code == 404
