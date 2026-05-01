FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/apps/api:/app/packages/contracts:/app/packages/safety:/app/packages/robot_adapters

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[dev]"

COPY apps ./apps
COPY packages ./packages

EXPOSE 8000

CMD ["uvicorn", "g1_bobby_api.app:app", "--host", "0.0.0.0", "--port", "8000"]

