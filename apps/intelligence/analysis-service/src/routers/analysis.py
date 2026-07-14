from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from services.core import *

router = APIRouter()


@router.get("/health")
async def health():
    mysql_ok = bool(DbUtil.query_one("SELECT 1"))
    try:
        redis_ok = bool(redis_client.client.ping())
    except Exception:
        redis_ok = False
    deferred_jobs = _deferred_analysis_job_runtime()
    deps = {
        "mysql": build_dependency_status(
            "mysql", "healthy" if mysql_ok else "degraded", detail="分析历史与推荐读写数据库"
        ),
        "redis": build_dependency_status(
            "redis", "healthy" if redis_ok else "degraded", detail="AI 缓存与热点结果缓存"
        ),
        "deferredAnalysisJobs": build_dependency_status(
            "deferredAnalysisJobs",
            deferred_jobs["status"],
            detail=deferred_jobs["detail"],
            extra={
                "statusCounts": deferred_jobs["statusCounts"],
                "activeCount": deferred_jobs["activeCount"],
                "oldestActiveAgeSeconds": deferred_jobs["oldestActiveAgeSeconds"],
                "strandedThresholdSeconds": deferred_jobs["strandedThresholdSeconds"],
                "maxJobs": deferred_jobs["maxJobs"],
                "storage": deferred_jobs["storage"],
                "restartBehavior": deferred_jobs["restartBehavior"],
            },
        ),
    }
    return build_health_payload(
        service="analysis-service",
        version=app.version,
        port=PORT,
        status=summarize_status(deps.values()),
        deps=deps,
        capabilities=["ai-analysis", "recommendations", "finance-briefings"],
        legacy_compat=legacy_boundary_status("analysis"),
    )


