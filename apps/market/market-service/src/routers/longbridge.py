from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from services.core import *

router = APIRouter()


@router.get("/api/v1/market/longbridge/bootstrap")
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


@router.get("/api/v1/market/longbridge/catalog")
async def longbridge_catalog(_: dict = Depends(get_current_session)):
    return {"success": True, "data": _longbridge_catalog()}


@router.get("/api/v1/market/longbridge/runtime")
async def longbridge_runtime(_: dict = Depends(get_current_session)):
    return {"success": True, "data": _longbridge_runtime()}


@router.get("/api/v1/market/longbridge/static-info")
async def longbridge_static_info(
    symbols: list[str] = Query(default=[]),
    symbol: str | None = None,
    session: dict = Depends(get_current_session),
):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.static_info(_require_symbols(symbols, symbol))
    return {"success": True, "data": _serialize_live(payload)}


@router.get("/api/v1/market/longbridge/quotes")
async def longbridge_quotes(
    symbols: list[str] = Query(default=[]),
    symbol: str | None = None,
    session: dict = Depends(get_current_session),
):
    return await _load_longbridge_quotes(
        user_id=int(session["user_id"]),
        symbols=_require_symbols(symbols, symbol),
    )


@router.get("/api/v1/market/longbridge/options/quotes")
async def longbridge_option_quotes(
    symbols: list[str] = Query(default=[]),
    symbol: str | None = None,
    session: dict = Depends(get_current_session),
):
    if not _quote_capability("option_quote"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持期权实时行情接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.option_quote(_require_symbols(symbols, symbol))
    return {"success": True, "data": _serialize_live(payload)}


@router.get("/api/v1/market/longbridge/warrants/quotes")
async def longbridge_warrant_quotes(
    symbols: list[str] = Query(default=[]),
    symbol: str | None = None,
    session: dict = Depends(get_current_session),
):
    if not _quote_capability("warrant_quote"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持轮证实时行情接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.warrant_quote(_require_symbols(symbols, symbol))
    return {"success": True, "data": _serialize_live(payload)}


@router.get("/api/v1/market/longbridge/depth")
async def longbridge_depth(symbol: str, session: dict = Depends(get_current_session)):
    return await _load_longbridge_depth(user_id=int(session["user_id"]), symbol=symbol)


@router.get("/api/v1/market/longbridge/brokers")
async def longbridge_brokers(symbol: str, session: dict = Depends(get_current_session)):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.brokers(HistoricalMarketDataService.normalize_symbol(symbol))
    return {"success": True, "data": _serialize_live(payload)}


@router.get("/api/v1/market/longbridge/participants")
async def longbridge_participants(session: dict = Depends(get_current_session)):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.participants()
    return {"success": True, "data": _serialize_live(payload, data_source="longbridge-snapshot")}


@router.get("/api/v1/market/longbridge/trades")
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


@router.get("/api/v1/market/longbridge/snapshot")
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


@router.get("/api/v1/market/longbridge/intraday")
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


@router.get("/api/v1/market/longbridge/history-candlesticks")
async def longbridge_history_candlesticks(
    symbol: str,
    period: str = "day",
    adjust_type: str = "no_adjust",
    start_date: str | None = None,
    end_date: str | None = None,
    trade_session: str = "all",
    storage_mode: str = "auto",
    refresh: bool = False,
    limit: int = 180,
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    parsed_period = parse_period(period)
    parsed_start = _parse_date(start_date, "start_date")
    parsed_end = _parse_date(end_date, "end_date")
    normalized_storage = str(storage_mode or "auto").strip().lower()

    if normalized_storage in {"longbridge", "sdk", "live"}:
        raise HTTPException(
            status_code=410,
            detail="Longbridge 历史 K 线 SDK 路径已停用；请使用 storage_mode=auto/skshare 读取本地日线历史库",
        )

    if str(parsed_period) != str(parse_period("day")):
        raise HTTPException(
            status_code=410, detail="Longbridge 历史 K 线 SDK 路径已停用；该兼容端点仅提供日线历史库数据"
        )

    history = HistoricalMarketDataService.get_history(
        symbol=normalized_symbol,
        timeframe="daily",
        limit=max(1, min(int(limit or 180), 5000)),
        user_id=user_id,
        refresh=refresh,
    )
    items = history.get("items", [])
    if parsed_start:
        items = [
            item for item in items if (item.get("date") or item.get("trade_date") or "") >= parsed_start.isoformat()
        ]
    if parsed_end:
        items = [item for item in items if (item.get("date") or item.get("trade_date") or "") <= parsed_end.isoformat()]
    history["items"] = items
    history["dataSource"] = "market-price-history-daily"
    history["runtime"] = _longbridge_runtime()
    return {"success": True, "data": history}


@router.get("/api/v1/market/longbridge/candlesticks")
async def longbridge_candlesticks(
    symbol: str,
    period: str = "day",
    adjust_type: str = "no_adjust",
    count: int = 30,
    trade_session: str = "all",
    session: dict = Depends(get_current_session),
):
    raise HTTPException(
        status_code=410,
        detail="Longbridge K 线 SDK 路径已停用；日线历史请使用 /api/v1/market/longbridge/history-candlesticks?storage_mode=auto",
    )


@router.get("/api/v1/market/longbridge/options/expiry-dates")
async def longbridge_option_expiry_dates(symbol: str, session: dict = Depends(get_current_session)):
    if not _quote_capability("option_chain_expiry_date_list"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持期权链到期日接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.option_chain_expiry_date_list(HistoricalMarketDataService.normalize_symbol(symbol))
    return {"success": True, "data": _serialize_live(payload, data_source="longbridge-snapshot")}


@router.get("/api/v1/market/longbridge/options/chain")
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


@router.get("/api/v1/market/longbridge/warrants/issuers")
async def longbridge_warrant_issuers(session: dict = Depends(get_current_session)):
    if not _quote_capability("warrant_issuers"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持轮证发行商接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.warrant_issuers()
    return {"success": True, "data": _serialize_live(payload, data_source="longbridge-snapshot")}


@router.get("/api/v1/market/longbridge/warrants/list")
async def longbridge_warrant_list(
    symbol: str,
    sort_by: str = "volume",
    sort_order: str = "desc",
    warrant_type: str | None = None,
    issuer: int | None = None,
    expiry_date: str | None = None,
    price_type: str | None = None,
    status: str | None = None,
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


@router.get("/api/v1/market/longbridge/trading-session")
async def longbridge_trading_session(session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    now = time.time()
    cached_payload = _TRADING_SESSION_CACHE.get("payload")
    if cached_payload and now < float(_TRADING_SESSION_CACHE.get("expires_at") or 0):
        return {"success": True, "data": cached_payload}

    try:

        def fetch_trading_session() -> dict[str, Any]:
            ctx = _with_quote_context(user_id)
            return ctx.trading_session()

        payload = await asyncio.to_thread(fetch_trading_session)
        data = _serialize_live(
            payload,
            data_source="longbridge-snapshot",
            extra={"cacheHit": False},
        )
        _TRADING_SESSION_CACHE.update(
            {
                "expires_at": now + _TRADING_SESSION_TTL_SECONDS,
                "payload": data,
            }
        )
        return {"success": True, "data": data}
    except Exception as exc:
        _warn_live_fallback_once(
            "longbridge_trading_session",
            "Longbridge trading-session degraded: user_id=%s error=%s",
            user_id,
            exc,
        )
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
        _TRADING_SESSION_CACHE.update(
            {
                "expires_at": now + 30,
                "payload": response.get("data"),
            }
        )
        return response


@router.get("/api/v1/market/longbridge/trading-days")
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


@router.get("/api/v1/market/longbridge/capital-flow")
async def longbridge_capital_flow(symbol: str, session: dict = Depends(get_current_session)):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.capital_flow(HistoricalMarketDataService.normalize_symbol(symbol))
    return {"success": True, "data": _serialize_live(payload)}


@router.get("/api/v1/market/longbridge/capital-distribution")
async def longbridge_capital_distribution(symbol: str, session: dict = Depends(get_current_session)):
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.capital_distribution(HistoricalMarketDataService.normalize_symbol(symbol))
    return {"success": True, "data": _serialize_live(payload)}


@router.get("/api/v1/market/longbridge/calc-indexes")
async def longbridge_calc_indexes(
    symbols: list[str] = Query(default=[]),
    symbol: str | None = None,
    indexes: list[str] = Query(default=[]),
    index: str | None = None,
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


@router.get("/api/v1/market/longbridge/security-list")
async def longbridge_security_list(
    market: str,
    category: str | None = None,
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


@router.get("/api/v1/market/longbridge/market-temperature/current")
async def longbridge_market_temperature(
    market: str,
    session: dict = Depends(get_current_session),
):
    if not _quote_capability("market_temperature"):
        raise HTTPException(status_code=501, detail="当前 SDK 不支持市场温度接口")
    ctx = _with_quote_context(int(session["user_id"]))
    payload = ctx.market_temperature(parse_market(market))
    return {"success": True, "data": _serialize_live(payload)}


@router.get("/api/v1/market/longbridge/market-temperature/history")
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


@router.get("/api/v1/market/longbridge/announcements")
async def longbridge_announcements(symbol: str, session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return _cached_content_payload(
        symbol=symbol,
        content_type="announcements",
        user_id=user_id,
        source_name="longbridge-filings",
        loader=lambda normalized_symbol: _with_quote_context(user_id).filings(normalized_symbol),
    )


@router.get("/api/v1/market/longbridge/content/news")
async def longbridge_content_news(symbol: str, session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return _cached_content_payload(
        symbol=symbol,
        content_type="news",
        user_id=user_id,
        source_name="longbridge-news",
        loader=lambda normalized_symbol: _with_content_context(user_id).news(normalized_symbol),
    )


@router.get("/api/v1/market/longbridge/content/topics")
async def longbridge_content_topics(symbol: str, session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return _cached_content_payload(
        symbol=symbol,
        content_type="topics",
        user_id=user_id,
        source_name="longbridge-topics",
        loader=lambda normalized_symbol: _with_content_context(user_id).topics(normalized_symbol),
    )


@router.get("/api/v1/market/longbridge/push/runtime")
async def longbridge_push_runtime(session: dict = Depends(get_current_session)):
    return {"success": True, "data": push_hub.runtime(int(session["user_id"]))}


@router.post("/api/v1/market/longbridge/push/subscribe")
async def longbridge_push_subscribe(
    payload: dict[str, Any] = Body(default_factory=dict),
    session: dict = Depends(get_current_session),
):
    result = push_hub.subscribe(
        int(session["user_id"]),
        payload.get("symbols") or [payload.get("symbol")],
        payload.get("subTypes") or payload.get("sub_types") or ["quote"],
        trade_count=payload.get("tradeCount") or payload.get("trade_count") or 50,
    )
    return {"success": True, "data": result}


@router.post("/api/v1/market/longbridge/push/unsubscribe")
async def longbridge_push_unsubscribe(
    payload: dict[str, Any] = Body(default_factory=dict),
    session: dict = Depends(get_current_session),
):
    result = push_hub.unsubscribe(
        int(session["user_id"]),
        payload.get("symbols") or [payload.get("symbol")],
        payload.get("subTypes") or payload.get("sub_types") or ["quote"],
    )
    return {"success": True, "data": result}


@router.post("/api/v1/market/longbridge/push/candlesticks/subscribe")
async def longbridge_push_subscribe_candlesticks(
    payload: dict[str, Any] = Body(default_factory=dict),
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


@router.post("/api/v1/market/longbridge/push/candlesticks/unsubscribe")
async def longbridge_push_unsubscribe_candlesticks(
    payload: dict[str, Any] = Body(default_factory=dict),
    session: dict = Depends(get_current_session),
):
    result = push_hub.unsubscribe_candlesticks(
        int(session["user_id"]),
        str(payload.get("symbol") or "").strip(),
        str(payload.get("period") or "1m").strip(),
    )
    return {"success": True, "data": result}


@router.websocket("/ws/market/longbridge/push")
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
                        "receivedAt": datetime.now(UTC).isoformat(),
                        "userId": user_id,
                    }
                )
            elif action == "runtime":
                await websocket.send_json(
                    {
                        "type": "system",
                        "channel": "longbridge.push.system",
                        "receivedAt": datetime.now(UTC).isoformat(),
                        "userId": user_id,
                        "payload": push_hub.runtime(user_id),
                    }
                )
    except WebSocketDisconnect:
        pass
    finally:
        push_hub.disconnect(user_id, websocket)
