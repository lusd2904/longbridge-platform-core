from __future__ import annotations

import asyncio
import copy
import json
import re
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Body, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect


REFACTOR_ROOT = Path(__file__).resolve().parents[3]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.market.module_shared import (
    CalcIndex,
    ContentContext,
    DailyMarketScanService,
    DailySymbolTrendScanService,
    HistoricalMarketDataService,
    IndicatorSnapshotService,
    MarketInsightService,
    MarketUniverseSync,
    QuoteContext,
    QuoteSnapshotService,
    SDK_PACKAGE,
    SymbolContentCacheService,
    bootstrap_runtime,
    build_content_context,
    build_dependency_status,
    build_health_payload,
    build_quote_context,
    build_stock_pool_stats,
    create_service_app,
    decode_token,
    get_current_session,
    get_persistence_manager,
    iter_stock_pool_tables,
    legacy_boundary_status,
    normalize_market_symbol,
    parse_adjust_type,
    parse_calc_indexes,
    parse_market,
    parse_period,
    parse_security_list_category,
    parse_sort_order,
    parse_trade_sessions,
    parse_warrant_expiry_filter,
    parse_warrant_price_type,
    parse_warrant_sort_by,
    parse_warrant_status,
    parse_warrant_type,
    resolve_endpoints,
    resolve_region,
    resolve_stock_pool_table,
    service_port,
    summarize_status,
    to_plain,
    DbUtil,
)

bootstrap_runtime()

from push_hub import push_hub
from stock_pool_query import load_stock_pool_page
from watchlist_service import WatchlistService


@asynccontextmanager
async def market_service_lifespan(_: Any):
    push_hub.bind_loop(asyncio.get_running_loop())
    SymbolContentCacheService.ensure_schema()
    QuoteSnapshotService.ensure_schema()
    WatchlistService.ensure_schema()
    await asyncio.to_thread(HistoricalMarketDataService.get_backfill_status)
    default_coverage_key = _build_history_coverage_cache_key(
        start_date=_HISTORY_COVERAGE_START_DATE,
        search="",
        status="",
        page=1,
        page_size=20,
        expected_start=None,
        expected_end=None,
    )
    default_coverage_payload = await asyncio.to_thread(
        _load_history_coverage_payload,
        start_date=_HISTORY_COVERAGE_START_DATE,
        search="",
        status="",
        page=1,
        page_size=20,
    )
    _set_history_coverage_cache(default_coverage_key, default_coverage_payload)
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
_TRADING_SESSION_CACHE: Dict[str, Any] = {"expires_at": 0.0, "payload": None}
_TRADING_SESSION_TTL_SECONDS = 90
_LIVE_MARKET_CACHE_TTL_SECONDS = 6
_LIVE_MARKET_STALE_SECONDS = 45
_SYMBOL_OVERVIEW_CACHE_TTL_SECONDS = 10
_HISTORY_COVERAGE_START_DATE = date(2024, 1, 1)
_HISTORY_COVERAGE_STATUSES = {"complete", "partial", "missing"}
_HISTORY_COVERAGE_CACHE_TTL_SECONDS = 300
_HISTORY_COVERAGE_CACHE_LOCK = threading.Lock()
_HISTORY_COVERAGE_CACHE: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
_HISTORY_MARKET_EXPECTATION_CACHE_TTL_SECONDS = 300
_HISTORY_MARKET_EXPECTATION_CACHE_LOCK = threading.Lock()
_HISTORY_MARKET_EXPECTATION_CACHE: Dict[Tuple[str, str], Dict[str, Any]] = {}
_HISTORY_MARKET_EXPECTATION_ANCHORS: Dict[str, Tuple[str, ...]] = {
    "US": ("AAPL.US", "SPY.US", "QQQ.US", "NVDA.US"),
    "CN": ("000001.SH", "399001.SZ", "510300.SH", "510050.SH"),
    "HK": ("00700.HK", "2800.HK", "09988.HK", "00005.HK"),
}
_READ_MODEL_TABLE_EXISTS_CACHE_LOCK = threading.Lock()
_READ_MODEL_TABLE_EXISTS_CACHE: Dict[str, bool] = {}
_HISTORY_BACKFILL_LOCK = threading.Lock()
_HISTORY_BACKFILL_SYMBOLS: set[str] = set()
_LIVE_MARKET_CACHE_LOCK = threading.Lock()
_LIVE_MARKET_CACHE: Dict[Tuple[Any, ...], Dict[str, Any]] = {}