@router.get("/api/v1/analysis/bootstrap")
async def bootstrap_analysis(session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return {
        "success": True,
        "data": {
            "service": "analysis-service",
            "status": "live",
            "provider": AIAnalyst._provider(user_id=user_id),
            "modelPlan": AIAnalyst.get_task_model_plan(user_id=user_id),
            "latestTrendScans": DailySymbolTrendScanService.get_latest_batch(limit=6),
            "recommendationProfiles": ["growth", "balanced", "value", "dividend"],
            "legacySources": [
                "refactor-v2/backend-server/src/api/ai_routes.py",
                "refactor-v2/backend-server/src/core/analysis/DailySymbolTrendScanService.py",
                "refactor-v2/backend-server/src/core/analysis/RecommendationService.py",
            ],
        },
    }


@router.get("/api/v1/analysis/models")
async def analysis_models(session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    return {
        "success": True,
        "data": {
            "catalog": AIAnalyst.get_model_catalog(user_id=user_id),
            "defaultPlan": AIAnalyst.get_task_model_plan(user_id=user_id),
            "providerPlan": AIAnalyst.get_task_provider_plan(user_id=user_id),
            "provider": AIAnalyst._provider(user_id=user_id),
        },
    }


@router.post("/api/v1/analysis/assistant/consult")
async def assistant_consult(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    question = _clip_assistant_text(
        payload.get("question") or payload.get("message") or payload.get("prompt"),
        _ASSISTANT_QUESTION_MAX_CHARS,
    )
    if not question:
        raise HTTPException(status_code=400, detail="咨询内容不能为空")

    _enforce_assistant_rate_limit(user_id)

    page_context = _normalize_assistant_context(payload.get("pageContext") or payload.get("page_context"))
    messages = _normalize_assistant_messages(payload.get("messages"))
    prompt = _build_assistant_consult_prompt(
        question=question,
        page_context=page_context,
        messages=messages,
    )
    answer = await asyncio.to_thread(
        AIAnalyst.get_decision,
        None,
        prompt,
        task="assistant",
        user_id=user_id,
    )
    answer_text = _repair_assistant_mojibake(answer)
    if not answer_text or answer_text.startswith("ERROR"):
        raise HTTPException(status_code=502, detail=AIAnalyst._build_business_error(answer_text))

    model_plan = AIAnalyst.get_task_model_plan(user_id=user_id)
    general_model = model_plan.get("general") if isinstance(model_plan, dict) else {}
    return {
        "success": True,
        "data": {
            "answer": answer_text,
            "createdAt": _utc_iso(),
            "model": general_model or {},
            "pageContext": page_context,
        },
    }


@router.post("/api/v1/analysis/analyze-positions")
async def analyze_positions(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    started_at = time.time()
    user_id = int(session["user_id"])
    positions = payload.get("positions") or []
    account_id = payload.get("account_id") or payload.get("accountId")
    force_refresh = bool(payload.get("force_refresh", payload.get("forceRefresh", True)))
    allow_single_quote_retry = bool(
        payload.get("allow_live_quote")
        or payload.get("allowLiveQuote")
        or payload.get("allow_single_quote_retry")
        or payload.get("allowSingleQuoteRetry")
    )
    model_plan = AIAnalyst.get_task_model_plan(user_id=user_id)

    if not positions:
        raise HTTPException(status_code=400, detail="持仓数据不能为空")

    original_positions = positions if isinstance(positions, list) else []
    positions, batch_meta = _normalize_position_batch_payload(original_positions)
    if batch_meta["partial"]:
        deferred_job = _enqueue_deferred_positions_analysis(
            positions=[item for item in original_positions if isinstance(item, dict)],
            base_payload={
                **payload,
                "force_refresh": force_refresh,
                "forceRefresh": force_refresh,
            },
            session={"user_id": user_id},
            model_plan=model_plan,
            batch_meta=batch_meta,
        )
        response_payload = {
            "success": True,
            "data": _build_deferred_analysis_placeholders(
                original_positions,
                model_plan=model_plan,
                sync_limit=int(batch_meta["syncLimit"]),
            ),
            "jobId": deferred_job["jobId"],
            "jobStatus": deferred_job["status"],
            "statusUrl": f"/api/v1/analysis/analyze-positions/jobs/{deferred_job['jobId']}",
            "jobExpiresAt": deferred_job.get("expiresAt"),
            "jobTtlSeconds": deferred_job.get("ttlSeconds"),
            "marketSummary": None,
            "modelPlan": model_plan,
            "message": f"批量分析请求共 {batch_meta['requested']} 只股票，超过同步上限 {batch_meta['syncLimit']}，已创建后台任务 {deferred_job['jobId']}",
            "duration": time.time() - started_at,
            "accepted": True,
            "degraded": True,
            "syncLimit": batch_meta["syncLimit"],
            "stats": {
                "total": batch_meta["requested"],
                "accepted": 0,
                "successful": 0,
                "failed": 0,
                "deferred": batch_meta["requested"],
            },
            "meta": {
                **batch_meta,
                "status": "accepted",
                "executionMode": "deferred",
                "jobId": deferred_job["jobId"],
                "jobExpiresAt": deferred_job.get("expiresAt"),
                "jobTtlSeconds": deferred_job.get("ttlSeconds"),
            },
        }
        return JSONResponse(status_code=202, content=response_payload)

    resolved_account_id = _resolve_analysis_account_id(user_id, account_id)
    results = []
    market_snapshot_cache: dict[str, dict] = {}
    response_market_summary = None
    normalized_symbols = [
        HistoricalMarketDataService.normalize_symbol(str(position.get("symbol") or "").strip())
        for position in positions
        if str(position.get("symbol") or "").strip()
    ]
    quote_cache = (
        get_quotes_from_broker(
            normalized_symbols,
            resolved_account_id,
            user_id=user_id,
        )
        if normalized_symbols and allow_single_quote_retry
        else {}
    )

    for position in positions:
        raw_symbol = str(position.get("symbol") or "").strip()
        if not raw_symbol:
            continue

        symbol = HistoricalMarketDataService.normalize_symbol(raw_symbol)
        current_price = 0.0
        volume = 0
        change_percent = 0.0
        prev_close = 0.0
        indicator_payload = {}
        indicator_meta = {"source": "", "warning": ""}
        market_snapshot = response_market_summary or {}

        try:
            cached_result = None if force_refresh else AICache.get_analysis(symbol, "combined")
            if cached_result and cached_result.get("scanLayers"):
                refreshed_cached_result = dict(cached_result)
                cached_quote = quote_cache.get(symbol) or {}
                if cached_quote:
                    current_price = float(cached_quote.get("last_price") or 0)
                    volume = int(cached_quote.get("volume") or 0)
                    change_percent = float(cached_quote.get("change_percent") or 0)
                    prev_close = float(cached_quote.get("prev_close") or 0)
                else:
                    current_price, volume, change_percent, prev_close = extract_position_quote_fallback(position)
                    if current_price <= 0:
                        current_price, volume, change_percent, prev_close = _extract_read_model_quote_fallback(symbol)
                    if current_price <= 0 and allow_single_quote_retry:
                        current_price, volume, change_percent, prev_close = get_quote_from_broker(
                            symbol, resolved_account_id, user_id=user_id
                        )
                market_key = detect_market(symbol)
                market_snapshot = market_snapshot_cache.get(market_key)
                if not market_snapshot:
                    market_snapshot = build_market_snapshot(resolved_account_id, symbol, user_id=user_id)
                    market_snapshot_cache[market_key] = market_snapshot

                if current_price > 0:
                    refreshed_cached_result.update(
                        {
                            "price": current_price,
                            "volume": volume,
                            "changePercent": change_percent,
                            "prevClose": prev_close,
                            "analysisTime": time.time(),
                            "timestamp": time.time(),
                        }
                    )
                refreshed_cached_result["marketSummary"] = market_snapshot
                refreshed_cached_result["modelPlan"] = model_plan
                refreshed_cached_result["source"] = "manual_scan"
                refreshed_cached_result["analysisMode"] = "manual_live_scan"
                results.append(refreshed_cached_result)
                response_market_summary = market_snapshot or response_market_summary
                continue

            cached_quote = quote_cache.get(symbol) or {}
            if cached_quote:
                current_price = float(cached_quote.get("last_price") or 0)
                volume = int(cached_quote.get("volume") or 0)
                change_percent = float(cached_quote.get("change_percent") or 0)
                prev_close = float(cached_quote.get("prev_close") or 0)
            else:
                current_price, volume, change_percent, prev_close = extract_position_quote_fallback(position)
                if current_price <= 0:
                    current_price, volume, change_percent, prev_close = _extract_read_model_quote_fallback(symbol)
                if current_price <= 0 and allow_single_quote_retry:
                    current_price, volume, change_percent, prev_close = get_quote_from_broker(
                        symbol, resolved_account_id, user_id=user_id
                    )

            if current_price <= 0:
                results.append(
                    {
                        "symbol": symbol,
                        "name": position.get("name") or position.get("symbol_name") or symbol,
                        "error": "无行情数据",
                        "reason": "当前未能从券商获取到实时行情，请稍后重试或检查代码格式。",
                        "modelPlan": model_plan,
                        "scanLayers": [],
                        "finalSignal": "danger",
                        "finalDecision": "无行情",
                        "source": "manual_scan",
                        "analysisMode": "manual_live_scan",
                    }
                )
                continue

            real_ai_payload, indicator_payload = build_real_indicator_context(
                symbol, current_price, volume, user_id=user_id
            )
            indicator_meta = {"source": "snapshot", "warning": ""}

            market_key = detect_market(symbol)
            market_snapshot = market_snapshot_cache.get(market_key)
            if not market_snapshot:
                market_snapshot = build_market_snapshot(resolved_account_id, symbol, user_id=user_id)
                market_snapshot_cache[market_key] = market_snapshot
            response_market_summary = market_snapshot

            ai_data = {
                **real_ai_payload,
                "price": float(current_price or real_ai_payload.get("price") or 0),
                "market_context": market_snapshot,
                "account_id": resolved_account_id,
                "user_id": user_id,
                "indicator_source": indicator_meta.get("source"),
            }

            rsi = float(real_ai_payload.get("rsi") or 0)
            algo_side = "BUY" if rsi < 30 else "SELL" if rsi > 70 else "HOLD"
            verdict, reason, gemma_analysis, llama_analysis, deepseek_analysis = (
                AiConsultant.get_final_decision_with_details(symbol, algo_side, ai_data)
            )

            final_reason = f"{reason}；{indicator_meta['warning']}" if indicator_meta.get("warning") else reason
            analysis_result = _build_manual_scan_result(
                symbol=symbol,
                position=position,
                current_price=current_price,
                prev_close=prev_close,
                change_percent=change_percent,
                volume=volume,
                indicator_payload=indicator_payload,
                market_snapshot=market_snapshot,
                model_plan=model_plan,
                reason=final_reason,
                gemma_analysis=gemma_analysis,
                llama_analysis=llama_analysis,
                deepseek_analysis=deepseek_analysis,
                verdict=verdict,
            )
            analysis_result["indicatorSource"] = indicator_meta.get("source") or "snapshot"

            try:
                get_persistence_manager().save_ai_analysis(
                    AIAnalysisHistory(
                        user_id=user_id,
                        symbol=symbol,
                        market=detect_market(symbol),
                        price=current_price,
                        gemma_decision=analysis_result.get("gemmaDecision", ""),
                        gemma_confidence=80.0,
                        gemma_analysis=gemma_analysis.get("full_text", ""),
                        llama_decision=analysis_result.get("llamaDecision", ""),
                        llama_confidence=80.0,
                        llama_analysis=llama_analysis.get("full_text", ""),
                        deepseek_decision=analysis_result.get("deepseekDecision", ""),
                        deepseek_confidence=deepseek_analysis.get("confidence", 75.0),
                        deepseek_analysis=deepseek_analysis.get("full_text", ""),
                        final_decision=analysis_result["finalDecision"],
                        final_confidence=deepseek_analysis.get("confidence", 75.0),
                        indicators=analysis_result["indicators"],
                        analysis_time=datetime.now(),
                    )
                )
            except Exception:
                pass

            AICache.cache_analysis(symbol, analysis_result, "combined", 1800)
            results.append(analysis_result)
        except Exception as exc:
            results.append(
                _build_manual_scan_error_result(
                    symbol=symbol,
                    position=position,
                    model_plan=model_plan,
                    error=str(exc),
                    reason=str(exc),
                    current_price=current_price,
                    prev_close=prev_close,
                    change_percent=change_percent,
                    volume=volume,
                    indicator_payload=indicator_payload,
                    market_snapshot=market_snapshot,
                    indicator_source=indicator_meta.get("source") or "",
                )
            )

    response_payload = {
        "success": True,
        "data": results,
        "marketSummary": response_market_summary,
        "modelPlan": model_plan,
        "message": (
            f"本次同步分析 {batch_meta['accepted']} 只股票，成功分析 {len(results)} 只股票"
            + (f"；其余 {batch_meta['deferred']} 只已接受但延后处理" if batch_meta["partial"] else "")
        ),
        "duration": time.time() - started_at,
        "accepted": True,
        "degraded": bool(batch_meta["partial"]),
        "syncLimit": batch_meta["syncLimit"],
        "stats": {
            "total": batch_meta["requested"],
            "accepted": batch_meta["accepted"],
            "successful": len(results),
            "failed": len([item for item in results if item.get("error")]),
            "deferred": batch_meta["deferred"],
        },
        "meta": {
            **batch_meta,
            "status": "accepted" if batch_meta["partial"] else "completed",
        },
    }
    if batch_meta["partial"]:
        return JSONResponse(status_code=202, content=response_payload)
    return response_payload


@router.get("/api/v1/analysis/analyze-positions/jobs/{job_id}")
async def analyze_positions_job_status(
    job_id: str,
    session: dict = Depends(get_current_session),
):
    job = _deferred_analysis_job_snapshot(job_id)
    if not job:
        return JSONResponse(
            status_code=410,
            content={
                "success": False,
                "error": "分析任务已失效或不存在，请重新发起扫描",
                "data": {
                    "jobId": job_id,
                    "status": "expired",
                    "retryable": False,
                },
            },
        )
    if int(job.get("userId") or 0) != int(session["user_id"]):
        raise HTTPException(status_code=404, detail="分析任务不存在")
    return {
        "success": True,
        "data": job,
    }


@router.get("/api/v1/analysis/trend-scans")
async def trend_scans(
    symbols: list[str] = Query(default=[]),
    symbol: str | None = None,
    market: str | None = None,
    limit: int = 24,
    _: dict = Depends(get_current_session),
):
    parsed_symbols = _parse_symbols(symbols, symbol)
    safe_limit = max(1, min(int(limit or 24), 80))
    normalized_market = str(market or "").strip().upper() or None
    items = DailySymbolTrendScanService.get_latest_batch(
        symbols=parsed_symbols or None,
        market=normalized_market,
        limit=safe_limit,
    )
    results = [_build_trend_scan_analysis_result(item) for item in items]
    return {
        "success": True,
        "data": results,
        "meta": _build_trend_scan_meta(
            items=items,
            symbols=parsed_symbols,
            market=normalized_market,
            limit=safe_limit,
        ),
    }


@router.get("/api/v1/analysis/symbols/{symbol}/latest")
async def latest_symbol_analysis(symbol: str, session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
    trend_scan = DailySymbolTrendScanService.get_latest_for_symbol(normalized_symbol)
    latest_ai = get_persistence_manager().get_latest_ai_analysis(normalized_symbol, user_id=user_id)
    return {
        "success": True,
        "data": {
            "symbol": normalized_symbol,
            "latestTrendScan": trend_scan,
            "latestAiAnalysis": latest_ai.to_dict() if latest_ai else None,
        },
    }


@router.get("/api/v1/analysis/recommendations")
async def recommendations(
    profile: str = "growth",
    refresh: bool = False,
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    normalized_profile = str(profile or "growth").strip().lower() or "growth"
    if refresh:
        result = RecommendationService.refresh(profile=normalized_profile, user_id=user_id, force=True)
    else:
        result = RecommendationService.get_latest(profile=normalized_profile, user_id=user_id)
        if not result:
            result = RecommendationService.refresh(profile=normalized_profile, user_id=user_id, force=True)
    return {
        "success": True,
        "data": result,
        "meta": _build_recommendation_meta(result, normalized_profile),
    }


@router.post("/api/v1/analysis/recommendations/refresh")
async def refresh_recommendations(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    profile = str(payload.get("profile", "growth") or "growth").strip().lower() or "growth"
    result = RecommendationService.refresh(
        profile=profile,
        user_id=int(session["user_id"]),
        force=True,
    )
    return {
        "success": True,
        "message": "智能推荐已刷新",
        "data": result,
        "meta": _build_recommendation_meta(result, profile),
    }


@router.post("/api/v1/analysis/agent/watchlist-review")
async def watchlist_review(
    payload: dict = Body(default={}),
    auth_session: dict = Depends(get_current_session),
):
    normalized_session = _normalize_watchlist_session(payload.get("session"))
    scene = _resolve_watchlist_scene(normalized_session)
    raw_user_id = payload.get("userId", payload.get("user_id", auth_session.get("user_id")))
    user_id = _resolve_agent_run_scope_user_id(
        session=auth_session,
        requested_user_id=raw_user_id,
    )

    trigger_source = str(payload.get("triggerSource") or "manual").strip() or "manual"
    dry_run = bool(payload.get("dryRun", True))
    targets = _normalize_watchlist_targets(payload.get("targets"))
    if not targets:
        targets = _load_watchlist_scan_targets(user_id=user_id, session_name=normalized_session)
    run_id = str(uuid.uuid4())
    sidecar_payload = {
        "runId": run_id,
        "scene": scene,
        "session": normalized_session,
        "userId": user_id,
        "user_id": user_id,
        "targets": targets,
        "triggerSource": trigger_source,
        "dryRun": dry_run,
    }
    if isinstance(payload.get("autoBuy"), dict):
        sidecar_payload["autoBuy"] = payload["autoBuy"]

    if not targets:
        return _build_watchlist_review_skipped_result(
            run_id=run_id,
            scene=scene,
            normalized_session=normalized_session,
            trigger_source=trigger_source,
            dry_run=dry_run,
            user_id=user_id,
        )

    idempotency_key = _build_watchlist_idempotency_key(
        scene=scene,
        user_id=user_id,
        trigger_source=trigger_source,
        targets=targets,
    )
    sidecar_payload["idempotencyKey"] = idempotency_key
    existing_run = _find_recent_watchlist_run_by_idempotency_key(
        scene=scene,
        user_id=user_id,
        idempotency_key=idempotency_key,
    )
    if isinstance(existing_run, dict):
        existing_run_id = existing_run.get("runId") or existing_run.get("run_id")
        return _build_watchlist_review_accepted_result(
            run_id=str(existing_run_id or run_id),
            db_run_id=int(existing_run_id) if existing_run_id else None,
            scene=scene,
            normalized_session=normalized_session,
            trigger_source=trigger_source,
            dry_run=dry_run,
            targets_count=len(targets),
            idempotency_key=idempotency_key,
            deduped=True,
        )

    db_run_id = _create_watchlist_run(
        scene=scene,
        user_id=user_id,
        trigger_source=trigger_source,
        targets=targets,
        request_payload=sidecar_payload,
    )

    _start_watchlist_review_worker(
        db_run_id=db_run_id,
        run_id=run_id,
        scene=scene,
        sidecar_payload=sidecar_payload,
    )
    return _build_watchlist_review_accepted_result(
        run_id=run_id,
        db_run_id=db_run_id,
        scene=scene,
        normalized_session=normalized_session,
        trigger_source=trigger_source,
        dry_run=dry_run,
        targets_count=len(targets),
        idempotency_key=idempotency_key,
    )


@router.get("/api/v1/analysis/agent/runs")
async def list_agent_runs(
    scene: str | None = None,
    status: str | None = None,
    limit: int = 20,
    userId: int | None = Query(default=None),
    session: dict = Depends(get_current_session),
):
    scoped_user_id = _resolve_agent_run_scope_user_id(session=session, requested_user_id=userId)
    runs = _call_agent_run_service(
        ("list_recent_runs", "list_runs", "get_runs"),
        scene=str(scene or "").strip() or None,
        status=_normalize_agent_run_status(status),
        user_id=scoped_user_id,
        limit=_normalize_agent_run_limit(limit),
        use_primary=True,
    )
    return {
        "success": True,
        "data": runs if isinstance(runs, list) else [],
        "message": "获取 Agent 运行记录成功",
    }


@router.get("/api/v1/analysis/agent/runs/{run_id}")
async def get_agent_run_detail(
    run_id: int,
    userId: int | None = Query(default=None),
    session: dict = Depends(get_current_session),
):
    scoped_user_id = _resolve_agent_run_scope_user_id(session=session, requested_user_id=userId)
    run = _load_agent_run_or_404(int(run_id))
    _assert_agent_run_visible(run, session=session, scoped_user_id=scoped_user_id)
    return {
        "success": True,
        "data": run,
        "message": "获取 Agent 运行详情成功",
    }


@router.post("/api/v1/analysis/agent/runs/{run_id}/override")
async def override_agent_run(
    run_id: int,
    payload: dict = Body(default={}),
    userId: int | None = Query(default=None),
    session: dict = Depends(get_current_session),
):
    current_user_id = _coerce_agent_run_user_id(session.get("user_id"), field_name="session.user_id")
    scoped_user_id = _resolve_agent_run_scope_user_id(session=session, requested_user_id=userId)
    run = _load_agent_run_or_404(int(run_id))
    _assert_agent_run_visible(run, session=session, scoped_user_id=scoped_user_id)

    action = _normalize_override_action(payload.get("action"))
    new_status = _validate_override_status_transition(
        action,
        _normalize_override_new_status(payload.get("newStatus", payload.get("new_status"))),
    )
    actor = (
        str(payload.get("actor") or session.get("username") or session.get("role") or "human-review").strip()
        or "human-review"
    )

    override_id = _call_agent_run_service(
        ("record_override", "create_override", "save_override"),
        run_id=int(run_id),
        user_id=current_user_id,
        actor=actor,
        action=action,
        reason=payload.get("reason"),
        old_status=run.get("status"),
        new_status=new_status,
        review_note=payload.get("reviewNote", payload.get("review_note")),
    )
    if override_id is None:
        raise HTTPException(status_code=500, detail="人工复核记录写入失败")

    updated_run = _load_agent_run_or_404(int(run_id))
    _assert_agent_run_visible(updated_run, session=session, scoped_user_id=scoped_user_id)
    return {
        "success": True,
        "data": updated_run,
        "message": "人工复核结果已记录",
    }


@router.get("/api/v1/analysis/finance-briefings")
async def finance_briefings(
    limit: int = 20,
    market: str | None = None,
    refresh: bool = False,
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    safe_limit = max(1, min(int(limit or 20), 60))
    normalized_market = str(market or "").strip().upper() or None
    items = FinanceBriefingService.get_latest(limit=safe_limit, market=normalized_market)
    if refresh:
        FinanceBriefingService.refresh_all_markets(user_id=user_id)
        items = FinanceBriefingService.get_latest(limit=safe_limit, market=normalized_market)
    return {
        "success": True,
        "data": items,
        "meta": _build_finance_briefing_meta(
            items=items,
            market=normalized_market,
            limit=safe_limit,
        ),
    }
