# Dockerfile per DELTA Orchestrator (multi-platform)
FROM python:3.11-slim

# Abilita build multi-arch
ARG TARGETARCH

WORKDIR /app

COPY . /app

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

EXPOSE 8000

CMD ["uvicorn", "delta_orchestrator.api.routes:router", "--host", "0.0.0.0", "--port", "8000"]
