from pathlib import Path

from job_search_assistant.resume_pdf import build_resume_pdf
from job_search_assistant.resume_templates import SAMPLE_RESUME


def main() -> None:
    output = Path(__file__).parents[3] / "output" / "pdf" / "resume-template-teal-professional.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(build_resume_pdf(SAMPLE_RESUME))
    print(output)


if __name__ == "__main__":
    main()
