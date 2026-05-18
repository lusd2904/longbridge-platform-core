FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl build-essential ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN curl -sSL https://open.longbridge.cn/longbridge/longbridge-terminal/install | sh

COPY requirements.services.txt ./
RUN pip install --no-cache-dir -r requirements.services.txt

COPY . .

CMD ["scripts/docker_service_entrypoint.sh", "apps/market/market-service/src"]
