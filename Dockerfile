FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Runtime-only OS deps. No build toolchain: every Python dependency resolves to
# a prebuilt manylinux wheel (verified) and the longbridge CLI is a static
# binary, so build-essential/gcc would only add ~250MB of dead weight.
# curl is required by the compose healthchecks and the longbridge installer.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://open.longbridge.cn/longbridge/longbridge-terminal/install | sh

COPY requirements.services.txt ./
RUN pip install --no-cache-dir -r requirements.services.txt

COPY . .

# Precompile to .pyc up front so the first request of every worker doesn't pay
# the compile cost (PYTHONDONTWRITEBYTECODE only suppresses implicit writes).
RUN python -m compileall -q apps shared core utils config || true

CMD ["scripts/docker_service_entrypoint.sh", "apps/market/market-service/src"]
