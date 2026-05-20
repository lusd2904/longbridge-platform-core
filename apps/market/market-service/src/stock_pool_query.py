from __future__ import annotations

from typing import Any, Dict, List, Optional

from apps.market.market_shared.boundary import iter_stock_pool_tables
from core.readmodel.QuoteSnapshotService import QuoteSnapshotService
from utils.DbUtil import DbUtil


def _table_exists(table_name: str) -> bool:
    row = DbUtil.query_one(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = %s",
        (table_name,),
    )
    return bool(row)


def _coerce_number(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sanitize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_asset_type(value: Any, fallback: str = "") -> str:
    token = str(value or fallback or "").strip().lower()
    if token in {"stock", "etf"}:
        return token
    return str(fallback or "").strip().lower()


def _normalize_exact_number_filters(filters: Dict[str, Any]) -> Dict[str, Optional[float]]:
    return {
        "change_percent": _coerce_number(filters.get("change_percent")),
        "pe": _coerce_number(filters.get("pe")),
    }


def _build_union_sql(
    table_configs: List[Dict[str, str]],
    user_id: int,
    search: str,
    group_id: str,
    filters: Dict[str, Any],
) -> tuple[str, tuple[Any, ...]]:
    clauses: List[str] = []
    params: List[Any] = []
    search_value = _sanitize_text(search)
    symbol_value = _sanitize_text(filters.get("symbol"))
    name_value = _sanitize_text(filters.get("name"))
    market_value = _sanitize_text(filters.get("column_market"))
    column_type = _normalize_asset_type(filters.get("column_type"))
    asset_type = _normalize_asset_type(filters.get("asset_type") or filters.get("type"), column_type)
    numeric_filters = {
        "price_min": _coerce_number(filters.get("price_min")),
        "price_max": _coerce_number(filters.get("price_max")),
        "volume_min": _coerce_number(filters.get("volume_min")),
        "volume_max": _coerce_number(filters.get("volume_max")),
        "market_cap_min": _coerce_number(filters.get("market_cap_min")),
        "market_cap_max": _coerce_number(filters.get("market_cap_max")),
    }
    exact_filters = _normalize_exact_number_filters(filters)

    for table_config in table_configs:
        table_name = str(table_config.get("table") or "").strip()
        table_asset_type = str(table_config.get("type") or "").strip().lower()
        table_market = str(table_config.get("market") or "").strip().upper()
        if not table_name or not _table_exists(table_name):
            continue
        if asset_type and table_asset_type != asset_type:
            continue
        if column_type and table_asset_type != column_type:
            continue
        if market_value and table_market != market_value:
            continue

        where_clauses = ["is_active = 1", "user_id = %s"]
        select_params: List[Any] = [int(user_id)]

        if search_value:
            where_clauses.append(f"(symbol LIKE %s OR {table_config['name_field']} LIKE %s)")
            select_params.extend([f"%{search_value}%", f"%{search_value}%"])

        if group_id:
            where_clauses.append("group_id = %s")
            select_params.append(group_id)

        if symbol_value:
            where_clauses.append("symbol LIKE %s")
            select_params.append(f"%{symbol_value}%")

        if name_value:
            where_clauses.append(f"{table_config['name_field']} LIKE %s")
            select_params.append(f"%{name_value}%")

        for field_name, column_name in (
            ("price_min", "current_price"),
            ("price_max", "current_price"),
            ("volume_min", "volume"),
            ("volume_max", "volume"),
            ("market_cap_min", "market_cap"),
            ("market_cap_max", "market_cap"),
        ):
            numeric_value = numeric_filters[field_name]
            if numeric_value is None:
                continue
            operator = ">=" if field_name.endswith("_min") else "<="
            where_clauses.append(f"{column_name} {operator} %s")
            select_params.append(numeric_value)

        for field_name, column_name in (
            ("change_percent", "change_percent"),
            ("pe", "pe_ratio"),
        ):
            exact_value = exact_filters[field_name]
            if exact_value is None:
                continue
            where_clauses.append(f"{column_name} = %s")
            select_params.append(exact_value)

        clauses.append(
            f"""
            SELECT
                symbol,
                {table_config['name_field']} AS display_name,
                market,
                {table_config['category_field']} AS display_category,
                group_id,
                current_price,
                change_percent,
                volume,
                market_cap,
                pe_ratio,
                '{table_asset_type}' AS asset_type,
                {0 if table_asset_type == 'etf' else 1} AS type_priority
            FROM {table_name}
            WHERE {' AND '.join(where_clauses)}
            """
        )
        params.extend(select_params)

    return "\nUNION ALL\n".join(clauses), tuple(params)


def _merge_quote_snapshot(base: Dict[str, Any], snapshot: Dict[str, Any] | None) -> Dict[str, Any]:
    merged = dict(base)
    quote_snapshot = snapshot or {}
    for source_key, target_key in (
        ("price", "price"),
        ("change", "change"),
        ("change_percent", "change_percent"),
        ("prev_close", "prev_close"),
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("volume", "volume"),
        ("turnover", "turnover"),
    ):
        if quote_snapshot.get(source_key) not in (None, ""):
            merged[target_key] = quote_snapshot.get(source_key)
    merged["quote_source"] = quote_snapshot.get("source") or merged.get("quote_source") or "universe"
    merged["quote_snapshot_at"] = quote_snapshot.get("snapshotAt") or merged.get("quote_snapshot_at")
    merged["quoteReady"] = bool(
        merged.get("quoteReady")
        or merged.get("price")
        or merged.get("prev_close")
        or merged.get("open")
        or merged.get("high")
        or merged.get("low")
        or merged.get("quote_snapshot_at")
    )
    return merged


def load_stock_pool_page(
    *,
    market: str,
    user_id: int,
    search: str,
    group_id: str,
    page: int,
    page_size: int,
    filters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    query_filters = dict(filters or {})
    table_configs = iter_stock_pool_tables(market)
    union_sql, union_params = _build_union_sql(table_configs, user_id, search, group_id, query_filters)
    if not union_sql:
        return {"items": [], "total": 0}

    deduped_sql = f"""
        SELECT *
        FROM (
            SELECT
                pool_union.*,
                ROW_NUMBER() OVER (
                    PARTITION BY symbol
                    ORDER BY type_priority ASC, symbol ASC
                ) AS row_rank
            FROM (
                {union_sql}
            ) AS pool_union
        ) AS ranked_pool
        WHERE row_rank = 1
    """

    count_sql = f"""
        SELECT COUNT(*) AS total
        FROM (
            {deduped_sql}
        ) AS deduped_pool
    """
    count_row = DbUtil.fetch_one(count_sql, union_params) or {}
    total = int(count_row.get("total") or 0)

    offset = max(page - 1, 0) * page_size
    page_sql = f"""
        SELECT
            deduped_pool.*,
            CASE WHEN watchlist.symbol IS NULL THEN 0 ELSE 1 END AS is_watchlisted,
            watchlist.added_at AS watchlisted_at
        FROM (
            {deduped_sql}
        ) AS deduped_pool
        LEFT JOIN user_watchlist_stocks AS watchlist
          ON watchlist.user_id = %s
         AND watchlist.symbol = deduped_pool.symbol
        ORDER BY deduped_pool.symbol
        LIMIT %s OFFSET %s
    """
    rows = DbUtil.fetch_all(page_sql, union_params + (int(user_id), int(page_size), int(offset))) or []
    quote_map = QuoteSnapshotService.get_latest_map([str(row.get("symbol") or "") for row in rows]) if rows else {}

    items: List[Dict[str, Any]] = []
    for row in rows:
        base = {
            "symbol": row.get("symbol"),
            "name": row.get("display_name") or row.get("symbol"),
            "market": row.get("market"),
            "sector": row.get("display_category") or "",
            "group_id": row.get("group_id"),
            "price": float(row.get("current_price")) if row.get("current_price") is not None else None,
            "change_percent": float(row.get("change_percent")) if row.get("change_percent") is not None else None,
            "volume": int(row.get("volume")) if row.get("volume") is not None else None,
            "market_cap": float(row.get("market_cap")) if row.get("market_cap") is not None else None,
            "pe": float(row.get("pe_ratio")) if row.get("pe_ratio") is not None else None,
            "prev_close": None,
            "open": None,
            "high": None,
            "low": None,
            "change": None,
            "turnover": None,
            "quote_source": "universe",
            "quote_snapshot_at": None,
            "quoteReady": bool(
                row.get("current_price") is not None
                or row.get("change_percent") is not None
                or row.get("volume") is not None
            ),
            "type": row.get("asset_type") or "stock",
            "asset_type": row.get("asset_type") or "stock",
            "isWatchlisted": bool(row.get("is_watchlisted")),
            "watchlistedAt": row.get("watchlisted_at"),
        }
        items.append(_merge_quote_snapshot(base, quote_map.get(str(row.get("symbol") or ""))))

    return {"items": items, "total": total}
