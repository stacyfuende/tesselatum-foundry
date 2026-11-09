FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PROJ_NETWORK=OFF \
    FOUNDRY_DATA_DIR=/var/lib/foundry \
    FOUNDRY_WORKER_MODE=remote

WORKDIR /opt/foundry

COPY pyproject.toml README.md ./
COPY schema ./schema
COPY capabilities ./capabilities
COPY implementations ./implementations
COPY src ./src

RUN python -m pip install --no-cache-dir ".[api]" \
    && python -m compileall -q /opt/foundry/src \
    && mkdir -p /var/lib/foundry \
    && groupadd --gid 10001 foundry \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin foundry \
    && chown -R 10001:10001 /var/lib/foundry

USER 10001:10001

VOLUME ["/var/lib/foundry"]
EXPOSE 8000

ENTRYPOINT ["uvicorn", "tessellatum_foundry.api:create_app", "--factory", \
    "--host", "0.0.0.0", "--port", "8000", "--workers", "1", \
    "--no-access-log", "--limit-concurrency", "16"]
