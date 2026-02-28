FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# system deps for running basic tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /app/pyproject.toml

# Install dependencies. Default is "prod" (includes SWE-bench eval deps).
# For training/HF patcher add build-arg: PIP_EXTRAS="prod,train"
ARG PIP_EXTRAS="prod"
RUN pip install --no-cache-dir -U pip && pip install --no-cache-dir ".[${PIP_EXTRAS}]"

COPY app /app/app

EXPOSE 8000

CMD ["bash", "-lc", "python -m app.migrate && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
