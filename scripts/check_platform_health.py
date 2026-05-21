from __future__ import annotations

import json
import os
import sys
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


def fetch_json(url: str) -> dict:
    with urlopen(url, timeout=2.0) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    failures = []
    for service, port in SERVICE_PORTS.items():
        url = f"http://127.0.0.1:{port}/health"
        try:
            payload = fetch_json(url)
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
