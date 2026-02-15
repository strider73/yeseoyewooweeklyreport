FROM python:3.11-slim

WORKDIR /app

# Install dependencies only — scripts mounted at runtime
RUN pip install --no-cache-dir "psycopg2-binary>=2.9" "requests>=2.28"

CMD ["python3", "reports/notion_sync.py"]
