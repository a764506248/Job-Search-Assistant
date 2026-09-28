FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

RUN mkdir -p /data

EXPOSE 8765

CMD ["uvicorn", "job_search_assistant.main:app", "--host", "0.0.0.0", "--port", "8765"]
