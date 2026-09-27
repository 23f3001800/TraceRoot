FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY traceroot/ traceroot/
RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --home-dir /data --shell /usr/sbin/nologin traceroot \
    && mkdir -p /data \
    && chown 10001:10001 /data
USER 10001:10001
ENTRYPOINT ["python", "-m", "traceroot", "monitor"]
