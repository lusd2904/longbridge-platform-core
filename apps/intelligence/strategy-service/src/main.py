from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from fastapi import Body, Depends, Query


REFACTOR_ROOT = Path(__file__).resolve().parents[3]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.intelligence.module_shared import (
    QuantTradingService,
    StrategyMonitorService,
    bootstrap_runtime,
    build_dependency_status,
    build_health_payload,
    create_service_app,
    get_current_session,
    service_port,
    summarize_status,
    DbUtil,
)

bootstrap_runtime()


app = create_service_app(
    title="Refactor V2 Strategy Service",
    version="0.2.0",
    description="Phase 1 live service for strategy management, backtests, monitor alerts and quant status.",
)
PORT = service_port("REF_STRATEGY_SERVICE_PORT", 8104)


def _coerce_execute_flag(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


@app.get("/health")
async def health():
    mysql_ok = bool(DbUtil.query_one("SELECT 1"))
    deps = {
        "mysql": build_dependency_status("mysql", "healthy" if mysql_ok else "degraded", detail="策略、回测与监控规则存储"),
    }
    return build_health_payload(
        service="strategy-service",
        version=app.version,
        port=PORT,
        status=summarize_status(deps.values()),
        deps=deps,
        capabilities=["strategy-management", "backtest", "strategy-monitor"],
    )


@app.get("/api/v1/strategy/bootstrap")
async def bootstrap_strategy(
    account_id: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    StrategyMonitorService.ensure_schema(user_id=user_id)
    QuantTradingService.ensure_schema()
    return {
        "success": True,
        "data": {
            "service": "strategy-service",
            "status": "live",
            "monitorSummary": StrategyMonitorService.get_monitor_summary(
                user_id=user_id,
                account_id=account_id,
            ),
            "latestBacktests": StrategyMonitorService.list_backtests(user_id=user_id)[:6],
            "quantStatus": QuantTradingService.get_status(user_id=user_id),
            "legacySources": [
                "refactor-v2/backend-server/src/core/analysis/StrategyMonitorService.py",
                "refactor-v2/backend-server/src/core/analysis/QuantTradingService.py",
                "refactor-v2/backend-server/src/api/data_routes.py",
                "refactor-v2/backend-server/src/api/ai_routes.py",
            ],
        },
    }


@app.get("/api/v1/strategy/runtime")
async def runtime_summary(session: dict = Depends(get_current_session)):
    user_id = int(session["user_id"])
    summary = StrategyMonitorService.get_monitor_summary(user_id=user_id)
    quant_status = QuantTradingService.get_status(user_id=user_id)
    return {
        "success": True,
        "data": {
            "userId": user_id,
            "service": "strategy-service",
            "phase": "phase-1-live",
            "port": PORT,
            "ruleCount": summary.get("overview", {}).get("ruleCount", 0),
            "alertCount": summary.get("overview", {}).get("alertCount", 0),
            "quantEnabled": bool(quant_status.get("enabled")),
            "autoExecute": bool(quant_status.get("autoExecute")),
        },
    }


@app.get("/api/v1/strategy/strategies")
async def list_strategies(session: dict = Depends(get_current_session)):
    return {
        "success": True,
        "data": StrategyMonitorService.list_strategies(user_id=int(session["user_id"])),
    }


@app.get("/api/v1/strategy/templates")
async def list_strategy_templates(session: dict = Depends(get_current_session)):
    return {
        "success": True,
        "data": StrategyMonitorService.get_strategy_templates(),
    }


@app.post("/api/v1/strategy/strategies")
async def create_strategy(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    strategy = StrategyMonitorService.save_strategy(int(session["user_id"]), payload)
    return {"success": True, "data": strategy}


@app.put("/api/v1/strategy/strategies/{strategy_id}")
async def update_strategy(
    strategy_id: int,
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    strategy = StrategyMonitorService.save_strategy(
        int(session["user_id"]),
        payload,
        strategy_id=strategy_id,
    )
    return {"success": True, "data": strategy}


@app.delete("/api/v1/strategy/strategies/{strategy_id}")
async def delete_strategy(strategy_id: int, session: dict = Depends(get_current_session)):
    StrategyMonitorService.delete_strategy(int(session["user_id"]), strategy_id)
    return {"success": True, "message": "策略已删除"}


@app.get("/api/v1/strategy/backtests")
async def list_backtests(session: dict = Depends(get_current_session)):
    return {
        "success": True,
        "data": StrategyMonitorService.list_backtests(user_id=int(session["user_id"])),
    }


@app.post("/api/v1/strategy/backtests")
async def run_backtest(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    result = StrategyMonitorService.run_backtest(int(session["user_id"]), payload)
    return {"success": True, "message": "回测已完成", "data": result}


@app.get("/api/v1/strategy/monitor/summary")
async def monitor_summary(
    account_id: Optional[int] = Query(default=None),
    session: dict = Depends(get_current_session),
):
    return {
        "success": True,
        "data": StrategyMonitorService.get_monitor_summary(
            user_id=int(session["user_id"]),
            account_id=account_id,
        ),
    }


@app.post("/api/v1/strategy/monitor/run")
async def run_monitor(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    account_id = payload.get("account_id")
    strategy_id = payload.get("strategy_id")
    result = StrategyMonitorService.run_monitor(
        user_id=int(session["user_id"]),
        account_id=int(account_id) if account_id else None,
        source="manual",
        strategy_id=int(strategy_id) if strategy_id else None,
    )
    return {"success": True, "data": result}


@app.get("/api/v1/strategy/monitor/alerts")
async def monitor_alerts(
    limit: int = Query(default=20, ge=1, le=100),
    session: dict = Depends(get_current_session),
):
    return {
        "success": True,
        "data": StrategyMonitorService.get_alerts(
            user_id=int(session["user_id"]),
            limit=limit,
        ),
    }


@app.get("/api/v1/strategy/quant/status")
async def quant_status(session: dict = Depends(get_current_session)):
    return {"success": True, "data": QuantTradingService.get_status(user_id=int(session["user_id"]))}


@app.post("/api/v1/strategy/quant/run")
async def run_quant_cycle(
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    account_id = payload.get("account_id")
    execute = payload.get("execute")
    result = QuantTradingService.run_cycle(
        user_id=int(session["user_id"]),
        account_id=int(account_id) if account_id else None,
        source="manual",
        execute=_coerce_execute_flag(execute) if execute is not None else False,
    )
    return {"success": True, "message": "量化分析已完成", "data": result}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
