from __future__ import annotations

import asyncio
import copy
import logging
import os
import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException, WebSocket

REFACTOR_ROOT = Path(__file__).resolve().parents[4]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.market.module_shared import (
    SDK_PACKAGE,
    ContentContext,
    DbUtil,
    HistoricalMarketDataService,
    QuoteContext,
    QuoteSnapshotService,
    SymbolContentCacheService,
    bootstrap_runtime,
    build_content_context,
    build_quote_context,
    create_service_app,
    decode_token,
    iter_stock_pool_tables,
    resolve_endpoints,
    resolve_region,
    service_port,
    to_plain,
)

bootstrap_runtime()

from push_hub import push_hub
from watchlist_service import WatchlistService

LOGGER = logging.getLogger(__name__)

LONGBRIDGE_PULL_CATALOG = [
    {
        "section": "行情与交易",
        "items": [
            {"name": "实时行情", "capabilityType": "quote", "sdkMethod": "quote"},
            {"name": "深度盘口", "capabilityType": "quote", "sdkMethod": "depth"},
            {"name": "逐笔成交", "capabilityType": "quote", "sdkMethod": "trades"},
            {"name": "经纪商明细", "capabilityType": "quote", "sdkMethod": "brokers"},
            {"name": "资金流向", "capabilityType": "quote", "sdkMethod": "capital_flow"},
        ],
    }
]


@asynccontextmanager
async def market_service_lifespan(_: Any):
    push_hub.bind_loop(asyncio.get_running_loop())
    SymbolContentCacheService.ensure_schema()
    QuoteSnapshotService.ensure_schema()
    WatchlistService.ensure_schema()
    await asyncio.to_thread(HistoricalMarketDataService.get_backfill_status)
    for market in ("US", "CN", "HK"):
        await asyncio.to_thread(
            _get_history_market_expectation,
            start_date=_HISTORY_COVERAGE_START_DATE,
            market=market,
        )
    yield


app = create_service_app(
    title="Refactor V2 Market Service",
    version="0.3.0",
    description="Phase 1 live service for market history, indicators, Longbridge quote/content/push APIs and scan datasets.",
    lifespan=market_service_lifespan,
)
PORT = service_port("REF_MARKET_SERVICE_PORT", 8102)
_TRADING_SESSION_CACHE: dict[str, Any] = {"expires_at": 0.0, "payload": None}
_TRADING_SESSION_TTL_SECONDS = 90
_LIVE_MARKET_CACHE_TTL_SECONDS = 6
_LIVE_MARKET_STALE_SECONDS = 45
_SYMBOL_OVERVIEW_CACHE_TTL_SECONDS = 10
_HISTORY_COVERAGE_START_DATE = date(2024, 1, 1)
_HISTORY_COVERAGE_STATUSES = {"complete", "partial", "missing"}
_HISTORY_COVERAGE_CACHE_TTL_SECONDS = 300
_HISTORY_COVERAGE_CACHE_LOCK = threading.Lock()
_HISTORY_COVERAGE_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_HISTORY_MARKET_EXPECTATION_CACHE_TTL_SECONDS = 300
_HISTORY_MARKET_EXPECTATION_CACHE_LOCK = threading.Lock()
_HISTORY_MARKET_EXPECTATION_CACHE: dict[tuple[str, str], dict[str, Any]] = {}
_HISTORY_MARKET_EXPECTATION_ANCHORS: dict[str, tuple[str, ...]] = {
    "US": ("AAPL.US", "SPY.US", "QQQ.US", "NVDA.US"),
    "CN": ("000001.SH", "399001.SZ", "510300.SH", "510050.SH"),
    "HK": ("00700.HK", "2800.HK", "09988.HK", "00005.HK"),
}
_READ_MODEL_TABLE_EXISTS_CACHE_LOCK = threading.Lock()
_READ_MODEL_TABLE_EXISTS_CACHE: dict[str, bool] = {}
_HISTORY_BACKFILL_LOCK = threading.Lock()
_HISTORY_BACKFILL_SYMBOLS: set[str] = set()
_LIVE_MARKET_CACHE_LOCK = threading.Lock()
_LIVE_MARKET_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}
_LIVE_FALLBACK_LOG_INTERVAL_SECONDS = max(
    5.0,
    float(os.getenv("REF_MARKET_LIVE_FALLBACK_LOG_INTERVAL_SECONDS", "60") or "60"),
)
_LIVE_FALLBACK_LOG_LOCK = threading.Lock()
_LIVE_FALLBACK_LAST_LOGS: dict[str, float] = {}


def _warn_live_fallback_once(key: str, message: str, *args: Any) -> None:
    now = time.monotonic()
    with _LIVE_FALLBACK_LOG_LOCK:
        last_log = float(_LIVE_FALLBACK_LAST_LOGS.get(key) or 0.0)
        if now - last_log >= _LIVE_FALLBACK_LOG_INTERVAL_SECONDS:
            _LIVE_FALLBACK_LAST_LOGS[key] = now
            LOGGER.warning(message, *args)
            return
    LOGGER.debug(message, *args)


def _as_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_symbols(raw_values: list[str] | None, merged: str | None = None) -> list[str]:
    items: list[str] = []
    for raw in raw_values or []:
        for chunk in str(raw or "").split(","):
            symbol = chunk.strip()
            if symbol and symbol not in items:
                items.append(symbol)
    if merged:
        for chunk in str(merged or "").split(","):
            symbol = chunk.strip()
            if symbol and symbol not in items:
                items.append(symbol)
    return items


