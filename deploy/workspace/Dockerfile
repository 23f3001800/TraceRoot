FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8080
WORKDIR /app
COPY pyproject.toml requirements.txt ./
COPY traceroot/ traceroot/
COPY ui/ ui/
RUN pip install --no-cache-dir . \
    && useradd --system --uid 10001 --home-dir /data --shell /usr/sbin/nologin traceroot \
    && mkdir -p /data/workspace \
    && chown -R 10001:10001 /data

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["python", "-m", "traceroot", "workspace-ui", "--workspace-dir", "/data/workspace", "--host", "0.0.0.0", "--port", "8080"]
