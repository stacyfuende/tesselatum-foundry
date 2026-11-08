FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PROJ_NETWORK=OFF

WORKDIR /opt/foundry

COPY pyproject.toml README.md ./
COPY schema ./schema
COPY capabilities ./capabilities
COPY implementations ./implementations
COPY src ./src

RUN python -m pip install --no-cache-dir ".[shapely]" \
    && python -m compileall -q /opt/foundry/src \
    && mkdir -p /run/input /run/output

RUN groupadd --gid 10001 foundry \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin foundry

USER 10001:10001

EXPOSE 8080

CMD ["python", "-m", "tessellatum_foundry.worker.cli"]
