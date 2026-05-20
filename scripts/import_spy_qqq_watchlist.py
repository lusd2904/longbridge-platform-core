from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import zipfile
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
from xml.etree import ElementTree as ET

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.DbUtil import DbUtil


WATCHLIST_TABLE = "user_watchlist_stocks"
US_SUFFIX = ".US"
SPY_URL = "https://www.ssga.com/library-content/products/fund-data/etfs/us/holdings-daily-us-en-spy.xlsx"
QQQ_URL = "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/holdings/fund?idType=ticker&interval=monthly&productType=ETF"
SPY_REFERER = "https://www.ssga.com/us/en/intermediary/etfs/state-street-spdr-sp-500-etf-trust-spy"
USER_AGENT = "Mozilla/5.0"
XML_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


@dataclass(frozen=True)
class WatchlistItem:
    symbol: str
    name: str
    market: str
    asset_type: str
    category: str
    scan_before_open: int = 1
    scan_after_close: int = 1


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _normalize_symbol(raw_symbol: Any) -> str:
    token = str(raw_symbol or "").strip().upper()
    if not token:
        return ""
    if token.endswith(US_SUFFIX):
        return token
    return f"{token}{US_SUFFIX}"


def _is_supported_equity_ticker(ticker: str) -> bool:
    return bool(re.fullmatch(r"[A-Z0-9.\-]{1,16}", str(ticker or "").strip().upper()))


def _merge_categories(*values: str) -> str:
    tokens: List[str] = []
    for value in values:
        for chunk in str(value or "").split("|"):
            normalized = chunk.strip()
            if normalized and normalized not in tokens:
                tokens.append(normalized)
    return "|".join(tokens)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导入 SPY / QQQ 及其成分股到默认自选股池")
    parser.add_argument("--username", default="admin", help="目标用户名，默认 admin")
    parser.add_argument("--user-id", type=int, default=0, help="可选：直接指定 user_id，默认通过 username 查询")
    parser.add_argument("--dry-run", action="store_true", help="仅输出摘要，不写库")
    parser.add_argument("--timeout", type=int, default=30, help="网络超时秒数")
    return parser.parse_args()


def _resolve_user(args: argparse.Namespace) -> Dict[str, Any]:
    if args.user_id:
        row = DbUtil.fetch_one(
            "SELECT id, username, role, status FROM users WHERE id = %s LIMIT 1",
            (int(args.user_id),),
        )
    else:
        row = DbUtil.fetch_one(
            "SELECT id, username, role, status FROM users WHERE username = %s LIMIT 1",
            (args.username,),
        )
    if not row:
        raise RuntimeError("目标用户不存在")
    return row


def _fetch_spy_holdings(timeout: int) -> Dict[str, Any]:
    response = requests.get(
        SPY_URL,
        timeout=timeout,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": SPY_REFERER,
        },
    )
    response.raise_for_status()
    if "spreadsheetml.sheet" not in str(response.headers.get("content-type") or ""):
        raise RuntimeError("SPY 官方文件类型异常")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=True) as handle:
        handle.write(response.content)
        handle.flush()
        holdings, effective_date = _parse_spy_xlsx(Path(handle.name))

    return {
        "source": SPY_URL,
        "retrievedAt": _utc_now_iso(),
        "effectiveDate": effective_date,
        "httpStatus": response.status_code,
        "lastModified": response.headers.get("last-modified"),
        "count": len(holdings),
        "holdings": holdings,
    }


def _parse_spy_xlsx(path: Path) -> Tuple[List[Dict[str, str]], str]:
    with zipfile.ZipFile(path) as archive:
        shared_strings = _load_shared_strings(archive)
        rows = _load_sheet_rows(archive, shared_strings)

    effective_date = ""
    holdings: List[Dict[str, str]] = []
    in_holdings_table = False
    for row in rows:
        first = row.get("A", "").strip()
        if first == "Holdings:":
            effective_date = row.get("B", "").replace("As of", "").strip()
            continue
        if row.get("A", "").strip() == "Name" and row.get("B", "").strip() == "Ticker":
            in_holdings_table = True
            continue
        if not in_holdings_table:
            continue
        ticker = str(row.get("B", "")).strip().upper()
        name = str(row.get("A", "")).strip()
        if not ticker or not name or not _is_supported_equity_ticker(ticker):
            continue
        if any(marker in name for marker in ("Investing involves risk", "Distributor:", "Before investing in a fund")):
            continue
        holdings.append({
            "ticker": ticker,
            "name": name,
        })

    if not holdings:
        raise RuntimeError("未能从 SPY 官方 xlsx 解析出持仓")
    return holdings, effective_date