def _build_market_history_meta(
    *,
    symbols: list[str],
    timeframe: str,
    limit: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    series = payload.get("series") if isinstance(payload.get("series"), list) else []
    snapshot_candidates: list[str] = []
    for item in series:
        if not isinstance(item, dict):
            continue
        summary = item.get("summary") if isinstance(item.get("summary"), dict) else {}
        snapshot_candidates.extend(
            [
                str(summary.get("latestDate") or ""),
                str(item.get("updatedAt") or ""),
            ]
        )
    snapshot_at = max([value for value in snapshot_candidates if value], default=None)
    return {
        "readModel": "market-history",
        "defaultMode": "database",
        "dataSource": "snapshot",
        "snapshotAt": snapshot_at,
        "sources": {
            "history": "historical_market_data",
            "indicators": "indicator_snapshots",
        },
        "count": len(series),
        "query": {
            "symbols": symbols,
            "timeframe": str(timeframe or "daily"),
            "limit": int(limit),
        },
        "realtimeOverlay": [],
    }


def _build_market_insight_meta(
    *,
    data: list[dict[str, Any]],
    market: str,
    generated_at: str,
) -> dict[str, Any]:
    snapshot_candidates: list[str] = []
    for item in data:
        if isinstance(item, dict):
            snapshot_candidates.append(str(item.get("generatedAt") or ""))
    snapshot_at = max([value for value in snapshot_candidates if value], default=None)
    return {
        "readModel": "market-insights",
        "defaultMode": "database",
        "dataSource": "snapshot",
        "snapshotAt": snapshot_at,
        "sources": {
            "insights": "market_insight_snapshots",
            "quotes": "quote_snapshots",
        },
        "market": str(market or "").strip().upper() or None,
        "generatedAt": str(generated_at or "").strip() or None,
        "count": len(data),
        "realtimeOverlay": ["quote"],
    }


def _build_stock_pool_meta(
    *,
    market: str,
    search: str,
    group_id: str,
    page: int,
    page_size: int,
    total: int,
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    updated_candidates = [
        str(item.get("updated_at") or item.get("updatedAt") or "") for item in items if isinstance(item, dict)
    ]
    snapshot_at = max([value for value in updated_candidates if value], default=None)
    return {
        "readModel": "stock-pool",
        "defaultMode": "database",
        "dataSource": "market_universe",
        "snapshotAt": snapshot_at,
        "sources": {
            "universe": "market_universe",
            "quotes": "longbridge-live",
        },
        "market": str(market or "").strip().upper() or "ALL",
        "query": {
            "search": str(search or "").strip() or None,
            "groupId": str(group_id or "").strip() or None,
            "page": int(page),
            "pageSize": int(page_size),
        },
        "count": len(items),
        "total": int(total),
        "realtimeOverlay": ["quote"],
    }


def _read_model_table_exists(table_name: str) -> bool:
    normalized_table_name = str(table_name or "").strip()
    if not normalized_table_name:
        return False
    with _READ_MODEL_TABLE_EXISTS_CACHE_LOCK:
        if _READ_MODEL_TABLE_EXISTS_CACHE.get(normalized_table_name):
            return True
    row = DbUtil.fetch_one(
        "SELECT 1 AS present FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
        (normalized_table_name,),
    )
    exists = bool(row)
    if exists:
        with _READ_MODEL_TABLE_EXISTS_CACHE_LOCK:
            _READ_MODEL_TABLE_EXISTS_CACHE[normalized_table_name] = True
    return exists


def _normalize_history_coverage_status(raw_value: str) -> str:
    value = str(raw_value or "").strip().lower()
    if not value:
        return ""
    if value not in _HISTORY_COVERAGE_STATUSES:
        raise HTTPException(status_code=400, detail="status 仅支持 complete / partial / missing")
    return value


def _isoformat_optional(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _build_history_coverage_meta(
    *,
    start_date: date,
    search: str,
    status: str,
    page: int,
    page_size: int,
    total: int,
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "readModel": "market-history-coverage",
        "defaultMode": "database",
        "dataSource": "snapshot",
        "snapshotAt": summary.get("lastUpdated"),
        "sources": {
            "universe": "market_universe",
            "history": "historical_market_data",
            "historyTable": HistoricalMarketDataService.TABLE_NAME,
        },
        "query": {
            "search": str(search or "").strip() or None,
            "status": str(status or "").strip() or None,
            "page": int(page),
            "pageSize": int(page_size),
            "expectedStart": start_date.isoformat(),
        },
        "total": int(total),
    }


def _build_history_coverage_universe_sql(user_id: int) -> tuple[str, tuple[Any, ...]]:
    table_configs = iter_stock_pool_tables("all")
    clauses: list[str] = []
    params: list[Any] = []
    for table_config in table_configs:
        table_name = str(table_config.get("table") or "").strip()
        name_field = str(table_config.get("name_field") or "").strip()
        market = str(table_config.get("market") or "").strip().upper()
        asset_type = str(table_config.get("type") or "").strip().lower()
        if not table_name or not name_field or not market or not _read_model_table_exists(table_name):
            continue
        priority = 0 if asset_type == "stock" else 1
        clauses.append(
            f"""
            SELECT
                symbol,
                COALESCE(NULLIF(TRIM({name_field}), ''), symbol) AS display_name,
                '{market}' AS market,
                updated_at AS universe_updated_at,
                {priority} AS source_priority
            FROM {table_name}
            WHERE is_active = 1
              AND user_id = %s
            """
        )
        params.append(int(user_id))
    return "\nUNION ALL\n".join(clauses), tuple(params)


def _empty_history_coverage_payload(start_date: date) -> dict[str, Any]:
    return {
        "summary": {
            "expectedStart": start_date.isoformat(),
            "expectedEnd": None,
            "markets": [],
            "filteredTotal": 0,
            "counts": {key: 0 for key in sorted(_HISTORY_COVERAGE_STATUSES)},
            "totalRows": 0,
            "totalMissingDays": 0,
            "lastUpdated": None,
        },
        "items": [],
        "total": 0,
    }


def _normalize_exact_history_coverage_symbol(search: str) -> tuple[str, bool]:
    search_value = str(search or "").strip()
    if not search_value:
        return "", False
    if "." not in search_value and not re.fullmatch(r"[A-Za-z0-9\-]{1,16}", search_value):
        return "", False
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(search_value)
    if not re.fullmatch(r"[A-Z0-9.\-]{1,32}\.(US|HK|SH|SZ|BJ)", normalized_symbol):
        return "", False
    return normalized_symbol, "." in search_value


def _coerce_history_coverage_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _load_exact_history_coverage_universe_rows(symbol: str, user_id: int) -> list[dict[str, Any]]:
    table_configs = iter_stock_pool_tables("all")
    rows: list[dict[str, Any]] = []
    for table_config in table_configs:
        table_name = str(table_config.get("table") or "").strip()
        name_field = str(table_config.get("name_field") or "").strip()
        market = str(table_config.get("market") or "").strip().upper()
        asset_type = str(table_config.get("type") or "").strip().lower()
        if not table_name or not name_field or not market or not _read_model_table_exists(table_name):
            continue
        priority = 0 if asset_type == "stock" else 1
        table_rows = (
            DbUtil.fetch_all(
                f"""
            SELECT
                symbol,
                COALESCE(NULLIF(TRIM({name_field}), ''), symbol) AS display_name,
                '{market}' AS market,
                updated_at AS universe_updated_at,
                {priority} AS source_priority
            FROM {table_name}
            WHERE is_active = 1
              AND user_id = %s
              AND symbol = %s
            ORDER BY
                updated_at DESC
            LIMIT 1
            """,
                (int(user_id), symbol),
            )
            or []
        )
        rows.extend(table_rows)

    return sorted(
        rows,
        key=lambda row: (
            int(row.get("source_priority") or 0),
            str(row.get("market") or ""),
            str(row.get("symbol") or ""),
        ),
    )


def _get_history_market_expectation(*, start_date: date, market: str) -> dict[str, Any]:
    normalized_market = str(market or "").strip().upper()
    if not normalized_market:
        return {}

    cache_key = (start_date.isoformat(), normalized_market)
    now = time.monotonic()
    with _HISTORY_MARKET_EXPECTATION_CACHE_LOCK:
        cached = _HISTORY_MARKET_EXPECTATION_CACHE.get(cache_key)
        if cached and float(cached.get("expires_at") or 0.0) > now:
            return copy.deepcopy(cached.get("payload") or {})

    history_table = HistoricalMarketDataService.TABLE_NAME
    anchors = _HISTORY_MARKET_EXPECTATION_ANCHORS.get(normalized_market, ())
    row: dict[str, Any] = {}
    if anchors:
        placeholders = ", ".join(["%s"] * len(anchors))
        row = (
            DbUtil.fetch_one(
                f"""
            SELECT
                market,
                MIN(trade_date) AS expected_start_trade_date,
                MAX(trade_date) AS expected_end,
                COUNT(DISTINCT trade_date) AS expected_days
            FROM (
                SELECT market, trade_date
                FROM {history_table} FORCE INDEX (idx_symbol_date)
                WHERE symbol IN ({placeholders})
                  AND market = %s
                  AND trade_date >= %s
            ) AS anchor_trade_dates
            GROUP BY market
            """,
                (*anchors, normalized_market, start_date),
            )
            or {}
        )
    if not row:
        row = (
            DbUtil.fetch_one(
                f"""
        SELECT
            market,
            MIN(trade_date) AS expected_start_trade_date,
            MAX(trade_date) AS expected_end,
            COUNT(DISTINCT trade_date) AS expected_days
        FROM {history_table} FORCE INDEX (idx_market_date)
        WHERE market = %s
          AND trade_date >= %s
        GROUP BY market
        """,
                (normalized_market, start_date),
            )
            or {}
        )
    payload = {
        "market": row.get("market") or normalized_market,
        "expected_start_trade_date": row.get("expected_start_trade_date"),
        "expected_end": row.get("expected_end"),
        "expected_days": int(row.get("expected_days") or 0),
    }
    with _HISTORY_MARKET_EXPECTATION_CACHE_LOCK:
        _HISTORY_MARKET_EXPECTATION_CACHE[cache_key] = {
            "expires_at": now + _HISTORY_MARKET_EXPECTATION_CACHE_TTL_SECONDS,
            "payload": copy.deepcopy(payload),
        }
    return payload


def _build_history_coverage_sql(
    *,
    user_id: int,
    start_date: date,
    search: str,
    status: str,
) -> tuple[str, tuple[Any, ...]]:
    universe_sql, universe_params = _build_history_coverage_universe_sql(user_id)
    if not universe_sql:
        return "", ()

    history_table = HistoricalMarketDataService.TABLE_NAME
    params: list[Any] = list(universe_params)
    search_clause = ""
    search_value = str(search or "").strip()
    if search_value:
        search_clause = "AND (symbol LIKE %s OR display_name LIKE %s)"
        like_value = f"%{search_value}%"
        params.extend([like_value, like_value])

    select_sql = f"""
        WITH universe_union AS (
            {universe_sql}
        ),
        ranked_universe AS (
            SELECT
                symbol,
                display_name,
                market,
                universe_updated_at,
                ROW_NUMBER() OVER (
                    PARTITION BY symbol
                    ORDER BY source_priority ASC, market ASC, symbol ASC
                ) AS row_rank
            FROM universe_union
        ),
        base_universe AS (
            SELECT
                symbol,
                display_name,
                market,
                universe_updated_at
            FROM ranked_universe
            WHERE row_rank = 1
        ),
        filtered_universe AS (
            SELECT
                symbol,
                display_name,
                market,
                universe_updated_at
            FROM base_universe
            WHERE 1 = 1
              {search_clause}
        ),
        history_agg AS (
            SELECT
                history.symbol,
                history.market,
                MIN(history.trade_date) AS first_date,
                MAX(history.trade_date) AS latest_date,
                COUNT(*) AS row_count,
                MAX(history.updated_at) AS last_updated
            FROM {history_table} history
            INNER JOIN filtered_universe
              ON filtered_universe.symbol = history.symbol
             AND filtered_universe.market = history.market
            WHERE history.trade_date >= %s
            GROUP BY history.symbol, history.market
        ),
        market_expectation AS (
            SELECT
                history.market,
                MIN(history.trade_date) AS expected_start_trade_date,
                MAX(history.trade_date) AS expected_end,
                COUNT(DISTINCT history.trade_date) AS expected_days
            FROM {history_table} history
            INNER JOIN (
                SELECT DISTINCT market
                FROM filtered_universe
            ) target_markets
              ON target_markets.market = history.market
            WHERE history.trade_date >= %s
            GROUP BY history.market
        )
        SELECT *
        FROM (
            SELECT
                filtered_universe.symbol,
                filtered_universe.display_name AS name,
                filtered_universe.market,
                history_agg.first_date,
                history_agg.latest_date,
                COALESCE(history_agg.row_count, 0) AS row_count,
                %s AS expected_start,
                market_expectation.expected_start_trade_date,
                market_expectation.expected_end,
                COALESCE(market_expectation.expected_days, 0) AS expected_days,
                CASE
                    WHEN COALESCE(history_agg.row_count, 0) = 0 THEN 'missing'
                    WHEN COALESCE(market_expectation.expected_days, 0) > 0
                         AND COALESCE(history_agg.row_count, 0) >= COALESCE(market_expectation.expected_days, 0)
                         AND history_agg.first_date <= market_expectation.expected_start_trade_date
                         AND history_agg.latest_date >= market_expectation.expected_end
                    THEN 'complete'
                    ELSE 'partial'
                END AS status,
                GREATEST(COALESCE(market_expectation.expected_days, 0) - COALESCE(history_agg.row_count, 0), 0) AS missing_days,
                COALESCE(history_agg.last_updated, filtered_universe.universe_updated_at) AS last_updated
            FROM filtered_universe
            LEFT JOIN history_agg
              ON history_agg.symbol = filtered_universe.symbol
             AND history_agg.market = filtered_universe.market
            LEFT JOIN market_expectation
              ON market_expectation.market = filtered_universe.market
        ) AS coverage
        WHERE 1 = 1
    """
    params.extend([start_date, start_date, start_date])

    status_value = _normalize_history_coverage_status(status)
    if status_value:
        select_sql += " AND coverage.status = %s"
        params.append(status_value)

    return select_sql, tuple(params)


def _load_exact_history_coverage_payload(
    *,
    user_id: int,
    start_date: date,
    search: str,
    status: str,
    page: int,
    page_size: int,
) -> dict[str, Any] | None:
    exact_symbol, explicit_market_suffix = _normalize_exact_history_coverage_symbol(search)
    if not exact_symbol:
        return None

    universe_rows = _load_exact_history_coverage_universe_rows(exact_symbol, user_id)
    if not universe_rows:
        if explicit_market_suffix:
            return _empty_history_coverage_payload(start_date)
        return None

    target_universe = universe_rows[0]
    target_market = str(target_universe.get("market") or "").strip().upper()
    history_table = HistoricalMarketDataService.TABLE_NAME
    history_row = (
        DbUtil.fetch_one(
            f"""
        SELECT
            history.symbol,
            history.market,
            MIN(history.trade_date) AS first_date,
            MAX(history.trade_date) AS latest_date,
            COUNT(*) AS row_count,
            MAX(history.updated_at) AS last_updated
        FROM {history_table} history
        WHERE history.symbol = %s
          AND history.market = %s
          AND history.trade_date >= %s
        GROUP BY history.symbol, history.market
        """,
            (exact_symbol, target_market, start_date),
        )
        or {}
    )
    expectation_row = _get_history_market_expectation(start_date=start_date, market=target_market)

    row_count = int(history_row.get("row_count") or 0)
    expected_days = int(expectation_row.get("expected_days") or 0)
    first_date = _coerce_history_coverage_date(history_row.get("first_date"))
    latest_date = _coerce_history_coverage_date(history_row.get("latest_date"))
    expected_first_trade_date = _coerce_history_coverage_date(expectation_row.get("expected_start_trade_date"))
    expected_end = _coerce_history_coverage_date(expectation_row.get("expected_end"))
    if row_count <= 0:
        coverage_status = "missing"
    elif (
        expected_days > 0
        and row_count >= expected_days
        and first_date is not None
        and latest_date is not None
        and expected_first_trade_date is not None
        and expected_end is not None
        and first_date <= expected_first_trade_date
        and latest_date >= expected_end
    ):
        coverage_status = "complete"
    else:
        coverage_status = "partial"
    missing_days = max(expected_days - row_count, 0)
    coverage_rows = [
        {
            "symbol": target_universe.get("symbol"),
            "name": target_universe.get("display_name") or target_universe.get("symbol"),
            "market": target_market,
            "first_date": history_row.get("first_date"),
            "latest_date": history_row.get("latest_date"),
            "row_count": row_count,
            "expected_start": start_date,
            "expected_start_trade_date": expectation_row.get("expected_start_trade_date"),
            "expected_end": expectation_row.get("expected_end"),
            "expected_days": expected_days,
            "status": coverage_status,
            "missing_days": missing_days,
            "last_updated": history_row.get("last_updated") or target_universe.get("universe_updated_at"),
        }
    ]

    status_value = _normalize_history_coverage_status(status)
    filtered_rows = [
        row for row in coverage_rows if not status_value or str(row.get("status") or "").strip().lower() == status_value
    ]
    total = len(filtered_rows)
    offset = max(int(page) - 1, 0) * int(page_size)
    item_rows = filtered_rows[offset : offset + int(page_size)]

    counts = {key: 0 for key in sorted(_HISTORY_COVERAGE_STATUSES)}
    total_rows = 0
    total_missing_days = 0
    expected_end_values: list[Any] = []
    last_updated_values: list[Any] = []
    for row in filtered_rows:
        row_status = str(row.get("status") or "missing").strip().lower()
        counts[row_status if row_status in counts else "missing"] += 1
        total_rows += int(row.get("row_count") or 0)
        total_missing_days += int(row.get("missing_days") or 0)
        if row.get("expected_end") not in (None, ""):
            expected_end_values.append(row.get("expected_end"))
        if row.get("last_updated") not in (None, ""):
            last_updated_values.append(row.get("last_updated"))

    markets = [
        {
            "market": target_market,
            "expectedStart": start_date.isoformat(),
            "expectedFirstTradeDate": _isoformat_optional(expectation_row.get("expected_start_trade_date")),
            "expectedEnd": _isoformat_optional(expectation_row.get("expected_end")),
            "expectedDays": expected_days,
        }
    ]

    items = [
        {
            "symbol": row.get("symbol"),
            "name": row.get("name") or row.get("symbol"),
            "market": row.get("market"),
            "firstDate": _isoformat_optional(row.get("first_date")),
            "latestDate": _isoformat_optional(row.get("latest_date")),
            "rowCount": int(row.get("row_count") or 0),
            "expectedStart": _isoformat_optional(row.get("expected_start")),
            "expectedEnd": _isoformat_optional(row.get("expected_end")),
            "status": row.get("status") or "missing",
            "missingDays": int(row.get("missing_days") or 0),
            "lastUpdated": _isoformat_optional(row.get("last_updated")),
        }
        for row in item_rows
    ]

    return {
        "summary": {
            "expectedStart": start_date.isoformat(),
            "expectedEnd": _isoformat_optional(max(expected_end_values)) if expected_end_values else None,
            "markets": markets,
            "filteredTotal": total,
            "counts": counts,
            "totalRows": total_rows,
            "totalMissingDays": total_missing_days,
            "lastUpdated": _isoformat_optional(max(last_updated_values)) if last_updated_values else None,
        },
        "items": items,
        "total": total,
    }


def _load_history_coverage_market_rows(*, user_id: int, start_date: date, search: str) -> list[dict[str, Any]]:
    universe_sql, universe_params = _build_history_coverage_universe_sql(user_id)
    if not universe_sql:
        return []

    params: list[Any] = list(universe_params)
    search_clause = ""
    search_value = str(search or "").strip()
    if search_value:
        search_clause = "AND (symbol LIKE %s OR display_name LIKE %s)"
        like_value = f"%{search_value}%"
        params.extend([like_value, like_value])

    market_rows = (
        DbUtil.fetch_all(
            f"""
        WITH universe_union AS (
            {universe_sql}
        ),
        ranked_universe AS (
            SELECT
                symbol,
                display_name,
                market,
                ROW_NUMBER() OVER (
                    PARTITION BY symbol
                    ORDER BY source_priority ASC, market ASC, symbol ASC
                ) AS row_rank
            FROM universe_union
        ),
        base_universe AS (
            SELECT symbol, display_name, market
            FROM ranked_universe
            WHERE row_rank = 1
        )
        SELECT DISTINCT market
        FROM base_universe
        WHERE 1 = 1
          {search_clause}
        ORDER BY market ASC
        """,
            tuple(params),
        )
        or []
    )
    markets = [
        str(row.get("market") or "").strip().upper() for row in market_rows if str(row.get("market") or "").strip()
    ]
    if not markets:
        return []

    placeholders = ", ".join(["%s"] * len(markets))
    history_table = HistoricalMarketDataService.TABLE_NAME
    return (
        DbUtil.fetch_all(
            f"""
        SELECT
            market,
            MIN(trade_date) AS expected_start_trade_date,
            MAX(trade_date) AS expected_end,
            COUNT(DISTINCT trade_date) AS expected_days
        FROM {history_table}
        WHERE trade_date >= %s
          AND market IN ({placeholders})
        GROUP BY market
        ORDER BY market ASC
        """,
            (start_date, *markets),
        )
        or []
    )


def _load_history_coverage_payload(
    *,
    user_id: int,
    start_date: date,
    search: str,
    status: str,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    exact_payload = _load_exact_history_coverage_payload(
        user_id=user_id,
        start_date=start_date,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )
    if exact_payload is not None:
        return exact_payload

    coverage_sql, coverage_params = _build_history_coverage_sql(
        user_id=user_id,
        start_date=start_date,
        search=search,
        status=status,
    )
    if not coverage_sql:
        return _empty_history_coverage_payload(start_date)

    offset = max(int(page) - 1, 0) * int(page_size)
    item_rows = (
        DbUtil.fetch_all(
            f"""
        SELECT *
        FROM (
            SELECT
                paged_coverage.*,
                COUNT(*) OVER() AS filtered_total,
                SUM(CASE WHEN paged_coverage.status = 'complete' THEN 1 ELSE 0 END) OVER() AS complete_count,
                SUM(CASE WHEN paged_coverage.status = 'partial' THEN 1 ELSE 0 END) OVER() AS partial_count,
                SUM(CASE WHEN paged_coverage.status = 'missing' THEN 1 ELSE 0 END) OVER() AS missing_count,
                SUM(COALESCE(paged_coverage.row_count, 0)) OVER() AS total_rows,
                SUM(COALESCE(paged_coverage.missing_days, 0)) OVER() AS total_missing_days,
                MAX(paged_coverage.expected_end) OVER() AS summary_expected_end,
                MAX(paged_coverage.last_updated) OVER() AS summary_last_updated
            FROM ({coverage_sql}) AS paged_coverage
        ) AS windowed_coverage
        ORDER BY
            CASE windowed_coverage.status
                WHEN 'missing' THEN 0
                WHEN 'partial' THEN 1
                ELSE 2
            END ASC,
            windowed_coverage.missing_days DESC,
            windowed_coverage.symbol ASC
        LIMIT %s OFFSET %s
        """,
            coverage_params + (int(page_size), int(offset)),
        )
        or []
    )
    summary_row = item_rows[0] if item_rows else {}
    total = int(summary_row.get("filtered_total") or 0)
    market_rows = _load_history_coverage_market_rows(user_id=user_id, start_date=start_date, search=search)

    items = [
        {
            "symbol": row.get("symbol"),
            "name": row.get("name") or row.get("symbol"),
            "market": row.get("market"),
            "firstDate": _isoformat_optional(row.get("first_date")),
            "latestDate": _isoformat_optional(row.get("latest_date")),
            "rowCount": int(row.get("row_count") or 0),
            "expectedStart": _isoformat_optional(row.get("expected_start")),
            "expectedEnd": _isoformat_optional(row.get("expected_end")),
            "status": row.get("status") or "missing",
            "missingDays": int(row.get("missing_days") or 0),
            "lastUpdated": _isoformat_optional(row.get("last_updated")),
        }
        for row in item_rows
    ]

    return {
        "summary": {
            "expectedStart": start_date.isoformat(),
            "expectedEnd": _isoformat_optional(summary_row.get("summary_expected_end")),
            "markets": [
                {
                    "market": row.get("market"),
                    "expectedStart": start_date.isoformat(),
                    "expectedFirstTradeDate": _isoformat_optional(row.get("expected_start_trade_date")),
                    "expectedEnd": _isoformat_optional(row.get("expected_end")),
                    "expectedDays": int(row.get("expected_days") or 0),
                }
                for row in market_rows
            ],
            "filteredTotal": int(summary_row.get("filtered_total") or 0),
            "counts": {
                "complete": int(summary_row.get("complete_count") or 0),
                "partial": int(summary_row.get("partial_count") or 0),
                "missing": int(summary_row.get("missing_count") or 0),
            },
            "totalRows": int(summary_row.get("total_rows") or 0),
            "totalMissingDays": int(summary_row.get("total_missing_days") or 0),
            "lastUpdated": _isoformat_optional(summary_row.get("summary_last_updated")),
        },
        "items": items,
        "total": total,
    }


def _build_history_coverage_cache_key(
    *,
    user_id: int,
    start_date: date,
    search: str,
    status: str,
    page: int,
    page_size: int,
    expected_start: str | None,
    expected_end: str | None,
) -> tuple[Any, ...]:
    normalized_search, _explicit_market_suffix = _normalize_exact_history_coverage_symbol(search)
    return (
        "history-coverage",
        int(user_id),
        start_date.isoformat(),
        normalized_search or str(search or "").strip(),
        str(status or "").strip().lower(),
        int(page),
        int(page_size),
        str(expected_start or "").strip(),
        str(expected_end or "").strip(),
    )


def _get_history_coverage_cache(cache_key: tuple[Any, ...]) -> dict[str, Any] | None:
    now = time.monotonic()
    with _HISTORY_COVERAGE_CACHE_LOCK:
        cached = _HISTORY_COVERAGE_CACHE.get(cache_key)
        if not cached:
            return None
        if float(cached.get("expires_at") or 0.0) <= now:
            _HISTORY_COVERAGE_CACHE.pop(cache_key, None)
            return None
        return copy.deepcopy(cached.get("payload"))


def _set_history_coverage_cache(cache_key: tuple[Any, ...], payload: dict[str, Any]) -> dict[str, Any]:
    cached_payload = copy.deepcopy(payload)
    now = time.monotonic()
    expires_at = now + _HISTORY_COVERAGE_CACHE_TTL_SECONDS
    with _HISTORY_COVERAGE_CACHE_LOCK:
        expired_keys = [
            key for key, value in _HISTORY_COVERAGE_CACHE.items() if float(value.get("expires_at") or 0.0) <= now
        ]
        for key in expired_keys:
            _HISTORY_COVERAGE_CACHE.pop(key, None)
        _HISTORY_COVERAGE_CACHE[cache_key] = {
            "expires_at": expires_at,
            "payload": cached_payload,
        }
    return copy.deepcopy(cached_payload)


def _clear_history_coverage_cache() -> None:
    with _HISTORY_COVERAGE_CACHE_LOCK:
        _HISTORY_COVERAGE_CACHE.clear()
    with _HISTORY_MARKET_EXPECTATION_CACHE_LOCK:
        _HISTORY_MARKET_EXPECTATION_CACHE.clear()


def _parse_date(raw_value: str | None, field_name: str) -> date | None:
    if raw_value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(raw_value).strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是 YYYY-MM-DD 格式") from exc


def _require_symbols(raw_values: list[str] | None, merged: str | None = None) -> list[str]:
    symbols = _parse_symbols(raw_values, merged)
    if not symbols:
        raise HTTPException(status_code=400, detail="至少需要一个 symbol")
    return symbols


def _coerce_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是整数") from exc


def _coerce_optional_float(value: Any, field_name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是数字") from exc


def _build_stock_pool_filters(
    *,
    asset_type: str,
    symbol: str,
    name: str,
    column_market: str,
    column_type: str,
    price_min: float | None,
    price_max: float | None,
    change_percent: float | None,
    volume_min: float | None,
    volume_max: float | None,
    market_cap_min: float | None,
    market_cap_max: float | None,
    pe: float | None,
) -> dict[str, Any]:
    return {
        "asset_type": str(asset_type or "").strip().lower(),
        "type": str(asset_type or "").strip().lower(),
        "symbol": str(symbol or "").strip(),
        "name": str(name or "").strip(),
        "column_market": str(column_market or "").strip().upper(),
        "column_type": str(column_type or "").strip().lower(),
        "price_min": price_min,
        "price_max": price_max,
        "change_percent": change_percent,
        "volume_min": volume_min,
        "volume_max": volume_max,
        "market_cap_min": market_cap_min,
        "market_cap_max": market_cap_max,
        "pe": pe,
    }


def _quote_capability(method_name: str) -> bool:
    return hasattr(QuoteContext, method_name)


def _content_capability(method_name: str) -> bool:
    return hasattr(ContentContext, method_name)


def _sdk_capability(item: dict[str, Any]) -> bool:
    capability_type = str(item.get("capabilityType") or "quote").strip().lower()
    method_name = str(item.get("sdkMethod") or "").strip()
    if not method_name:
        return False
    if capability_type == "content":
        return _content_capability(method_name)
    return _quote_capability(method_name)


def _longbridge_catalog() -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    for section in LONGBRIDGE_PULL_CATALOG:
        items = []
        for item in section["items"]:
            items.append(
                {
                    **item,
                    "available": _sdk_capability(item),
                }
            )
        catalog.append({"group": section["group"], "items": items})
    return catalog


def _longbridge_runtime() -> dict[str, Any]:
    endpoints = resolve_endpoints()
    return {
        "region": resolve_region(),
        "sdkPackage": SDK_PACKAGE,
        "endpoints": endpoints,
        "capabilities": {
            "staticInfo": _quote_capability("static_info"),
            "quote": _quote_capability("quote"),
            "optionQuote": _quote_capability("option_quote"),
            "warrantQuote": _quote_capability("warrant_quote"),
            "depth": _quote_capability("depth"),
            "brokers": _quote_capability("brokers"),
            "participants": _quote_capability("participants"),
            "trades": _quote_capability("trades"),
            "intraday": _quote_capability("intraday"),
            "historyCandlesticks": _quote_capability("history_candlesticks_by_date"),
            "candlesticks": _quote_capability("candlesticks"),
            "optionChain": _quote_capability("option_chain_info_by_date"),
            "warrants": _quote_capability("warrant_list"),
            "tradingSession": _quote_capability("trading_session"),
            "tradingDays": _quote_capability("trading_days"),
            "capitalFlow": _quote_capability("capital_flow"),
            "capitalDistribution": _quote_capability("capital_distribution"),
            "calcIndexes": _quote_capability("calc_indexes"),
            "securityList": _quote_capability("security_list"),
            "marketTemperature": _quote_capability("market_temperature"),
            "historyMarketTemperature": _quote_capability("history_market_temperature"),
            "announcements": _quote_capability("filings"),
            "contentNews": _content_capability("news"),
            "contentTopics": _content_capability("topics"),
            "pushSubscribe": _quote_capability("subscribe"),
            "pushUnsubscribe": _quote_capability("unsubscribe"),
            "pushSubscriptions": _quote_capability("subscriptions"),
            "pushQuote": _quote_capability("set_on_quote"),
            "pushDepth": _quote_capability("set_on_depth"),
            "pushBrokers": _quote_capability("set_on_brokers"),
            "pushTrades": _quote_capability("set_on_trades"),
            "pushCandlestick": _quote_capability("set_on_candlestick"),
        },
    }


def _with_quote_context(user_id: int):
    return build_quote_context(user_id=user_id, region=resolve_region())


def _with_content_context(user_id: int):
    return build_content_context(user_id=user_id, region=resolve_region())


def _fallback_live_payload(
    payload: Any,
    *,
    reason: str,
    data_source: str = "longbridge-fallback",
):
    return {
        "success": True,
        "data": _serialize_live(
            payload,
            data_source=data_source,
            extra={
                "fallback": True,
                "reason": reason,
            },
        ),
    }


def _extract_websocket_session(websocket: WebSocket) -> dict[str, Any]:
    raw_token = (
        str(websocket.query_params.get("token") or "").strip()
        or str(websocket.headers.get("authorization") or "").strip()
    )
    if not raw_token:
        raise HTTPException(status_code=401, detail="未登录")
    if raw_token.startswith("Bearer "):
        raw_token = raw_token[7:].strip()
    return decode_token(raw_token)


def _serialize_live(
    payload: Any, *, data_source: str = "longbridge-live", extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    body = {
        "dataSource": data_source,
        "runtime": _longbridge_runtime(),
        "payload": to_plain(payload),
    }
    if extra:
        body.update(extra)
    return body


def _mark_live_payload_stale(payload: dict[str, Any]) -> dict[str, Any]:
    marked = copy.deepcopy(payload)
    data = marked.get("data")
    if isinstance(data, dict):
        source = str(data.get("dataSource") or "longbridge-live")
        data["dataSource"] = source if source.endswith("-stale") else f"{source}-stale"
        data["stale"] = True
    return marked


def _live_cache_get(cache_key: tuple[Any, ...], *, allow_stale: bool = False) -> dict[str, Any] | None:
    now = time.time()
    with _LIVE_MARKET_CACHE_LOCK:
        cached = _LIVE_MARKET_CACHE.get(cache_key)
        if not cached:
            return None
        expires_at = float(cached.get("expires_at") or 0)
        stale_until = float(cached.get("stale_until") or 0)
        if expires_at <= now:
            if allow_stale and stale_until > now:
                return _mark_live_payload_stale(cached.get("payload") or {})
            _LIVE_MARKET_CACHE.pop(cache_key, None)
            return None
        return copy.deepcopy(cached.get("payload"))


def _live_cache_set(cache_key: tuple[Any, ...], payload: dict[str, Any], ttl_seconds: int) -> dict[str, Any]:
    now = time.time()
    cached_payload = copy.deepcopy(payload)
    with _LIVE_MARKET_CACHE_LOCK:
        if len(_LIVE_MARKET_CACHE) > 256:
            expired_keys = [
                key for key, value in _LIVE_MARKET_CACHE.items() if float(value.get("expires_at") or 0) <= now
            ]
            for key in expired_keys[:64]:
                _LIVE_MARKET_CACHE.pop(key, None)
        _LIVE_MARKET_CACHE[cache_key] = {
            "expires_at": now + max(1, int(ttl_seconds or 1)),
            "stale_until": now + max(1, int(ttl_seconds or 1)) + _LIVE_MARKET_STALE_SECONDS,
            "payload": cached_payload,
        }
    return copy.deepcopy(cached_payload)


async def _run_live_pull(loader):
    return await asyncio.to_thread(loader)


def _live_response(
    payload: Any, *, data_source: str = "longbridge-live", extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"success": True, "data": _serialize_live(payload, data_source=data_source, extra=extra)}


async def _load_longbridge_quotes(
    *,
    user_id: int,
    symbols: list[str],
    ctx: Any = None,
    allow_stale: bool = True,
) -> dict[str, Any]:
    normalized_symbols = [HistoricalMarketDataService.normalize_symbol(symbol) for symbol in symbols]
    cache_key = ("longbridge-quotes", int(user_id), tuple(normalized_symbols))
    cached_payload = _live_cache_get(cache_key, allow_stale=allow_stale)
    if cached_payload:
        return cached_payload

    quote_context = ctx or _with_quote_context(int(user_id))
    try:
        payload = await _run_live_pull(lambda: quote_context.quote(normalized_symbols))
    except Exception as exc:
        _warn_live_fallback_once(
            "longbridge_quote_pull",
            "Longbridge quote pull degraded: user_id=%s symbol_count=%s error=%s",
            user_id,
            len(normalized_symbols),
            exc,
        )
        return _fallback_live_payload(
            [],
            reason=str(exc)[:180],
            data_source="longbridge-live-unavailable",
        )
    return _live_cache_set(cache_key, _live_response(payload), _LIVE_MARKET_CACHE_TTL_SECONDS)


async def _load_longbridge_depth(
    *,
    user_id: int,
    symbol: str,
    ctx: Any = None,
    allow_stale: bool = True,
) -> dict[str, Any]:
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    cache_key = ("longbridge-depth", int(user_id), normalized_symbol)
    cached_payload = _live_cache_get(cache_key, allow_stale=allow_stale)
    if cached_payload:
        return cached_payload

    quote_context = ctx or _with_quote_context(int(user_id))
    try:
        payload = await _run_live_pull(lambda: quote_context.depth(normalized_symbol))
    except Exception as exc:
        _warn_live_fallback_once(
            "longbridge_depth_pull",
            "Longbridge depth pull degraded: user_id=%s symbol=%s error=%s",
            user_id,
            normalized_symbol,
            exc,
        )
        return _fallback_live_payload(
            {},
            reason=str(exc)[:180],
            data_source="longbridge-live-unavailable",
        )
    return _live_cache_set(cache_key, _live_response(payload), _LIVE_MARKET_CACHE_TTL_SECONDS)


async def _load_longbridge_trades(
    *,
    user_id: int,
    symbol: str,
    count: int = 50,
    ctx: Any = None,
    allow_stale: bool = True,
) -> dict[str, Any]:
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    safe_count = max(1, min(int(count or 50), 1000))
    cache_key = ("longbridge-trades", int(user_id), normalized_symbol, safe_count)
    cached_payload = _live_cache_get(cache_key, allow_stale=allow_stale)
    if cached_payload:
        return cached_payload

    quote_context = ctx or _with_quote_context(int(user_id))
    try:
        payload = await _run_live_pull(lambda: quote_context.trades(normalized_symbol, safe_count))
    except Exception as exc:
        _warn_live_fallback_once(
            "longbridge_trades_pull",
            "Longbridge trades pull degraded: user_id=%s symbol=%s count=%s error=%s",
            user_id,
            normalized_symbol,
            safe_count,
            exc,
        )
        return _fallback_live_payload(
            [],
            reason=str(exc)[:180],
            data_source="longbridge-live-unavailable",
        )
    return _live_cache_set(cache_key, _live_response(payload), _LIVE_MARKET_CACHE_TTL_SECONDS)


def _extract_live_payload(response: Any, fallback: Any) -> Any:
    if not isinstance(response, dict):
        return fallback
    data = response.get("data")
    if isinstance(data, dict) and "payload" in data:
        return data.get("payload")
    return data if data is not None else fallback


def _extract_live_source(response: Any, fallback: str = "longbridge-live") -> str:
    data = response.get("data") if isinstance(response, dict) else {}
    if isinstance(data, dict):
        return str(data.get("dataSource") or fallback)
    return fallback


def _first_live_quote(payload: Any, symbol: str) -> dict[str, Any] | None:
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    rows = payload if isinstance(payload, list) else [payload] if isinstance(payload, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_symbol = HistoricalMarketDataService.normalize_symbol(row.get("symbol") or normalized_symbol)
        if row_symbol == normalized_symbol:
            return row
    return rows[0] if rows and isinstance(rows[0], dict) else None


async def _load_symbol_live_quote(user_id: int, symbol: str) -> dict[str, Any] | None:
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    try:
        response = await _load_longbridge_quotes(user_id=int(user_id), symbols=[normalized_symbol])
        payload = _extract_live_payload(response, [])
        quote = _first_live_quote(to_plain(payload), normalized_symbol)
        if not quote:
            return None
        source = _extract_live_source(response, "longbridge-live")
        timestamp = (
            quote.get("timestamp")
            or quote.get("updated_at")
            or quote.get("updatedAt")
            or (quote.get("pre_market_quote") or {}).get("timestamp")
            or (quote.get("post_market_quote") or {}).get("timestamp")
            or (quote.get("overnight_quote") or {}).get("timestamp")
        )
        return {
            **quote,
            "symbol": normalized_symbol,
            "source": source,
            "dataSource": source,
            "timestamp": timestamp,
            "snapshotAt": timestamp,
        }
    except Exception as exc:
        LOGGER.warning("Longbridge live quote failed for symbol overview: symbol=%s error=%s", normalized_symbol, exc)
        return None


def _cached_content_payload(
    *,
    symbol: str,
    content_type: str,
    user_id: int,
    loader,
    source_name: str,
):
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    cached = SymbolContentCacheService.get_cached(
        symbol=normalized_symbol,
        content_type=content_type,
        limit=20,
    )
    if cached:
        return {"success": True, "data": _serialize_live(cached, data_source="content-cache", extra={"cacheHit": True})}

    try:
        payload = loader(normalized_symbol)
        plain_payload = to_plain(payload)
        items = plain_payload if isinstance(plain_payload, list) else []
        if items:
            SymbolContentCacheService.upsert_items(
                symbol=normalized_symbol,
                market=HistoricalMarketDataService.detect_market(normalized_symbol),
                content_type=content_type,
                items=items,
                source_name=source_name,
            )
        return {"success": True, "data": _serialize_live(plain_payload, data_source="longbridge-content")}
    except Exception as exc:
        stale_cached = SymbolContentCacheService.get_cached(
            symbol=normalized_symbol,
            content_type=content_type,
            limit=20,
            include_expired=True,
        )
        if stale_cached:
            return _fallback_live_payload(
                stale_cached,
                reason=f"{str(exc)[:180]}，已回退缓存",
                data_source="content-cache-fallback",
            )
        return _fallback_live_payload([], reason=str(exc)[:180], data_source="longbridge-content-fallback")


def _content_cache_bundle(symbol: str, limit: int = 6) -> dict[str, Any]:
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    content_types = ("announcements", "news", "topics")
    bundle: dict[str, Any] = {}
    updated_at_candidates: list[str] = []
    total_items = 0

    for content_type in content_types:
        items = SymbolContentCacheService.get_cached(
            symbol=normalized_symbol,
            content_type=content_type,
            limit=limit,
        )
        total_items += len(items)
        fetched_candidates = [str(item.get("cache_fetched_at") or "") for item in items if item.get("cache_fetched_at")]
        updated_at = max(fetched_candidates) if fetched_candidates else None
        if updated_at:
            updated_at_candidates.append(updated_at)
        bundle[content_type] = {
            "items": items,
            "count": len(items),
            "dataSource": "content-cache" if items else "content-cache-empty",
            "updatedAt": updated_at,
        }

    return {
        "symbol": normalized_symbol,
        "dataSource": "content-cache" if total_items else "content-cache-empty",
        "updatedAt": max(updated_at_candidates) if updated_at_candidates else None,
        "totalCount": total_items,
        **bundle,
    }


def _build_symbol_overview_meta(
    *,
    overview: dict[str, Any],
    history: dict[str, Any],
    latest_ai_payload: dict[str, Any] | None,
    latest_trend_scan: dict[str, Any] | None,
    market_insight: dict[str, Any] | None,
    market_scan: dict[str, Any] | None,
    quote_snapshot: dict[str, Any] | None,
    content_cache: dict[str, Any],
    response_mode: str = "all",
    deferred_sections: list[str] | None = None,
) -> dict[str, Any]:
    snapshots = overview.get("snapshots") if isinstance(overview.get("snapshots"), dict) else {}
    daily_snapshot = snapshots.get("daily") if isinstance(snapshots.get("daily"), dict) else {}
    history_summary = history.get("summary") if isinstance(history.get("summary"), dict) else {}
    quote_source = str(
        (quote_snapshot or {}).get("dataSource") or (quote_snapshot or {}).get("source") or "longbridge-live"
    )
    snapshot_candidates = [
        str(daily_snapshot.get("snapshotDate") or ""),
        str(history_summary.get("latestDate") or ""),
        str((quote_snapshot or {}).get("snapshotAt") or ""),
        str((quote_snapshot or {}).get("timestamp") or ""),
        str(content_cache.get("updatedAt") or ""),
        str((latest_ai_payload or {}).get("analysis_time") or (latest_ai_payload or {}).get("created_at") or ""),
        str((latest_trend_scan or {}).get("analysisTime") or ""),
        str((market_insight or {}).get("generatedAt") or ""),
        str((market_scan or {}).get("generatedAt") or ""),
    ]
    snapshot_at = max([item for item in snapshot_candidates if item], default=None)
    history_items = history.get("items") if isinstance(history.get("items"), list) else []

    return {
        "readModel": "market-symbol-overview",
        "defaultMode": "database",
        "dataSource": "snapshot",
        "responseMode": response_mode,
        "deferredSections": deferred_sections or [],
        "historyStatus": "deferred" if "history" in (deferred_sections or []) else "loaded",
        "snapshotState": "ready" if snapshots else "missing",
        "snapshotAt": snapshot_at,
        "sources": {
            "fundamentals": "market_universe",
            "indicators": "indicator_snapshots",
            "history": "historical_market_data",
            "quote": quote_source,
            "marketInsight": "market_insight_snapshots",
            "marketScan": "daily_market_ai_scans",
            "trendScan": "daily_symbol_trend_ai_scans",
            "aiAnalysis": "ai_analysis_history",
            "content": "symbol_content_cache",
        },
        "historyCount": len(history_items),
        "hasQuoteSnapshot": bool((quote_snapshot or {}).get("snapshotAt") or (quote_snapshot or {}).get("price")),
        "hasRealtimeQuote": bool(quote_snapshot),
        "hasAiAnalysis": bool(latest_ai_payload),
        "hasTrendScan": bool(latest_trend_scan),
        "contentCount": int(content_cache.get("totalCount") or 0),
        "realtimeOverlay": ["quote", "depth", "trades"],
    }


def _empty_content_cache_bundle(data_source: str = "deferred") -> dict[str, Any]:
    return {
        "dataSource": data_source,
        "updatedAt": "",
        "totalCount": 0,
        "announcements": {"items": []},
        "news": {"items": []},
        "topics": {"items": []},
    }