def _as_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_symbols(raw_values: Optional[List[str]], merged: Optional[str] = None) -> List[str]:
    items: List[str] = []
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
    symbols: List[str],
    timeframe: str,
    limit: int,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    series = payload.get("series") if isinstance(payload.get("series"), list) else []
    snapshot_candidates: List[str] = []
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
    data: List[Dict[str, Any]],
    market: str,
    generated_at: str,
) -> Dict[str, Any]:
    snapshot_candidates: List[str] = []
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
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    updated_candidates = [
        str(item.get("updated_at") or item.get("updatedAt") or item.get("quote_snapshot_at") or item.get("quoteSnapshotAt") or "")
        for item in items
        if isinstance(item, dict)
    ]
    snapshot_at = max([value for value in updated_candidates if value], default=None)
    return {
        "readModel": "stock-pool",
        "defaultMode": "database",
        "dataSource": "snapshot",
        "snapshotAt": snapshot_at,
        "sources": {
            "universe": "market_universe",
            "quotes": "quote_snapshots",
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


def _isoformat_optional(value: Any) -> Optional[str]:
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
    summary: Dict[str, Any],
) -> Dict[str, Any]:
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


def _build_history_coverage_universe_sql() -> str:
    table_configs = iter_stock_pool_tables("all")
    clauses: List[str] = []
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
              AND (user_id = 1 OR user_id IS NULL)
            """
        )
    return "\nUNION ALL\n".join(clauses)


def _empty_history_coverage_payload(start_date: date) -> Dict[str, Any]:
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


def _normalize_exact_history_coverage_symbol(search: str) -> Tuple[str, bool]:
    search_value = str(search or "").strip()
    if not search_value:
        return "", False
    if "." not in search_value and not re.fullmatch(r"[A-Za-z0-9\-]{1,16}", search_value):
        return "", False
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(search_value)
    if not re.fullmatch(r"[A-Z0-9.\-]{1,32}\.(US|HK|SH|SZ|BJ)", normalized_symbol):
        return "", False
    return normalized_symbol, "." in search_value


def _coerce_history_coverage_date(value: Any) -> Optional[date]:
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


def _load_exact_history_coverage_universe_rows(symbol: str) -> List[Dict[str, Any]]:
    table_configs = iter_stock_pool_tables("all")
    rows: List[Dict[str, Any]] = []
    for table_config in table_configs:
        table_name = str(table_config.get("table") or "").strip()
        name_field = str(table_config.get("name_field") or "").strip()
        market = str(table_config.get("market") or "").strip().upper()
        asset_type = str(table_config.get("type") or "").strip().lower()
        if not table_name or not name_field or not market or not _read_model_table_exists(table_name):
            continue
        priority = 0 if asset_type == "stock" else 1
        table_rows = DbUtil.fetch_all(
            f"""
            SELECT
                symbol,
                COALESCE(NULLIF(TRIM({name_field}), ''), symbol) AS display_name,
                '{market}' AS market,
                updated_at AS universe_updated_at,
                {priority} AS source_priority
            FROM {table_name}
            WHERE is_active = 1
              AND (user_id = 1 OR user_id IS NULL)
              AND symbol = %s
            ORDER BY
                CASE WHEN user_id = 1 THEN 0 ELSE 1 END ASC,
                updated_at DESC
            LIMIT 1
            """,
            (symbol,),
        ) or []
        rows.extend(table_rows)

    return sorted(
        rows,
        key=lambda row: (
            int(row.get("source_priority") or 0),
            str(row.get("market") or ""),
            str(row.get("symbol") or ""),
        ),
    )


def _get_history_market_expectation(*, start_date: date, market: str) -> Dict[str, Any]:
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
    row: Dict[str, Any] = {}
    if anchors:
        placeholders = ", ".join(["%s"] * len(anchors))
        row = DbUtil.fetch_one(
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
        ) or {}
    if not row:
        row = DbUtil.fetch_one(
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
        ) or {}
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
    start_date: date,
    search: str,
    status: str,
) -> Tuple[str, Tuple[Any, ...]]:
    universe_sql = _build_history_coverage_universe_sql()
    if not universe_sql:
        return "", ()

    history_table = HistoricalMarketDataService.TABLE_NAME
    params: List[Any] = []
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
    start_date: date,
    search: str,
    status: str,
    page: int,
    page_size: int,
) -> Optional[Dict[str, Any]]:
    exact_symbol, explicit_market_suffix = _normalize_exact_history_coverage_symbol(search)
    if not exact_symbol:
        return None

    universe_rows = _load_exact_history_coverage_universe_rows(exact_symbol)
    if not universe_rows:
        if explicit_market_suffix:
            return _empty_history_coverage_payload(start_date)
        return None

    target_universe = universe_rows[0]
    target_market = str(target_universe.get("market") or "").strip().upper()
    history_table = HistoricalMarketDataService.TABLE_NAME
    history_row = DbUtil.fetch_one(
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
    ) or {}
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
        row
        for row in coverage_rows
        if not status_value or str(row.get("status") or "").strip().lower() == status_value
    ]
    total = len(filtered_rows)
    offset = max(int(page) - 1, 0) * int(page_size)
    item_rows = filtered_rows[offset : offset + int(page_size)]

    counts = {key: 0 for key in sorted(_HISTORY_COVERAGE_STATUSES)}
    total_rows = 0
    total_missing_days = 0
    expected_end_values: List[Any] = []
    last_updated_values: List[Any] = []
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


def _load_history_coverage_market_rows(*, start_date: date, search: str) -> List[Dict[str, Any]]:
    universe_sql = _build_history_coverage_universe_sql()
    if not universe_sql:
        return []

    params: List[Any] = []
    search_clause = ""
    search_value = str(search or "").strip()
    if search_value:
        search_clause = "AND (symbol LIKE %s OR display_name LIKE %s)"
        like_value = f"%{search_value}%"
        params.extend([like_value, like_value])

    market_rows = DbUtil.fetch_all(
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
    ) or []
    markets = [
        str(row.get("market") or "").strip().upper()
        for row in market_rows
        if str(row.get("market") or "").strip()
    ]
    if not markets:
        return []

    placeholders = ", ".join(["%s"] * len(markets))
    history_table = HistoricalMarketDataService.TABLE_NAME
    return DbUtil.fetch_all(
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
    ) or []


def _load_history_coverage_payload(
    *,
    start_date: date,
    search: str,
    status: str,
    page: int,
    page_size: int,
) -> Dict[str, Any]:
    exact_payload = _load_exact_history_coverage_payload(
        start_date=start_date,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
    )
    if exact_payload is not None:
        return exact_payload

    coverage_sql, coverage_params = _build_history_coverage_sql(
        start_date=start_date,
        search=search,
        status=status,
    )
    if not coverage_sql:
        return _empty_history_coverage_payload(start_date)

    offset = max(int(page) - 1, 0) * int(page_size)
    item_rows = DbUtil.fetch_all(
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
    ) or []
    summary_row = item_rows[0] if item_rows else {}
    total = int(summary_row.get("filtered_total") or 0)
    market_rows = _load_history_coverage_market_rows(start_date=start_date, search=search)

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
    start_date: date,
    search: str,
    status: str,
    page: int,
    page_size: int,
    expected_start: Optional[str],
    expected_end: Optional[str],
) -> Tuple[Any, ...]:
    return (
        "history-coverage",
        start_date.isoformat(),
        str(search or "").strip(),
        str(status or "").strip(),
        int(page),
        int(page_size),
        str(expected_start or "").strip(),
        str(expected_end or "").strip(),
    )


def _get_history_coverage_cache(cache_key: Tuple[Any, ...]) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    with _HISTORY_COVERAGE_CACHE_LOCK:
        cached = _HISTORY_COVERAGE_CACHE.get(cache_key)
        if not cached:
            return None
        if float(cached.get("expires_at") or 0.0) <= now:
            _HISTORY_COVERAGE_CACHE.pop(cache_key, None)
            return None
        return copy.deepcopy(cached.get("payload"))


def _set_history_coverage_cache(cache_key: Tuple[Any, ...], payload: Dict[str, Any]) -> Dict[str, Any]:
    cached_payload = copy.deepcopy(payload)
    now = time.monotonic()
    expires_at = now + _HISTORY_COVERAGE_CACHE_TTL_SECONDS
    with _HISTORY_COVERAGE_CACHE_LOCK:
        expired_keys = [
            key
            for key, value in _HISTORY_COVERAGE_CACHE.items()
            if float(value.get("expires_at") or 0.0) <= now
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


def _parse_date(raw_value: Optional[str], field_name: str) -> Optional[date]:
    if raw_value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(raw_value).strip())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是 YYYY-MM-DD 格式") from exc


def _require_symbols(raw_values: Optional[List[str]], merged: Optional[str] = None) -> List[str]:
    symbols = _parse_symbols(raw_values, merged)
    if not symbols:
        raise HTTPException(status_code=400, detail="至少需要一个 symbol")
    return symbols


def _coerce_int(value: Any, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是整数") from exc


def _coerce_optional_float(value: Any, field_name: str) -> Optional[float]:
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
    price_min: Optional[float],
    price_max: Optional[float],
    change_percent: Optional[float],
    volume_min: Optional[float],
    volume_max: Optional[float],
    market_cap_min: Optional[float],
    market_cap_max: Optional[float],
    pe: Optional[float],
) -> Dict[str, Any]:
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


def _sdk_capability(item: Dict[str, Any]) -> bool:
    capability_type = str(item.get("capabilityType") or "quote").strip().lower()
    method_name = str(item.get("sdkMethod") or "").strip()
    if not method_name:
        return False
    if capability_type == "content":
        return _content_capability(method_name)
    return _quote_capability(method_name)


LONGBRIDGE_PULL_CATALOG = [
    {
        "group": "基础行情",
        "items": [
            {
                "id": "static_info",
                "title": "获取标的基础信息",
                "path": "/api/v1/market/longbridge/static-info",
                "method": "GET",
                "sdkMethod": "static_info",
                "dataMode": "live",
            },
            {
                "id": "quotes",
                "title": "获取标的实时行情",
                "path": "/api/v1/market/longbridge/quotes",
                "method": "GET",
                "sdkMethod": "quote",
                "dataMode": "live",
            },
            {
                "id": "depth",
                "title": "获取标的盘口",
                "path": "/api/v1/market/longbridge/depth",
                "method": "GET",
                "sdkMethod": "depth",
                "dataMode": "live",
            },
            {
                "id": "brokers",
                "title": "获取标的经纪队列",
                "path": "/api/v1/market/longbridge/brokers",
                "method": "GET",
                "sdkMethod": "brokers",
                "dataMode": "live",
            },
            {
                "id": "participants",
                "title": "获取券商席位 ID",
                "path": "/api/v1/market/longbridge/participants",
                "method": "GET",
                "sdkMethod": "participants",
                "dataMode": "snapshot",
            },
            {
                "id": "trades",
                "title": "获取标的成交明细",
                "path": "/api/v1/market/longbridge/trades",
                "method": "GET",
                "sdkMethod": "trades",
                "dataMode": "live",
            },
            {
                "id": "intraday",
                "title": "获取标的当日分时",
                "path": "/api/v1/market/longbridge/intraday",
                "method": "GET",
                "sdkMethod": "intraday",
                "dataMode": "live",
            },
        ],
    },
    {
        "group": "K 线与指标",
        "items": [
            {
                "id": "history_candlesticks",
                "title": "获取标的历史 K 线",
                "path": "/api/v1/market/longbridge/history-candlesticks",
                "method": "GET",
                "sdkMethod": "history_candlesticks_by_date",
                "dataMode": "hybrid",
            },
            {
                "id": "candlesticks",
                "title": "获取标的 K 线",
                "path": "/api/v1/market/longbridge/candlesticks",
                "method": "GET",
                "sdkMethod": "candlesticks",
                "dataMode": "live",
            },
            {
                "id": "capital_flow",
                "title": "获取标的当日资金流向",
                "path": "/api/v1/market/longbridge/capital-flow",
                "method": "GET",
                "sdkMethod": "capital_flow",
                "dataMode": "live",
            },
            {
                "id": "capital_distribution",
                "title": "获取标的当日资金分布",
                "path": "/api/v1/market/longbridge/capital-distribution",
                "method": "GET",
                "sdkMethod": "capital_distribution",
                "dataMode": "live",
            },
            {
                "id": "calc_indexes",
                "title": "获取标的计算指标",
                "path": "/api/v1/market/longbridge/calc-indexes",
                "method": "GET",
                "sdkMethod": "calc_indexes",
                "dataMode": "live",
            },
        ],
    },
    {
        "group": "期权与轮证",
        "items": [
            {
                "id": "option_quotes",
                "title": "获取期权实时行情",
                "path": "/api/v1/market/longbridge/options/quotes",
                "method": "GET",
                "sdkMethod": "option_quote",
                "dataMode": "live",
            },
            {
                "id": "warrant_quotes",
                "title": "获取轮证实时行情",
                "path": "/api/v1/market/longbridge/warrants/quotes",
                "method": "GET",
                "sdkMethod": "warrant_quote",
                "dataMode": "live",
            },
            {
                "id": "option_expiry_dates",
                "title": "获取标的的期权链到期日列表",
                "path": "/api/v1/market/longbridge/options/expiry-dates",
                "method": "GET",
                "sdkMethod": "option_chain_expiry_date_list",
                "dataMode": "snapshot",
            },
            {
                "id": "option_chain",
                "title": "获取标的的期权链到期日期权标的列表",
                "path": "/api/v1/market/longbridge/options/chain",
                "method": "GET",
                "sdkMethod": "option_chain_info_by_date",
                "dataMode": "snapshot",
            },
            {
                "id": "warrant_issuers",
                "title": "获取轮证发行商 ID",
                "path": "/api/v1/market/longbridge/warrants/issuers",
                "method": "GET",
                "sdkMethod": "warrant_issuers",
                "dataMode": "snapshot",
            },
            {
                "id": "warrant_list",
                "title": "获取轮证筛选列表",
                "path": "/api/v1/market/longbridge/warrants/list",
                "method": "GET",
                "sdkMethod": "warrant_list",
                "dataMode": "live",
            },
        ],
    },
    {
        "group": "市场维度",
        "items": [
            {
                "id": "trading_session",
                "title": "获取各市场当日交易时段",
                "path": "/api/v1/market/longbridge/trading-session",
                "method": "GET",
                "sdkMethod": "trading_session",
                "dataMode": "snapshot",
            },
            {
                "id": "trading_days",
                "title": "获取市场交易日",
                "path": "/api/v1/market/longbridge/trading-days",
                "method": "GET",
                "sdkMethod": "trading_days",
                "dataMode": "snapshot",
            },
            {
                "id": "security_list",
                "title": "获取标的列表",
                "path": "/api/v1/market/longbridge/security-list",
                "method": "GET",
                "sdkMethod": "security_list",
                "dataMode": "snapshot",
            },
            {
                "id": "market_temperature_current",
                "title": "当前市场温度",
                "path": "/api/v1/market/longbridge/market-temperature/current",
                "method": "GET",
                "sdkMethod": "market_temperature",
                "dataMode": "live",
            },
            {
                "id": "market_temperature_history",
                "title": "历史市场温度",
                "path": "/api/v1/market/longbridge/market-temperature/history",
                "method": "GET",
                "sdkMethod": "history_market_temperature",
                "dataMode": "snapshot",
            },
            {
                "id": "announcements",
                "title": "获取标的公告",
                "path": "/api/v1/market/longbridge/announcements",
                "method": "GET",
                "sdkMethod": "filings",
                "dataMode": "snapshot",
            },
        ],
    },
    {
        "group": "内容服务",
        "items": [
            {
                "id": "content_news",
                "title": "获取标的资讯",
                "path": "/api/v1/market/longbridge/content/news",
                "method": "GET",
                "sdkMethod": "news",
                "capabilityType": "content",
                "dataMode": "snapshot",
            },
            {
                "id": "content_topics",
                "title": "获取标的讨论",
                "path": "/api/v1/market/longbridge/content/topics",
                "method": "GET",
                "sdkMethod": "topics",
                "capabilityType": "content",
                "dataMode": "snapshot",
            },
        ],
    },
    {
        "group": "订阅与推送",
        "items": [
            {
                "id": "push_subscribe",
                "title": "订阅行情数据",
                "path": "/api/v1/market/longbridge/push/subscribe",
                "method": "POST",
                "sdkMethod": "subscribe",
                "dataMode": "stream",
            },
            {
                "id": "push_unsubscribe",
                "title": "取消订阅行情数据",
                "path": "/api/v1/market/longbridge/push/unsubscribe",
                "method": "POST",
                "sdkMethod": "unsubscribe",
                "dataMode": "stream",
            },
            {
                "id": "push_runtime",
                "title": "获取已订阅标的行情",
                "path": "/api/v1/market/longbridge/push/runtime",
                "method": "GET",
                "sdkMethod": "subscriptions",
                "dataMode": "stream",
            },
            {
                "id": "push_candlestick_subscribe",
                "title": "订阅 K 线推送",
                "path": "/api/v1/market/longbridge/push/candlesticks/subscribe",
                "method": "POST",
                "sdkMethod": "subscribe_candlesticks",
                "dataMode": "stream",
            },
            {
                "id": "push_candlestick_unsubscribe",
                "title": "取消 K 线推送",
                "path": "/api/v1/market/longbridge/push/candlesticks/unsubscribe",
                "method": "POST",
                "sdkMethod": "unsubscribe_candlesticks",
                "dataMode": "stream",
            },
            {
                "id": "push_quote_stream",
                "title": "实时价格推送",
                "path": "/ws/market/longbridge/push",
                "method": "WS",
                "sdkMethod": "set_on_quote",
                "dataMode": "stream",
            },
            {
                "id": "push_depth_stream",
                "title": "实时盘口推送",
                "path": "/ws/market/longbridge/push",
                "method": "WS",
                "sdkMethod": "set_on_depth",
                "dataMode": "stream",
            },
            {
                "id": "push_brokers_stream",
                "title": "实时经纪队列推送",
                "path": "/ws/market/longbridge/push",
                "method": "WS",
                "sdkMethod": "set_on_brokers",
                "dataMode": "stream",
            },
            {
                "id": "push_trades_stream",
                "title": "实时成交推送",
                "path": "/ws/market/longbridge/push",
                "method": "WS",
                "sdkMethod": "set_on_trades",
                "dataMode": "stream",
            },
            {
                "id": "push_candlestick_stream",
                "title": "实时 K 线推送",
                "path": "/ws/market/longbridge/push",
                "method": "WS",
                "sdkMethod": "set_on_candlestick",
                "dataMode": "stream",
            },
        ],
    },
]


def _longbridge_catalog() -> List[Dict[str, Any]]:
    catalog: List[Dict[str, Any]] = []
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


def _longbridge_runtime() -> Dict[str, Any]:
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


def _extract_websocket_session(websocket: WebSocket) -> Dict[str, Any]:
    raw_token = (
        str(websocket.query_params.get("token") or "").strip()
        or str(websocket.headers.get("authorization") or "").strip()
    )
    if not raw_token:
        raise HTTPException(status_code=401, detail="未登录")
    if raw_token.startswith("Bearer "):
        raw_token = raw_token[7:].strip()
    return decode_token(raw_token)


def _serialize_live(payload: Any, *, data_source: str = "longbridge-live", extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    body = {
        "dataSource": data_source,
        "runtime": _longbridge_runtime(),
        "payload": to_plain(payload),
    }
    if extra:
        body.update(extra)
    return body


def _mark_live_payload_stale(payload: Dict[str, Any]) -> Dict[str, Any]:
    marked = copy.deepcopy(payload)
    data = marked.get("data")
    if isinstance(data, dict):
        source = str(data.get("dataSource") or "longbridge-live")
        data["dataSource"] = source if source.endswith("-stale") else f"{source}-stale"
        data["stale"] = True
    return marked


def _live_cache_get(cache_key: Tuple[Any, ...], *, allow_stale: bool = False) -> Optional[Dict[str, Any]]:
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


def _live_cache_set(cache_key: Tuple[Any, ...], payload: Dict[str, Any], ttl_seconds: int) -> Dict[str, Any]:
    now = time.time()
    cached_payload = copy.deepcopy(payload)
    with _LIVE_MARKET_CACHE_LOCK:
        if len(_LIVE_MARKET_CACHE) > 256:
            expired_keys = [
                key
                for key, value in _LIVE_MARKET_CACHE.items()
                if float(value.get("expires_at") or 0) <= now
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


def _live_response(payload: Any, *, data_source: str = "longbridge-live", extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"success": True, "data": _serialize_live(payload, data_source=data_source, extra=extra)}


async def _load_longbridge_quotes(
    *,
    user_id: int,
    symbols: List[str],
    ctx: Any = None,
    allow_stale: bool = True,
) -> Dict[str, Any]:
    normalized_symbols = [HistoricalMarketDataService.normalize_symbol(symbol) for symbol in symbols]
    cache_key = ("longbridge-quotes", int(user_id), tuple(normalized_symbols))
    cached_payload = _live_cache_get(cache_key, allow_stale=allow_stale)
    if cached_payload:
        return cached_payload

    quote_context = ctx or _with_quote_context(int(user_id))
    payload = await _run_live_pull(lambda: quote_context.quote(normalized_symbols))
    return _live_cache_set(cache_key, _live_response(payload), _LIVE_MARKET_CACHE_TTL_SECONDS)


async def _load_longbridge_depth(
    *,
    user_id: int,
    symbol: str,
    ctx: Any = None,
    allow_stale: bool = True,
) -> Dict[str, Any]:
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    cache_key = ("longbridge-depth", int(user_id), normalized_symbol)
    cached_payload = _live_cache_get(cache_key, allow_stale=allow_stale)
    if cached_payload:
        return cached_payload

    quote_context = ctx or _with_quote_context(int(user_id))
    payload = await _run_live_pull(lambda: quote_context.depth(normalized_symbol))
    return _live_cache_set(cache_key, _live_response(payload), _LIVE_MARKET_CACHE_TTL_SECONDS)


async def _load_longbridge_trades(
    *,
    user_id: int,
    symbol: str,
    count: int = 50,
    ctx: Any = None,
    allow_stale: bool = True,
) -> Dict[str, Any]:
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    safe_count = max(1, min(int(count or 50), 1000))
    cache_key = ("longbridge-trades", int(user_id), normalized_symbol, safe_count)
    cached_payload = _live_cache_get(cache_key, allow_stale=allow_stale)
    if cached_payload:
        return cached_payload

    quote_context = ctx or _with_quote_context(int(user_id))
    payload = await _run_live_pull(lambda: quote_context.trades(normalized_symbol, safe_count))
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


def _content_cache_bundle(symbol: str, limit: int = 6) -> Dict[str, Any]:
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    content_types = ("announcements", "news", "topics")
    bundle: Dict[str, Any] = {}
    updated_at_candidates: List[str] = []
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
    overview: Dict[str, Any],
    history: Dict[str, Any],
    latest_ai_payload: Optional[Dict[str, Any]],
    latest_trend_scan: Optional[Dict[str, Any]],
    market_insight: Optional[Dict[str, Any]],
    market_scan: Optional[Dict[str, Any]],
    quote_snapshot: Optional[Dict[str, Any]],
    content_cache: Dict[str, Any],
    response_mode: str = "all",
    deferred_sections: Optional[List[str]] = None,
) -> Dict[str, Any]:
    snapshots = overview.get("snapshots") if isinstance(overview.get("snapshots"), dict) else {}
    daily_snapshot = snapshots.get("daily") if isinstance(snapshots.get("daily"), dict) else {}
    history_summary = history.get("summary") if isinstance(history.get("summary"), dict) else {}
    snapshot_candidates = [
        str(daily_snapshot.get("snapshotDate") or ""),
        str(history_summary.get("latestDate") or ""),
        str((quote_snapshot or {}).get("snapshotAt") or ""),
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
            "quote": "quote_snapshots",
            "marketInsight": "market_insight_snapshots",
            "marketScan": "daily_market_ai_scans",
            "trendScan": "daily_symbol_trend_ai_scans",
            "aiAnalysis": "ai_analysis_history",
            "content": "symbol_content_cache",
        },
        "historyCount": len(history_items),
        "hasQuoteSnapshot": bool((quote_snapshot or {}).get("snapshotAt") or (quote_snapshot or {}).get("price")),
        "hasAiAnalysis": bool(latest_ai_payload),
        "hasTrendScan": bool(latest_trend_scan),
        "contentCount": int(content_cache.get("totalCount") or 0),
        "realtimeOverlay": ["quote", "depth", "trades"],
    }


def _empty_content_cache_bundle(data_source: str = "deferred") -> Dict[str, Any]:
    return {
        "dataSource": data_source,
        "updatedAt": "",
        "totalCount": 0,
        "announcements": {"items": []},
        "news": {"items": []},
        "topics": {"items": []},
    }


@app.get("/health")
async def health():
    mysql_ok = bool(DbUtil.query_one("SELECT 1"))
    runtime = _longbridge_runtime()
    quote_ready = bool(runtime.get("capabilities", {}).get("quote"))
    content_ready = bool(runtime.get("capabilities", {}).get("contentNews"))
    deps = {
        "mysql": build_dependency_status("mysql", "healthy" if mysql_ok else "degraded", detail="行情、指标与快照读写数据库"),
        "longbridge-sdk": build_dependency_status(
            "longbridge-sdk",
            "healthy" if quote_ready else "degraded",
            detail="行情与内容接口能力检测",
            observed={"region": runtime.get("region"), "sdkPackage": runtime.get("sdkPackage")},
        ),
    }
    broker_connectivity = {
        "longbridge": {
            "status": "healthy" if quote_ready else "degraded",
            "status_text": "行情能力已就绪" if quote_ready else "行情能力受限",
            "quote": quote_ready,
            "content": content_ready,
        }
    }
    return build_health_payload(
        service="market-service",
        version=app.version,
        port=PORT,
        status=summarize_status(deps.values()),
        deps=deps,
        broker_connectivity=broker_connectivity,
        capabilities=["market-scan", "quote-snapshots", "symbol-overview"],
        legacy_compat=legacy_boundary_status("market"),
    )


@app.get("/api/v1/market/bootstrap")
async def bootstrap_market(session: dict = Depends(get_current_session)):
    return {
        "success": True,
        "data": {
            "service": "market-service",
            "status": "live",
            "backfillStatus": HistoricalMarketDataService.get_backfill_status(),
            "latestMarketScans": DailyMarketScanService.get_latest_scans(),
            "latestMarketInsights": MarketInsightService.get_latest_snapshots(
                user_id=int(session["user_id"])
            ),
            "longbridge": {
                "runtime": _longbridge_runtime(),
                "catalog": _longbridge_catalog(),
            },
            "legacySources": [
                "refactor-v2/backend-server/src/core/analysis/HistoricalMarketDataService.py",
                "refactor-v2/backend-server/src/core/analysis/IndicatorSnapshotService.py",
                "refactor-v2/backend-server/src/api/data_routes.py",
                "refactor-v2/backend-server/src/api/platform_routes.py",
            ],
        },
    }


@app.get("/api/v1/market/backfill/status")
async def backfill_status(_: dict = Depends(get_current_session)):
    data = await asyncio.to_thread(HistoricalMarketDataService.get_backfill_status)
    return {"success": True, "data": data}


@app.get("/api/v1/market/history")
async def get_market_history(
    symbol: str,
    timeframe: str = "daily",
    limit: int = 180,
    refresh: bool = False,
    session: dict = Depends(get_current_session),
):
    payload = await asyncio.to_thread(
        HistoricalMarketDataService.get_history,
        symbol=symbol,
        timeframe=timeframe,
        limit=limit,
        user_id=int(session["user_id"]),
        refresh=refresh,
    )
    return {
        "success": True,
        "data": payload,
        "meta": _build_market_history_meta(
            symbols=[HistoricalMarketDataService.normalize_symbol(symbol)],
            timeframe=timeframe,
            limit=limit,
            payload={
                "series": [
                    {
                        "summary": payload.get("summary") if isinstance(payload.get("summary"), dict) else {},
                        "updatedAt": payload.get("updatedAt"),
                    }
                ]
            },
        ),
    }


@app.get("/api/v1/market/history/coverage")
async def market_history_coverage(
    search: str = "",
    status: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    expected_start: Optional[str] = Query(default=None, alias="expectedStart"),
    expected_end: Optional[str] = Query(default=None, alias="expectedEnd"),
    _: dict = Depends(get_current_session),
):
    cache_key = _build_history_coverage_cache_key(
        start_date=_HISTORY_COVERAGE_START_DATE,
        search=search,
        status=status,
        page=page,
        page_size=page_size,
        expected_start=expected_start,
        expected_end=expected_end,
    )
    payload = _get_history_coverage_cache(cache_key)
    if payload is None:
        payload = await asyncio.to_thread(
            _load_history_coverage_payload,
            start_date=_HISTORY_COVERAGE_START_DATE,
            search=search,
            status=status,
            page=page,
            page_size=page_size,
        )
        payload = _set_history_coverage_cache(cache_key, payload)
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    backfill_status = await asyncio.to_thread(HistoricalMarketDataService.get_backfill_status)
    backfill_task = backfill_status.get("task") if isinstance(backfill_status, dict) else {}
    if isinstance(backfill_task, dict):
        summary = {
            **summary,
            "task": backfill_task,
            "backfillTask": backfill_task,
        }
    total = int(payload.get("total") or 0)
    return {
        "success": True,
        "data": {
            "summary": summary,
            "items": payload.get("items") or [],
            "page": int(page),
            "pageSize": int(page_size),
            "total": total,
        },
        "meta": _build_history_coverage_meta(
            start_date=_HISTORY_COVERAGE_START_DATE,
            search=search,
            status=status,
            page=page,
            page_size=page_size,
            total=total,
            summary=summary,
        ),
    }


@app.post("/api/v1/market/history/backfill")
async def market_history_backfill(
    payload: Optional[Dict[str, Any]] = Body(default=None),
    session: dict = Depends(get_current_session),
):
    body = payload if isinstance(payload, dict) else {}
    raw_symbol = str(body.get("symbol") or body.get("code") or "").strip()
    if not raw_symbol:
        raise HTTPException(status_code=400, detail="symbol 不能为空")

    start_date = _parse_date(
        body.get("startDate") or body.get("start_date"),
        "startDate",
    ) or _HISTORY_COVERAGE_START_DATE
    end_date = _parse_date(
        body.get("endDate") or body.get("end_date"),
        "endDate",
    ) or date.today()
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="endDate 不能早于 startDate")

    normalized_symbol = HistoricalMarketDataService.normalize_symbol(raw_symbol)
    with _HISTORY_BACKFILL_LOCK:
        if normalized_symbol in _HISTORY_BACKFILL_SYMBOLS:
            raise HTTPException(status_code=409, detail=f"{normalized_symbol} 正在补价，请稍后刷新")
        _HISTORY_BACKFILL_SYMBOLS.add(normalized_symbol)

    try:
        result = await asyncio.to_thread(
            HistoricalMarketDataService.backfill_symbol_history,
            symbol=normalized_symbol,
            start_date=start_date,
            end_date=end_date,
            user_id=int(session["user_id"]),
        )
        _clear_history_coverage_cache()
    finally:
        with _HISTORY_BACKFILL_LOCK:
            _HISTORY_BACKFILL_SYMBOLS.discard(normalized_symbol)

    return {
        "success": True,
        "data": {
            "symbol": normalized_symbol,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            **(result if isinstance(result, dict) else {"result": result}),
        },
        "meta": {
            "readModel": "market-history-coverage",
            "operation": "single-symbol-backfill",
            "dataSource": "skshare-backfill",
            "cacheInvalidated": True,
        },
    }


@app.get("/api/v1/market/history/compare")
async def compare_market_history(
    symbols: List[str] = Query(default=[]),
    symbol: Optional[str] = None,
    timeframe: str = "daily",
    limit: int = 180,
    refresh: bool = False,
    session: dict = Depends(get_current_session),
):
    parsed_symbols = _parse_symbols(symbols, symbol)
    payload = await asyncio.to_thread(
        HistoricalMarketDataService.get_compare_history,
        symbols=parsed_symbols,
        timeframe=timeframe,
        limit=limit,
        user_id=int(session["user_id"]),
        refresh=refresh,
    )
    return {
        "success": True,
        "data": payload,
        "meta": _build_market_history_meta(
            symbols=parsed_symbols,
            timeframe=timeframe,
            limit=limit,
            payload=payload if isinstance(payload, dict) else {},
        ),
    }


@app.get("/api/v1/market/insights")
async def market_insights(
    market: str = "",
    generated_at: str = "",
    session: dict = Depends(get_current_session),
):
    normalized_market = str(market or "").strip().upper()
    if generated_at:
        data = MarketInsightService.get_snapshots_by_generated_at(generated_at, market=normalized_market)
    elif normalized_market:
        latest = MarketInsightService.get_latest_snapshots(user_id=int(session["user_id"]))
        data = [item for item in latest if item.get("market") == normalized_market]
    else:
        data = MarketInsightService.get_latest_snapshots(user_id=int(session["user_id"]))
    return {
        "success": True,
        "data": data,
        "meta": _build_market_insight_meta(
            data=data,
            market=normalized_market,
            generated_at=generated_at,
        ),
    }


@app.get("/api/v1/market/insights/history")
async def market_insight_history(
    market: str = "",
    limit: int = Query(default=24, ge=1, le=120),
    _: dict = Depends(get_current_session),
):
    return {
        "success": True,
        "data": MarketInsightService.list_snapshot_points(market=market, limit=limit),
    }


@app.get("/api/v1/market/scans")
async def market_scans(
    refresh: bool = False,
    session: dict = Depends(get_current_session),
):
    scans = DailyMarketScanService.get_latest_scans()
    if refresh or not scans:
        try:
            DailyMarketScanService.refresh_all_markets(user_id=int(session["user_id"]))
        except Exception:
            pass
        scans = DailyMarketScanService.get_latest_scans()
    return {"success": True, "data": scans}


@app.get("/api/v1/market/stock-pool")
async def stock_pool(
    request: Request,
    market: str = "all",
    search: str = "",
    group_id: str = "",
    asset_type: str = Query(default="", alias="type"),
    symbol: str = "",
    name: str = "",
    column_market: str = "",
    column_type: str = "",
    price_min: Optional[float] = Query(default=None),
    price_max: Optional[float] = Query(default=None),
    change_percent: Optional[float] = Query(default=None),
    volume_min: Optional[float] = Query(default=None),
    volume_max: Optional[float] = Query(default=None),
    market_cap_min: Optional[float] = Query(default=None),
    market_cap_max: Optional[float] = Query(default=None),
    pe: Optional[float] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    requested_asset_type = str(request.query_params.get("asset_type") or asset_type or "").strip()
    filters = _build_stock_pool_filters(
        asset_type=requested_asset_type,
        symbol=symbol,
        name=name,
        column_market=column_market,
        column_type=column_type,
        price_min=_coerce_optional_float(price_min, "price_min"),
        price_max=_coerce_optional_float(price_max, "price_max"),
        change_percent=_coerce_optional_float(change_percent, "change_percent"),
        volume_min=_coerce_optional_float(volume_min, "volume_min"),
        volume_max=_coerce_optional_float(volume_max, "volume_max"),
        market_cap_min=_coerce_optional_float(market_cap_min, "market_cap_min"),
        market_cap_max=_coerce_optional_float(market_cap_max, "market_cap_max"),
        pe=_coerce_optional_float(pe, "pe"),
    )

    def load_payload() -> Dict[str, Any]:
        MarketUniverseSync.ensure_schema()
        WatchlistService.ensure_schema()
        return load_stock_pool_page(
            market=market,
            user_id=user_id,
            search=search,
            group_id=group_id,
            page=page,
            page_size=page_size,
            filters=filters,
        )

    page_payload = await asyncio.to_thread(load_payload)
    paged_items = page_payload["items"]
    total = int(page_payload["total"])
    stats = await asyncio.to_thread(build_stock_pool_stats, user_id=user_id, group_id=group_id)
    stats["filtered_total"] = total
    return {
        "success": True,
        "data": paged_items,
        "stocks": paged_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "stats": stats,
        "meta": _build_stock_pool_meta(
            market=market,
            search=search,
            group_id=group_id,
            page=page,
            page_size=page_size,
            total=total,
            items=paged_items,
        ),
    }


@app.get("/api/v1/market/quote-snapshots")
async def quote_snapshots(
    symbols: List[str] = Query(default=[]),
    symbol: Optional[str] = None,
    max_age_minutes: int = Query(default=20, ge=1, le=240),
    _: dict = Depends(get_current_session),
):
    requested_symbols = _parse_symbols(symbols, symbol)
    if not requested_symbols:
        return {"success": True, "data": []}

    snapshot_map = QuoteSnapshotService.get_latest_map(
        requested_symbols,
        max_age_minutes=max_age_minutes,
    )
    return {
        "success": True,
        "data": [snapshot_map[item] for item in requested_symbols if item in snapshot_map],
        "meta": {
            "requested": len(requested_symbols),
            "resolved": len(snapshot_map),
            "maxAgeMinutes": max_age_minutes,
            "dataSource": "quote-snapshots",
        },
    }


@app.get("/api/v1/market/watchlist")
async def list_watchlist(
    market: str = "",
    asset_type: str = Query(default="", alias="type"),
    symbol: str = "",
    scan_session: str = Query(default="", alias="session"),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])

    def load_payload() -> List[Dict[str, Any]]:
        return WatchlistService.list_watchlist(
            user_id=user_id,
            market=market,
            asset_type=asset_type,
            symbol=symbol,
            session_filter=scan_session,
        )

    items = await asyncio.to_thread(load_payload)
    return {
        "success": True,
        "data": items,
        "total": len(items),
    }


@app.post("/api/v1/market/watchlist")
async def add_watchlist_item(
    payload: Dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])

    def write_payload() -> Dict[str, Any]:
        return WatchlistService.upsert_watchlist_item(user_id=user_id, payload=payload)

    try:
        item = await asyncio.to_thread(write_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "success": True,
        "message": "添加成功",
        "data": item,
    }


@app.put("/api/v1/market/watchlist/{symbol}")
async def update_watchlist_item(
    symbol: str,
    payload: Dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])

    def write_payload() -> Dict[str, Any]:
        next_payload = dict(payload or {})
        next_payload["symbol"] = symbol
        return WatchlistService.upsert_watchlist_item(user_id=user_id, payload=next_payload)

    try:
        item = await asyncio.to_thread(write_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "success": True,
        "message": "更新成功",
        "data": item,
    }


@app.delete("/api/v1/market/watchlist/{symbol}")
async def delete_watchlist_item(
    symbol: str,
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])

    def remove_payload() -> int:
        return WatchlistService.delete_watchlist_item(user_id=user_id, symbol=symbol)

    affected = await asyncio.to_thread(remove_payload)
    return {
        "success": True,
        "message": "删除成功",
        "deleted": bool(affected),
    }


@app.post("/api/v1/market/watchlist/scan-targets")
async def watchlist_scan_targets(
    payload: Dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    market = str(payload.get("market") or "").strip()
    asset_type = str(payload.get("asset_type") or payload.get("type") or "").strip()
    scan_session = str(payload.get("session") or payload.get("trade_session") or "").strip()

    def load_payload() -> Dict[str, Any]:
        return WatchlistService.build_scan_targets_response(
            user_id=user_id,
            market=market,
            asset_type=asset_type,
            session_filter=scan_session,
        )

    result = await asyncio.to_thread(load_payload)
    return {
        "success": True,
        "data": result["targets"],
        "targets": result["targets"],
        "total": result["total"],
        "filters": result["filters"],
        "markets": result["markets"],
        "types": result["types"],
    }


@app.post("/api/v1/market/stock-pool/sync-universe")
async def sync_stock_universe(
    payload: Dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    markets = payload.get("markets") or ["US", "HK", "CN"]
    if isinstance(markets, str):
        markets = [markets]
    result = MarketUniverseSync.sync_markets(markets=markets, user_id=int(session["user_id"]))
    message = "市场全量数据同步完成"
    if result.get("warning_count"):
        message = "市场数据已同步，部分外部数据源使用降级数据"
    return {"success": True, "message": message, "data": result}


@app.get("/api/v1/market/stock-groups")
async def stock_groups(
    market: str = "all",
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    where_clause = "WHERE is_active = 1 AND (user_id = %s OR user_id = 1)"
    params: List[Any] = [user_id]
    if market != "all":
        where_clause += " AND market = %s"
        params.append(market)

    rows = DbUtil.fetch_all(
        f"""
        SELECT id, market, name, color, sort_order, is_default
        FROM stock_groups
        {where_clause}
        ORDER BY market, sort_order
        """,
        tuple(params),
    )
    groups = [
        {
            "id": row.get("id"),
            "market": row.get("market"),
            "name": row.get("name"),
            "color": row.get("color"),
            "sort_order": row.get("sort_order"),
            "is_default": row.get("is_default"),
        }
        for row in rows
    ]
    return {"success": True, "data": groups}


@app.post("/api/v1/market/stock-groups")
async def create_stock_group(
    payload: Dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    market = str(payload.get("market") or "").strip().upper()
    name = str(payload.get("name") or "").strip()
    color = str(payload.get("color") or "#667eea").strip()
    if not market or not name:
        raise HTTPException(status_code=400, detail="市场和名称不能为空")

    DbUtil.execute(
        """
        INSERT INTO stock_groups (user_id, market, name, color)
        VALUES (%s, %s, %s, %s)
        """,
        (int(session["user_id"]), market, name, color),
    )
    return {"success": True, "message": "创建成功"}


@app.delete("/api/v1/market/stock-groups/{group_id}")
async def delete_stock_group(group_id: int, _: dict = Depends(get_current_session)):
    DbUtil.execute("UPDATE stock_groups SET is_active = 0 WHERE id = %s", (group_id,))
    return {"success": True, "message": "删除成功"}


@app.put("/api/v1/market/stock-pool/group")
async def update_stock_group_assignment(
    payload: Dict[str, Any] = Body(default={}),
    _: dict = Depends(get_current_session),
):
    MarketUniverseSync.ensure_schema()
    symbols = payload.get("symbols") or []
    if not symbols:
        raise HTTPException(status_code=400, detail="股票代码不能为空")
    table = resolve_stock_pool_table(
        payload.get("market", "US"),
        payload.get("type", "stock"),
    )["table"]
    for symbol in symbols:
        DbUtil.execute(f"UPDATE {table} SET group_id = %s WHERE symbol = %s", (payload.get("group_id"), symbol))
    return {"success": True, "message": f"成功更新 {len(symbols)} 只股票的分组"}


@app.put("/api/v1/market/stock-pool/broker")
async def update_stock_broker(
    payload: Dict[str, Any] = Body(default={}),
    _: dict = Depends(get_current_session),
):
    MarketUniverseSync.ensure_schema()
    symbols = payload.get("symbols") or []
    if not symbols:
        raise HTTPException(status_code=400, detail="股票代码不能为空")
    table = resolve_stock_pool_table(
        payload.get("market", "US"),
        payload.get("type", "stock"),
    )["table"]
    for symbol in symbols:
        DbUtil.execute(
            f"UPDATE {table} SET broker_account_id = %s WHERE symbol = %s",
            (payload.get("broker_account_id"), symbol),
        )
    return {"success": True, "message": f"成功更新 {len(symbols)} 只股票的券商账户"}


@app.post("/api/v1/market/stock-pool")
async def add_stock_to_pool(
    payload: Dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    MarketUniverseSync.ensure_schema()
    symbol = normalize_market_symbol(payload.get("symbol"))
    if not symbol:
        raise HTTPException(status_code=400, detail="股票代码不能为空")

    table_config = resolve_stock_pool_table(
        payload.get("market", "US"),
        payload.get("type", "stock"),
    )
    sql = f"""
        INSERT INTO {table_config['table']} (
            symbol, {table_config['name_field']}, market, {table_config['category_field']},
            user_id, group_id, broker_account_id, is_active
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
        ON DUPLICATE KEY UPDATE
        {table_config['name_field']} = VALUES({table_config['name_field']}),
        market = VALUES(market),
        user_id = VALUES(user_id),
        group_id = VALUES(group_id),
        broker_account_id = VALUES(broker_account_id),
        is_active = 1
    """
    DbUtil.execute(
        sql,
        (
            symbol,
            str(payload.get("name") or symbol),
            table_config["market"],
            str(payload.get("category") or ""),
            int(session["user_id"]),
            payload.get("group_id"),
            payload.get("broker_account_id"),
        ),
    )
    return {"success": True, "message": "添加成功"}


@app.delete("/api/v1/market/stock-pool/{symbol}")
async def remove_stock_from_pool(
    symbol: str,
    market: str = Query(default="US"),
    asset_type: str = Query(default="stock", alias="type"),
    _: dict = Depends(get_current_session),
):
    MarketUniverseSync.ensure_schema()
    table = resolve_stock_pool_table(market, asset_type)["table"]
    DbUtil.execute(f"UPDATE {table} SET is_active = 0 WHERE symbol = %s", (symbol,))
    return {"success": True, "message": "删除成功"}


@app.get("/api/v1/market/symbols/{symbol}/overview")
async def symbol_overview(
    symbol: str,
    include: str = Query(default="all", pattern="^(all|core)$"),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    response_mode = "core" if str(include or "all").lower() == "core" else "all"
    cache_key = ("symbol-overview", response_mode, user_id, normalized_symbol)
    cached_payload = _live_cache_get(cache_key)
    if cached_payload:
        return cached_payload

    overview = IndicatorSnapshotService.get_symbol_overview(
        normalized_symbol,
        user_id=user_id,
        allow_refresh=response_mode != "core",
    )
    if response_mode == "core":
        history = {"items": [], "summary": {}}
        latest_ai_payload = None
        latest_trend_scan = None
        market_insight = None
        market_scan = None
        quote_snapshot = QuoteSnapshotService.get_latest(normalized_symbol, max_age_minutes=20)
        content_cache = _empty_content_cache_bundle()
        deferred_sections = [
            "history",
            "latestAiAnalysis",
            "latestTrendScan",
            "marketInsight",
            "marketScan",
            "contentCache",
        ]
        payload = {
            "success": True,
            "data": {
                **overview,
                "history": history,
                "latestAiAnalysis": latest_ai_payload,
                "latestTrendScan": latest_trend_scan,
                "marketInsight": market_insight,
                "marketScan": market_scan,
                "quoteSnapshot": quote_snapshot,
                "contentCache": content_cache,
                "meta": _build_symbol_overview_meta(
                    overview=overview,
                    history=history,
                    latest_ai_payload=latest_ai_payload,
                    latest_trend_scan=latest_trend_scan,
                    market_insight=market_insight,
                    market_scan=market_scan,
                    quote_snapshot=quote_snapshot,
                    content_cache=content_cache,
                    response_mode="core",
                    deferred_sections=deferred_sections,
                ),
            },
        }
        return _live_cache_set(cache_key, payload, _SYMBOL_OVERVIEW_CACHE_TTL_SECONDS)

    history = HistoricalMarketDataService.get_history(
        normalized_symbol,
        timeframe="daily",
        limit=120,
        user_id=user_id,
    )
    latest_ai = get_persistence_manager().get_latest_ai_analysis(normalized_symbol, user_id=user_id)
    latest_ai_payload = latest_ai.to_dict() if latest_ai else None
    market_insights = {
        item["market"]: item
        for item in MarketInsightService.get_latest_snapshots(user_id=user_id)
    }
    market_scans = {item["market"]: item for item in DailyMarketScanService.get_latest_scans()}
    latest_trend_scan = DailySymbolTrendScanService.get_latest_for_symbol(normalized_symbol)
    quote_snapshot = QuoteSnapshotService.get_latest(normalized_symbol, max_age_minutes=20)
    content_cache = _content_cache_bundle(normalized_symbol)

    payload = {
        "success": True,
        "data": {
            **overview,
            "history": history,
            "latestAiAnalysis": latest_ai_payload,
            "latestTrendScan": latest_trend_scan,
            "marketInsight": market_insights.get(overview.get("market")),
            "marketScan": market_scans.get(overview.get("market")),
            "quoteSnapshot": quote_snapshot,
            "contentCache": content_cache,
            "meta": _build_symbol_overview_meta(
                overview=overview,
                history=history,
                latest_ai_payload=latest_ai_payload,
                latest_trend_scan=latest_trend_scan,
                market_insight=market_insights.get(overview.get("market")),
                market_scan=market_scans.get(overview.get("market")),
                quote_snapshot=quote_snapshot,
                content_cache=content_cache,
            ),
        },
    }
    return _live_cache_set(cache_key, payload, _SYMBOL_OVERVIEW_CACHE_TTL_SECONDS)


@app.get("/api/v1/market/runtime")
async def runtime_summary(session: dict = Depends(get_current_session)):
    return {
        "success": True,
        "data": {
            "userId": int(session["user_id"]),
            "service": "market-service",
            "phase": "phase-1-live",
            "port": PORT,
            "refreshable": {
                "history": True,
                "marketScans": True,
                "marketInsights": False,
                "longbridgePull": True,
            },
            "longbridge": _longbridge_runtime(),
        },
    }


@app.get("/api/v1/market/longbridge/bootstrap")
async def longbridge_bootstrap(session: dict = Depends(get_current_session)):
    return {
        "success": True,
        "data": {
            "userId": int(session["user_id"]),
            "runtime": _longbridge_runtime(),
            "catalog": _longbridge_catalog(),
            "storagePolicy": {
                "database": [
                    "history-candlesticks",
                ],
                "live": [
                    "quotes",
                    "option quotes",
                    "warrant quotes",
                    "depth",
                    "brokers",
                    "trades",
                    "intraday",
                    "capital flow",
                    "capital distribution",
                    "calc indexes",
                    "market temperature",
                ],
                "snapshot": [
                    "participants",
                    "option expiry dates",
                    "option chain",
                    "warrant issuers",
                    "trading session",
                    "trading days",
                    "security list",
                    "history market temperature",
                    "announcements",
                    "content news",
                    "content topics",
                ],
                "stream": [
                    "push quote",
                    "push depth",
                    "push brokers",
                    "push trades",
                    "push candlestick",
                ],
            },
        },
    }


@app.get("/api/v1/market/longbridge/catalog")
async def longbridge_catalog(_: dict = Depends(get_current_session)):
    return {"success": True, "data": _longbridge_catalog()}


@app.get("/api/v1/market/longbridge/runtime")
async def longbridge_runtime(_: dict = Depends(get_current_session)):
    return {"success": True, "data": _longbridge_runtime()}


@app.get("/api/v1/market/longbridge/static-info")
async def longbridge_static_info(
    symbols: List[str] = Query(default=[]),
    symbol: Optional[str] = None,
    session: dict = Depends(get_current_session),
):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.static_info(_require_symbols(symbols, symbol))
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/quotes")
async def longbridge_quotes(
    symbols: List[str] = Query(default=[]),
    symbol: Optional[str] = None,
    session: dict = Depends(get_current_session),
):
    return await _load_longbridge_quotes(
        user_id=int(session["user_id"]),
        symbols=_require_symbols(symbols, symbol),
    )


@app.get("/api/v1/market/longbridge/options/quotes")
async def longbridge_option_quotes(
    symbols: List[str] = Query(default=[]),
    symbol: Optional[str] = None,
    session: dict = Depends(get_current_session),
):
    if not _quote_capability("option_quote"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持期权实时行情接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.option_quote(_require_symbols(symbols, symbol))
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/warrants/quotes")
async def longbridge_warrant_quotes(
    symbols: List[str] = Query(default=[]),
    symbol: Optional[str] = None,
    session: dict = Depends(get_current_session),
):
    if not _quote_capability("warrant_quote"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持轮证实时行情接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.warrant_quote(_require_symbols(symbols, symbol))
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/depth")
async def longbridge_depth(symbol: str, session: dict = Depends(get_current_session)):
    return await _load_longbridge_depth(user_id=int(session["user_id"]), symbol=symbol)


@app.get("/api/v1/market/longbridge/brokers")
async def longbridge_brokers(symbol: str, session: dict = Depends(get_current_session)):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.brokers(HistoricalMarketDataService.normalize_symbol(symbol))
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/participants")
async def longbridge_participants(session: dict = Depends(get_current_session)):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.participants()
    return {"success": True, "data": _serialize_live(payload, data_source="longbridge-snapshot")}


@app.get("/api/v1/market/longbridge/trades")
async def longbridge_trades(
    symbol: str,
    count: int = 50,
    session: dict = Depends(get_current_session),
):
    return await _load_longbridge_trades(
        user_id=int(session["user_id"]),
        symbol=symbol,
        count=count,
    )


@app.get("/api/v1/market/longbridge/snapshot")
async def longbridge_snapshot(
    symbol: str,
    count: int = 18,
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    safe_count = max(1, min(int(count or 18), 1000))
    cache_key = ("longbridge-snapshot", user_id, normalized_symbol, safe_count)
    cached_payload = _live_cache_get(cache_key, allow_stale=True)
    if cached_payload:
        return cached_payload

    ctx = _with_quote_context(user_id)
    quote_result, depth_result, trades_result = await asyncio.gather(
        _load_longbridge_quotes(user_id=user_id, symbols=[normalized_symbol], ctx=ctx),
        _load_longbridge_depth(user_id=user_id, symbol=normalized_symbol, ctx=ctx),
        _load_longbridge_trades(user_id=user_id, symbol=normalized_symbol, count=safe_count, ctx=ctx),
    )
    payload = {
        "symbol": normalized_symbol,
        "quote": _extract_live_payload(quote_result, []),
        "depth": _extract_live_payload(depth_result, {}),
        "trades": _extract_live_payload(trades_result, []),
        "sources": {
            "quote": _extract_live_source(quote_result),
            "depth": _extract_live_source(depth_result),
            "trades": _extract_live_source(trades_result),
        },
    }
    response = _live_response(payload, extra={"components": ["quote", "depth", "trades"]})
    return _live_cache_set(cache_key, response, _LIVE_MARKET_CACHE_TTL_SECONDS)


@app.get("/api/v1/market/longbridge/intraday")
async def longbridge_intraday(
    symbol: str,
    trade_session: str = "all",
    session: dict = Depends(get_current_session),
):
    ctx = _with_quote_context(int(session["user_id"]))
    parsed_session = parse_trade_sessions(trade_session)
    kwargs = {}
    if parsed_session is not None:
        kwargs["trade_sessions"] = parsed_session
    payload = ctx.intraday(HistoricalMarketDataService.normalize_symbol(symbol), **kwargs)
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/history-candlesticks")
async def longbridge_history_candlesticks(
    symbol: str,
    period: str = "day",
    adjust_type: str = "no_adjust",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    trade_session: str = "all",
    storage_mode: str = "auto",
    refresh: bool = False,
    limit: int = 180,
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    parsed_period = parse_period(period)
    parsed_adjust = parse_adjust_type(adjust_type)
    parsed_start = _parse_date(start_date, "start_date")
    parsed_end = _parse_date(end_date, "end_date")
    parsed_session = parse_trade_sessions(trade_session)
    normalized_storage = str(storage_mode or "auto").strip().lower()

    if (
        normalized_storage not in {"longbridge", "sdk", "live"}
        and str(parsed_period) == str(parse_period("day"))
    ):
        history = HistoricalMarketDataService.get_history(
            symbol=normalized_symbol,
            timeframe="daily",
            limit=max(1, min(int(limit or 180), 5000)),
            user_id=user_id,
            refresh=refresh,
        )
        items = history.get("items", [])
        if parsed_start:
            items = [item for item in items if (item.get("date") or item.get("trade_date") or "") >= parsed_start.isoformat()]
        if parsed_end:
            items = [item for item in items if (item.get("date") or item.get("trade_date") or "") <= parsed_end.isoformat()]
        history["items"] = items
        history["dataSource"] = "skshare"
        history["runtime"] = _longbridge_runtime()
        return {"success": True, "data": history}

    ctx = _with_quote_context(user_id)
    kwargs = {}
    if parsed_start is not None:
        kwargs["start"] = parsed_start
    if parsed_end is not None:
        kwargs["end"] = parsed_end
    if parsed_session is not None:
        kwargs["trade_sessions"] = parsed_session
    payload = ctx.history_candlesticks_by_date(
        normalized_symbol,
        parsed_period,
        parsed_adjust,
        **kwargs,
    )
    return {
        "success": True,
        "data": _serialize_live(
            payload,
            extra={
                "symbol": normalized_symbol,
                "period": period,
                "adjustType": adjust_type,
                "startDate": parsed_start.isoformat() if parsed_start else None,
                "endDate": parsed_end.isoformat() if parsed_end else None,
            },
        ),
    }


@app.get("/api/v1/market/longbridge/candlesticks")
async def longbridge_candlesticks(
    symbol: str,
    period: str = "day",
    adjust_type: str = "no_adjust",
    count: int = 30,
    trade_session: str = "all",
    session: dict = Depends(get_current_session),
):
    ctx = _with_quote_context(int(session["user_id"]))
    parsed_session = parse_trade_sessions(trade_session)
    kwargs = {}
    if parsed_session is not None:
        kwargs["trade_sessions"] = parsed_session
    payload = ctx.candlesticks(
        HistoricalMarketDataService.normalize_symbol(symbol),
        parse_period(period),
        max(1, min(int(count or 30), 1000)),
        parse_adjust_type(adjust_type),
        **kwargs,
    )
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/options/expiry-dates")
async def longbridge_option_expiry_dates(symbol: str, session: dict = Depends(get_current_session)):
    if not _quote_capability("option_chain_expiry_date_list"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持期权链到期日接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.option_chain_expiry_date_list(HistoricalMarketDataService.normalize_symbol(symbol))
    return {"success": True, "data": _serialize_live(payload, data_source="longbridge-snapshot")}


@app.get("/api/v1/market/longbridge/options/chain")
async def longbridge_option_chain(
    symbol: str,
    expiry_date: str,
    session: dict = Depends(get_current_session),
):
    if not _quote_capability("option_chain_info_by_date"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持期权链明细接口")
    parsed_expiry = _parse_date(expiry_date, "expiry_date")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.option_chain_info_by_date(
        HistoricalMarketDataService.normalize_symbol(symbol),
        parsed_expiry,
    )
    return {"success": True, "data": _serialize_live(payload, data_source="longbridge-snapshot")}


@app.get("/api/v1/market/longbridge/warrants/issuers")
async def longbridge_warrant_issuers(session: dict = Depends(get_current_session)):
    if not _quote_capability("warrant_issuers"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持轮证发行商接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.warrant_issuers()
    return {"success": True, "data": _serialize_live(payload, data_source="longbridge-snapshot")}


@app.get("/api/v1/market/longbridge/warrants/list")
async def longbridge_warrant_list(
    symbol: str,
    sort_by: str = "volume",
    sort_order: str = "desc",
    warrant_type: Optional[str] = None,
    issuer: Optional[int] = None,
    expiry_date: Optional[str] = None,
    price_type: Optional[str] = None,
    status: Optional[str] = None,
    session: dict = Depends(get_current_session),
):
    if not _quote_capability("warrant_list"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持轮证筛选接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.warrant_list(
        HistoricalMarketDataService.normalize_symbol(symbol),
        parse_warrant_sort_by(sort_by),
        parse_sort_order(sort_order),
        warrant_type=parse_warrant_type(warrant_type),
        issuer=issuer,
        expiry_date=parse_warrant_expiry_filter(expiry_date),
        price_type=parse_warrant_price_type(price_type),
        status=parse_warrant_status(status),
    )
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/trading-session")
async def longbridge_trading_session(session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    now = time.time()
    cached_payload = _TRADING_SESSION_CACHE.get("payload")
    if cached_payload and now < float(_TRADING_SESSION_CACHE.get("expires_at") or 0):
        return {"success": True, "data": cached_payload}

    try:
        def fetch_trading_session() -> Dict[str, Any]:
            ctx = _with_quote_context(user_id)
            return ctx.trading_session()

        payload = await asyncio.to_thread(fetch_trading_session)
        data = _serialize_live(
            payload,
            data_source="longbridge-snapshot",
            extra={"cacheHit": False},
        )
        _TRADING_SESSION_CACHE.update({
            "expires_at": now + _TRADING_SESSION_TTL_SECONDS,
            "payload": data,
        })
        return {"success": True, "data": data}
    except Exception as exc:
        print(f"[market-service] longbridge trading-session fallback: {exc}")
        fallback_payload = {
            "US": {"market": "US", "trade_sessions": []},
            "HK": {"market": "HK", "trade_sessions": []},
            "CN": {"market": "CN", "trade_sessions": []},
        }
        response = _fallback_live_payload(
            fallback_payload,
            reason=str(exc),
            data_source="market-schedule-fallback",
        )
        _TRADING_SESSION_CACHE.update({
            "expires_at": now + 30,
            "payload": response.get("data"),
        })
        return response


@app.get("/api/v1/market/longbridge/trading-days")
async def longbridge_trading_days(
    market: str,
    start_date: str,
    end_date: str,
    session: dict = Depends(get_current_session),
):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.trading_days(
        parse_market(market),
        _parse_date(start_date, "start_date"),
        _parse_date(end_date, "end_date"),
    )
    return {"success": True, "data": _serialize_live(payload, data_source="longbridge-snapshot")}


@app.get("/api/v1/market/longbridge/capital-flow")
async def longbridge_capital_flow(symbol: str, session: dict = Depends(get_current_session)):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.capital_flow(HistoricalMarketDataService.normalize_symbol(symbol))
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/capital-distribution")
async def longbridge_capital_distribution(symbol: str, session: dict = Depends(get_current_session)):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.capital_distribution(HistoricalMarketDataService.normalize_symbol(symbol))
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/calc-indexes")
async def longbridge_calc_indexes(
    symbols: List[str] = Query(default=[]),
    symbol: Optional[str] = None,
    indexes: List[str] = Query(default=[]),
    index: Optional[str] = None,
    session: dict = Depends(get_current_session),
):
    if CalcIndex is None or not _quote_capability("calc_indexes"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持计算指标接口")
    parsed_symbols = _require_symbols(symbols, symbol)
    parsed_indexes = parse_calc_indexes([*indexes, index or ""])
    if not parsed_indexes:
        raise HTTPException(status_code=400, detail="至少需要一个 index")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.calc_indexes(parsed_symbols, parsed_indexes)
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/security-list")
async def longbridge_security_list(
    market: str,
    category: Optional[str] = None,
    session: dict = Depends(get_current_session),
):
    if not _quote_capability("security_list"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持标的列表接口")
    ctx = _with_quote_context(int(session["user_id"]))
    kwargs = {}
    parsed_category = parse_security_list_category(category)
    if parsed_category is not None:
        kwargs["category"] = parsed_category
    payload = ctx.security_list(parse_market(market), **kwargs)
    return {"success": True, "data": _serialize_live(payload, data_source="longbridge-snapshot")}


@app.get("/api/v1/market/longbridge/market-temperature/current")
async def longbridge_market_temperature(
    market: str,
    session: dict = Depends(get_current_session),
):
    if not _quote_capability("market_temperature"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持市场温度接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.market_temperature(parse_market(market))
    return {"success": True, "data": _serialize_live(payload)}


@app.get("/api/v1/market/longbridge/market-temperature/history")
async def longbridge_market_temperature_history(
    market: str,
    start_date: str,
    end_date: str,
    session: dict = Depends(get_current_session),
):
    if not _quote_capability("history_market_temperature"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持历史市场温度接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.history_market_temperature(
        parse_market(market),
        _parse_date(start_date, "start_date"),
        _parse_date(end_date, "end_date"),
    )
    return {"success": True, "data": _serialize_live(payload, data_source="longbridge-snapshot")}


@app.get("/api/v1/market/longbridge/announcements")
async def longbridge_announcements(symbol: str, session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return _cached_content_payload(
        symbol=symbol,
        content_type="announcements",
        user_id=user_id,
        source_name="longbridge-filings",
        loader=lambda normalized_symbol: _with_quote_context(user_id).filings(normalized_symbol),
    )


@app.get("/api/v1/market/longbridge/content/news")
async def longbridge_content_news(symbol: str, session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return _cached_content_payload(
        symbol=symbol,
        content_type="news",
        user_id=user_id,
        source_name="longbridge-news",
        loader=lambda normalized_symbol: _with_content_context(user_id).news(normalized_symbol),
    )


@app.get("/api/v1/market/longbridge/content/topics")
async def longbridge_content_topics(symbol: str, session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return _cached_content_payload(
        symbol=symbol,
        content_type="topics",
        user_id=user_id,
        source_name="longbridge-topics",
        loader=lambda normalized_symbol: _with_content_context(user_id).topics(normalized_symbol),
    )


@app.get("/api/v1/market/longbridge/push/runtime")
async def longbridge_push_runtime(session: dict = Depends(get_current_session)):
    return {"success": True, "data": push_hub.runtime(int(session["user_id"]))}


@app.post("/api/v1/market/longbridge/push/subscribe")
async def longbridge_push_subscribe(
    payload: Dict[str, Any] = Body(default_factory=dict),
    session: dict = Depends(get_current_session),
):
    result = push_hub.subscribe(
        int(session["user_id"]),
        payload.get("symbols") or [payload.get("symbol")],
        payload.get("subTypes") or payload.get("sub_types") or ["quote"],
        trade_count=payload.get("tradeCount") or payload.get("trade_count") or 50,
    )
    return {"success": True, "data": result}


@app.post("/api/v1/market/longbridge/push/unsubscribe")
async def longbridge_push_unsubscribe(
    payload: Dict[str, Any] = Body(default_factory=dict),
    session: dict = Depends(get_current_session),
):
    result = push_hub.unsubscribe(
        int(session["user_id"]),
        payload.get("symbols") or [payload.get("symbol")],
        payload.get("subTypes") or payload.get("sub_types") or ["quote"],
    )
    return {"success": True, "data": result}


@app.post("/api/v1/market/longbridge/push/candlesticks/subscribe")
async def longbridge_push_subscribe_candlesticks(
    payload: Dict[str, Any] = Body(default_factory=dict),
    session: dict = Depends(get_current_session),
):
    result = push_hub.subscribe_candlesticks(
        int(session["user_id"]),
        str(payload.get("symbol") or "").strip(),
        str(payload.get("period") or "1m").strip(),
        trade_session=str(payload.get("tradeSession") or payload.get("trade_session") or "all").strip(),
        snapshot_count=payload.get("snapshotCount") or payload.get("snapshot_count") or 60,
    )
    return {"success": True, "data": result}


@app.post("/api/v1/market/longbridge/push/candlesticks/unsubscribe")
async def longbridge_push_unsubscribe_candlesticks(
    payload: Dict[str, Any] = Body(default_factory=dict),
    session: dict = Depends(get_current_session),
):
    result = push_hub.unsubscribe_candlesticks(
        int(session["user_id"]),
        str(payload.get("symbol") or "").strip(),
        str(payload.get("period") or "1m").strip(),
    )
    return {"success": True, "data": result}


@app.websocket("/ws/market/longbridge/push")
async def longbridge_push_socket(websocket: WebSocket):
    try:
        session = _extract_websocket_session(websocket)
    except HTTPException:
        await websocket.close(code=4401)
        return

    user_id = int(session["user_id"])
    await websocket.accept()
    try:
        await push_hub.connect(user_id, websocket)
        while True:
            message = await websocket.receive_text()
            if not message:
                continue
            try:
                payload = json.loads(message)
            except Exception:
                payload = {"action": str(message).strip()}

            action = str(payload.get("action") or "").strip().lower()
            if action == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "channel": "longbridge.push.system",
                        "receivedAt": datetime.now(timezone.utc).isoformat(),
                        "userId": user_id,
                    }
                )
            elif action == "runtime":
                await websocket.send_json(
                    {
                        "type": "system",
                        "channel": "longbridge.push.system",
                        "receivedAt": datetime.now(timezone.utc).isoformat(),
                        "userId": user_id,
                        "payload": push_hub.runtime(user_id),
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        push_hub.disconnect(user_id, websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