def _load_shared_strings(archive: zipfile.ZipFile) -> List[str]:
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    values: List[str] = []
    for item in root.findall("a:si", XML_NS):
        values.append("".join(text.text or "" for text in item.iterfind(".//a:t", XML_NS)))
    return values


def _load_sheet_rows(archive: zipfile.ZipFile, shared_strings: List[str]) -> List[Dict[str, str]]:
    root = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    sheet_data = root.find("a:sheetData", XML_NS)
    if sheet_data is None:
        return []

    rows: List[Dict[str, str]] = []
    for row in sheet_data.findall("a:row", XML_NS):
        parsed: Dict[str, str] = {}
        for cell in row.findall("a:c", XML_NS):
            ref = cell.attrib.get("r", "")
            col = "".join(ch for ch in ref if ch.isalpha())
            if not col:
                continue
            cell_type = cell.attrib.get("t")
            value_node = cell.find("a:v", XML_NS)
            value = value_node.text if value_node is not None and value_node.text is not None else ""
            if cell_type == "s" and value:
                value = shared_strings[int(value)]
            parsed[col] = value
        rows.append(parsed)
    return rows


def _fetch_qqq_holdings(timeout: int) -> Dict[str, Any]:
    response = requests.get(
        QQQ_URL,
        timeout=timeout,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    payload = response.json()
    allowed_security_types = {
        "Common Stock",
        "American Depository Receipt",
        "American Depository Receipt - NY",
    }
    holdings = []
    skipped_non_equity = 0
    skipped_missing_ticker = 0
    for item in payload.get("holdings") or []:
        ticker = str(item.get("ticker") or "").strip().upper()
        security_type = str(item.get("securityTypeName") or "").strip()
        if not ticker:
            skipped_missing_ticker += 1
            continue
        if security_type not in allowed_security_types:
            skipped_non_equity += 1
            continue
        holdings.append({
            "ticker": ticker,
            "name": str(item.get("issuerName") or item.get("ticker") or "").strip(),
        })
    if not holdings:
        raise RuntimeError("未能从 QQQ 官方 API 解析出持仓")
    return {
        "source": QQQ_URL,
        "retrievedAt": _utc_now_iso(),
        "effectiveDate": payload.get("effectiveDate") or payload.get("effectiveBusinessDate") or "",
        "httpStatus": response.status_code,
        "count": len(holdings),
        "reportedTotal": int(payload.get("totalNumberOfHoldings") or len(holdings)),
        "skippedMissingTicker": skipped_missing_ticker,
        "skippedNonEquity": skipped_non_equity,
        "holdings": holdings,
    }


def _build_target_items(spy_payload: Dict[str, Any], qqq_payload: Dict[str, Any]) -> List[WatchlistItem]:
    catalog: Dict[str, WatchlistItem] = {}

    def add_item(symbol: str, name: str, asset_type: str, category: str) -> None:
        normalized_symbol = _normalize_symbol(symbol)
        if not normalized_symbol:
            return
        incoming = WatchlistItem(
            symbol=normalized_symbol,
            name=str(name or normalized_symbol).strip(),
            market="US",
            asset_type=asset_type,
            category=category,
        )
        existing = catalog.get(normalized_symbol)
        if existing is None:
            catalog[normalized_symbol] = incoming
            return
        catalog[normalized_symbol] = WatchlistItem(
            symbol=existing.symbol,
            name=existing.name or incoming.name,
            market="US",
            asset_type="etf" if existing.asset_type == "etf" or incoming.asset_type == "etf" else "stock",
            category=_merge_categories(existing.category, incoming.category),
        )

    add_item("SPY", "SPDR S&P 500 ETF Trust", "etf", "ETF:SPY")
    add_item("QQQ", "Invesco QQQ Trust", "etf", "ETF:QQQ")

    for row in spy_payload["holdings"]:
        add_item(row["ticker"], row["name"], "stock", "ETF:SPY")
    for row in qqq_payload["holdings"]:
        add_item(row["ticker"], row["name"], "stock", "ETF:QQQ")

    return sorted(catalog.values(), key=lambda item: item.symbol)


def _load_existing_watchlist(user_id: int) -> Dict[str, Dict[str, Any]]:
    rows = DbUtil.fetch_all(
        f"""
        SELECT symbol, name, market, asset_type, category, scan_before_open, scan_after_close, added_at, updated_at
        FROM {WATCHLIST_TABLE}
        WHERE user_id = %s
        """,
        (int(user_id),),
    ) or []
    return {str(row.get("symbol") or "").strip().upper(): row for row in rows}


def _apply_items(user_id: int, targets: List[WatchlistItem], dry_run: bool) -> Dict[str, Any]:
    existing = _load_existing_watchlist(user_id)
    before_count = len(existing)
    actions: Counter[str] = Counter()

    for item in targets:
        current = existing.get(item.symbol)
        merged_category = _merge_categories(current.get("category") if current else "", item.category)
        if current:
            unchanged = (
                str(current.get("name") or "") == item.name
                and str(current.get("market") or "") == item.market
                and str(current.get("asset_type") or "") == item.asset_type
                and str(current.get("category") or "") == merged_category
                and int(current.get("scan_before_open") or 0) == item.scan_before_open
                and int(current.get("scan_after_close") or 0) == item.scan_after_close
            )
            if unchanged:
                actions["skipped"] += 1
                continue
            actions["updated"] += 1
        else:
            actions["inserted"] += 1

        if dry_run:
            continue

        DbUtil.execute(
            f"""
            INSERT INTO {WATCHLIST_TABLE} (
                user_id,
                symbol,
                name,
                market,
                asset_type,
                category,
                scan_before_open,
                scan_after_close,
                added_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON DUPLICATE KEY UPDATE
                name = VALUES(name),
                market = VALUES(market),
                asset_type = VALUES(asset_type),
                category = VALUES(category),
                scan_before_open = VALUES(scan_before_open),
                scan_after_close = VALUES(scan_after_close),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                int(user_id),
                item.symbol,
                item.name,
                item.market,
                item.asset_type,
                merged_category,
                item.scan_before_open,
                item.scan_after_close,
            ),
        )

    final_rows = _load_existing_watchlist(user_id) if not dry_run else existing
    return {
        "beforeCount": before_count,
        "afterCount": len(final_rows) if not dry_run else before_count + actions["inserted"],
        "inserted": actions["inserted"],
        "updated": actions["updated"],
        "skipped": actions["skipped"],
    }


def _sample_presence(user_id: int, symbols: Iterable[str]) -> Dict[str, bool]:
    normalized = [_normalize_symbol(symbol) for symbol in symbols if _normalize_symbol(symbol)]
    if not normalized:
        return {}
    placeholders = ", ".join(["%s"] * len(normalized))
    rows = DbUtil.fetch_all(
        f"SELECT symbol FROM {WATCHLIST_TABLE} WHERE user_id = %s AND symbol IN ({placeholders})",
        (int(user_id), *normalized),
    ) or []
    existing = {str(row.get("symbol") or "").strip().upper() for row in rows}
    return {symbol: symbol in existing for symbol in normalized}


def main() -> None:
    args = _parse_args()
    user = _resolve_user(args)
    spy_payload = _fetch_spy_holdings(args.timeout)
    qqq_payload = _fetch_qqq_holdings(args.timeout)
    targets = _build_target_items(spy_payload, qqq_payload)
    summary = _apply_items(int(user["id"]), targets, args.dry_run)
    samples = _sample_presence(int(user["id"]), ["SPY", "QQQ", "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "BRK.B"])

    result = {
        "user": {
            "id": int(user["id"]),
            "username": user.get("username"),
            "role": user.get("role"),
            "status": user.get("status"),
        },
        "dryRun": bool(args.dry_run),
        "sources": {
            "SPY": {
                "source": spy_payload["source"],
                "retrievedAt": spy_payload["retrievedAt"],
                "effectiveDate": spy_payload["effectiveDate"],
                "httpStatus": spy_payload["httpStatus"],
                "lastModified": spy_payload["lastModified"],
                "count": spy_payload["count"],
            },
            "QQQ": {
                "source": qqq_payload["source"],
                "retrievedAt": qqq_payload["retrievedAt"],
                "effectiveDate": qqq_payload["effectiveDate"],
                "httpStatus": qqq_payload["httpStatus"],
                "count": qqq_payload["count"],
                "reportedTotal": qqq_payload["reportedTotal"],
                "skippedMissingTicker": qqq_payload["skippedMissingTicker"],
                "skippedNonEquity": qqq_payload["skippedNonEquity"],
            },
        },
        "targets": {
            "totalUniqueSymbols": len(targets),
            "assetTypeBreakdown": dict(Counter(item.asset_type for item in targets)),
            "categorySamples": {
                item.symbol: item.category
                for item in targets
                if item.symbol in {"SPY.US", "QQQ.US", "NVDA.US", "AAPL.US", "MSFT.US", "BRK.B.US"}
            },
        },
        "writeSummary": summary,
        "samples": samples,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
