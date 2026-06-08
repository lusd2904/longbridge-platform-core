#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict


ANOMALY_PATTERNS = {
    "Traceback": re.compile(r"Traceback", re.IGNORECASE),
    "ERROR": re.compile(r"ERROR", re.IGNORECASE),
    "request_too_many_symbols": re.compile(r"request too many symbols", re.IGNORECASE),
    "websocket_send": re.compile(r"WebSocket send failed|websocket send", re.IGNORECASE),
    "circuit_open_cn": re.compile(r"熔断器打开", re.IGNORECASE),
    "rate_limit": re.compile(r"rate limit", re.IGNORECASE),
    "rateLimited_true": re.compile(r"rateLimited=true", re.IGNORECASE),
    "raw_timeout": re.compile(
        r"Read timed out|Max retries exceeded|Connection timed out|timeout=",
        re.IGNORECASE,
    ),
    "connection_refused": re.compile(r"Connection refused", re.IGNORECASE),
    "longbridge_cli_polling": re.compile(
        r"CLI push polling degraded|Longbridge CLI push polling",
        re.IGNORECASE,
    ),
}
IGNORED_ANOMALY_LINE_PATTERNS = {
    "ERROR": [
        re.compile(r"<bf>.*\bbf-error-rate\b", re.IGNORECASE),
    ],
}
HANDLED_TIMEOUT_PATTERN = re.compile(r"OpenAI-compatible provider timeout handled", re.IGNORECASE)
HTTP_STATUS_PATTERN = re.compile(r'" (\d{3}) ')


def _line_is_ignored_anomaly(name: str, line: str) -> bool:
    return any(pattern.search(line) for pattern in IGNORED_ANOMALY_LINE_PATTERNS.get(name, ()))


def _count_anomalies(text: str) -> dict[str, int]:
    anomalies = {name: 0 for name in ANOMALY_PATTERNS}
    for line in text.splitlines():
        for name, pattern in ANOMALY_PATTERNS.items():
            if _line_is_ignored_anomaly(name, line):
                continue
            anomalies[name] += len(pattern.findall(line))
    return anomalies


def parse_log_text(text: str) -> dict:
    status_counts: Dict[str, int] = {}
    for match in HTTP_STATUS_PATTERN.finditer(text):
        status = match.group(1)
        status_counts[status] = status_counts.get(status, 0) + 1

    anomalies = _count_anomalies(text)
    handled_provider_timeout = len(HANDLED_TIMEOUT_PATTERN.findall(text))
    http_total = sum(status_counts.values())
    server_5xx = sum(count for status, count in status_counts.items() if status.startswith("5"))
    client_cancel_499 = int(status_counts.get("499", 0))

    return {
        "status_counts": dict(sorted(status_counts.items())),
        "http_total": http_total,
        "server_5xx": server_5xx,
        "client_cancel_499": client_cancel_499,
        "client_cancel_499_rate": (client_cancel_499 / http_total) if http_total else 0.0,
        "anomalies": anomalies,
        "handled_provider_timeout": handled_provider_timeout,
        "handled_provider_timeout_rate": (handled_provider_timeout / http_total) if http_total else 0.0,
    }


def evaluate_report(report: dict, *, max_499_rate: float) -> list[str]:
    failures: list[str] = []
    if report["server_5xx"]:
        failures.append(f"server_5xx={report['server_5xx']}")
    for name, count in report["anomalies"].items():
        if count:
            failures.append(f"{name}={count}")
    if report["client_cancel_499_rate"] > max_499_rate:
        failures.append(
            "client_cancel_499_rate="
            f"{report['client_cancel_499_rate']:.4f} exceeds {max_499_rate:.4f}"
        )
    return failures


def read_input(path: str | None) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8", errors="ignore")
    return sys.stdin.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check platform Docker logs for release-blocking anomalies.")
    parser.add_argument("logfile", nargs="?", help="Log file to scan. Reads stdin when omitted.")
    parser.add_argument(
        "--max-499-rate",
        type=float,
        default=0.05,
        help="Maximum allowed HTTP 499 client-cancel rate. Default: 0.05.",
    )
    args = parser.parse_args(argv)

    report = parse_log_text(read_input(args.logfile))
    failures = evaluate_report(report, max_499_rate=max(float(args.max_499_rate), 0.0))
    report["ok"] = not failures
    report["failures"] = failures
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
