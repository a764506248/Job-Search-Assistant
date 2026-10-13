FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir \
    "fastapi>=0.116,<1" \
    "pydantic-settings>=2.10,<3" \
    "pymupdf>=1.26,<2" \
    "pypdf>=6,<7" \
    "python-docx>=1.2,<2" \
    "python-multipart>=0.0.20,<1" \
    "reportlab>=4.4,<5" \
    "uvicorn>=0.35,<1" \
    "websockets>=15,<16" \
    "psycopg[binary]>=3.2,<4"
COPY src ./src
RUN pip install --no-cache-dir --no-deps .

RUN mkdir -p /data

EXPOSE 8765

CMD ["uvicorn", "job_search_assistant.main:app", "--host", "0.0.0.0", "--port", "8765"]
