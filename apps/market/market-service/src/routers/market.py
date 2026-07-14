from datetime import date
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from services.core import *

router = APIRouter()


@router.get("/health")
async def health():
    mysql_ok = bool(DbUtil.query_one("SELECT 1"))
    runtime = _longbridge_runtime()
    quote_ready = bool(runtime.get("capabilities", {}).get("quote"))
    content_ready = bool(runtime.get("capabilities", {}).get("contentNews"))
    deps = {
        "mysql": build_dependency_status(
            "mysql", "healthy" if mysql_ok else "degraded", detail="行情、指标与快照读写数据库"
        ),
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


@router.get("/api/v1/market/bootstrap")
async def bootstrap_market(session: dict = Depends(get_current_session)):
    return {
        "success": True,
        "data": {
            "service": "market-service",
            "status": "live",
            "backfillStatus": HistoricalMarketDataService.get_backfill_status(),
            "latestMarketScans": DailyMarketScanService.get_latest_scans(),
            "latestMarketInsights": MarketInsightService.get_latest_snapshots(user_id=int(session["user_id"])),
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


@router.get("/api/v1/market/backfill/status")
async def backfill_status(_: dict = Depends(get_current_session)):
    data = await asyncio.to_thread(HistoricalMarketDataService.get_backfill_status)
    return {"success": True, "data": data}


@router.get("/api/v1/market/history")
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


@router.get("/api/v1/market/history/coverage")
async def market_history_coverage(
    search: str = "",
    status: str = "",
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    expected_start: str | None = Query(default=None, alias="expectedStart"),
    expected_end: str | None = Query(default=None, alias="expectedEnd"),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    cache_key = _build_history_coverage_cache_key(
        user_id=user_id,
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
            user_id=user_id,
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


@router.post("/api/v1/market/history/backfill")
async def market_history_backfill(
    payload: dict[str, Any] | None = Body(default=None),
    session: dict = Depends(get_current_session),
):
    body = payload if isinstance(payload, dict) else {}
    raw_symbol = str(body.get("symbol") or body.get("code") or "").strip()
    if not raw_symbol:
        raise HTTPException(status_code=400, detail="symbol 不能为空")

    start_date = (
        _parse_date(
            body.get("startDate") or body.get("start_date"),
            "startDate",
        )
        or _HISTORY_COVERAGE_START_DATE
    )
    end_date = (
        _parse_date(
            body.get("endDate") or body.get("end_date"),
            "endDate",
        )
        or date.today()
    )
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


@router.get("/api/v1/market/history/compare")
async def compare_market_history(
    symbols: list[str] = Query(default=[]),
    symbol: str | None = None,
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


@router.get("/api/v1/market/insights")
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


@router.get("/api/v1/market/insights/history")
async def market_insight_history(
    market: str = "",
    limit: int = Query(default=24, ge=1, le=120),
    _: dict = Depends(get_current_session),
):
    return {
        "success": True,
        "data": MarketInsightService.list_snapshot_points(market=market, limit=limit),
    }


@router.get("/api/v1/market/scans")
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


@router.get("/api/v1/market/stock-pool")
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
    price_min: float | None = Query(default=None),
    price_max: float | None = Query(default=None),
    change_percent: float | None = Query(default=None),
    volume_min: float | None = Query(default=None),
    volume_max: float | None = Query(default=None),
    market_cap_min: float | None = Query(default=None),
    market_cap_max: float | None = Query(default=None),
    pe: float | None = Query(default=None),
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

    def load_payload() -> dict[str, Any]:
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


@router.get("/api/v1/market/quote-snapshots")
async def quote_snapshots(
    symbols: list[str] = Query(default=[]),
    symbol: str | None = None,
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


@router.get("/api/v1/market/watchlist")
async def list_watchlist(
    market: str = "",
    asset_type: str = Query(default="", alias="type"),
    symbol: str = "",
    scan_session: str = Query(default="", alias="session"),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])

    def load_payload() -> list[dict[str, Any]]:
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


@router.post("/api/v1/market/watchlist")
async def add_watchlist_item(
    payload: dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])

    def write_payload() -> dict[str, Any]:
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


@router.put("/api/v1/market/watchlist/{symbol}")
async def update_watchlist_item(
    symbol: str,
    payload: dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])

    def write_payload() -> dict[str, Any]:
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


@router.delete("/api/v1/market/watchlist/{symbol}")
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


@router.post("/api/v1/market/watchlist/scan-targets")
async def watchlist_scan_targets(
    payload: dict[str, Any] = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    market = str(payload.get("market") or "").strip()
    asset_type = str(payload.get("asset_type") or payload.get("type") or "").strip()
    scan_session = str(payload.get("session") or payload.get("trade_session") or "").strip()

    def load_payload() -> dict[str, Any]:
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


@router.post("/api/v1/market/stock-pool/sync-universe")
async def sync_stock_universe(
    payload: dict[str, Any] = Body(default={}),
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


@router.get("/api/v1/market/stock-groups")
async def stock_groups(
    market: str = "all",
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    where_clause = "WHERE is_active = 1 AND user_id = %s"
    params: list[Any] = [user_id]
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


@router.post("/api/v1/market/stock-groups")
async def create_stock_group(
    payload: dict[str, Any] = Body(default={}),
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


@router.delete("/api/v1/market/stock-groups/{group_id}")
async def delete_stock_group(group_id: int, _: dict = Depends(get_current_session)):
    DbUtil.execute("UPDATE stock_groups SET is_active = 0 WHERE id = %s", (group_id,))
    return {"success": True, "message": "删除成功"}


@router.put("/api/v1/market/stock-pool/group")
async def update_stock_group_assignment(
    payload: dict[str, Any] = Body(default={}),
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


@router.put("/api/v1/market/stock-pool/broker")
async def update_stock_broker(
    payload: dict[str, Any] = Body(default={}),
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


@router.post("/api/v1/market/stock-pool")
async def add_stock_to_pool(
    payload: dict[str, Any] = Body(default={}),
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


@router.delete("/api/v1/market/stock-pool/{symbol}")
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


@router.get("/api/v1/market/symbols/{symbol}/overview")
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
        quote_snapshot = await _load_symbol_live_quote(user_id, normalized_symbol)
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
    market_insights = {item["market"]: item for item in MarketInsightService.get_latest_snapshots(user_id=user_id)}
    market_scans = {item["market"]: item for item in DailyMarketScanService.get_latest_scans()}
    latest_trend_scan = DailySymbolTrendScanService.get_latest_for_symbol(normalized_symbol)
    quote_snapshot = await _load_symbol_live_quote(user_id, normalized_symbol)
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


@router.get("/api/v1/market/runtime")
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
