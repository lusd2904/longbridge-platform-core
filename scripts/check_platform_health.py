from __future__ import annotations

import json
import os
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


SERVICE_PORTS = {
    "api-gateway": int(os.getenv("REF_GATEWAY_PORT", "5101")),
    "user-center": int(os.getenv("REF_USER_CENTER_PORT", "8101")),
    "market-service": int(os.getenv("REF_MARKET_SERVICE_PORT", "8102")),
    "analysis-service": int(os.getenv("REF_ANALYSIS_SERVICE_PORT", "8103")),
    "strategy-service": int(os.getenv("REF_STRATEGY_SERVICE_PORT", "8104")),
    "agno-sidecar": int(os.getenv("REF_AGNO_SIDECAR_PORT", "3200")),
    "trade-service": int(os.getenv("REF_TRADE_SERVICE_PORT", "8105")),
    "scheduler-service": int(os.getenv("REF_SCHEDULER_SERVICE_PORT", "8107")),
    "risk-service": int(os.getenv("REF_RISK_SERVICE_PORT", "8108")),
}

REQUIRED_FIELDS = {"service", "version", "status", "status_text", "port", "checked_at", "deps", "brokerConnectivity"}
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REF_HEALTH_CHECK_TIMEOUT_SECONDS", "2.0"))
REQUEST_RETRIES = max(1, int(os.getenv("REF_HEALTH_CHECK_RETRIES", "3")))
RETRY_DELAY_SECONDS = max(0.0, float(os.getenv("REF_HEALTH_CHECK_RETRY_DELAY_SECONDS", "0.25")))


def fetch_json(url: str, *, timeout_seconds: float = REQUEST_TIMEOUT_SECONDS) -> dict:
    with urlopen(url, timeout=timeout_seconds) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_json_with_retries(url: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(REQUEST_RETRIES):
        try:
            return fetch_json(url)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < REQUEST_RETRIES - 1 and RETRY_DELAY_SECONDS > 0:
                time.sleep(RETRY_DELAY_SECONDS)
    assert last_error is not None
    raise last_error


def main() -> int:
    failures = []
    for service, port in SERVICE_PORTS.items():
        url = f"http://127.0.0.1:{port}/health"
        try:
            payload = fetch_json_with_retries(url)
        except URLError as exc:
            failures.append(f"{service}: unreachable ({exc})")
            continue
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{service}: invalid payload ({exc})")
            continue

        missing = sorted(REQUIRED_FIELDS - set(payload.keys()))
        if missing:
            failures.append(f"{service}: missing fields {', '.join(missing)}")
            continue

        if str(payload.get("service")) != service:
            failures.append(f"{service}: service field mismatch ({payload.get('service')})")

    if failures:
        for failure in failures:
            print(failure)
        return 1

    print("platform health contract ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
