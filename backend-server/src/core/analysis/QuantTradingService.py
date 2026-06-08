import importlib.util
import json
import os
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest
from zoneinfo import ZoneInfo

from config.Config import AppConfig
from core.analysis.DailySymbolTrendScanService import DailySymbolTrendScanService
from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.analysis.IndicatorSnapshotService import IndicatorSnapshotService
from core.analysis.StrategyMonitorService import StrategyMonitorService
from core.broker.BrokerInterface import get_broker_manager
from core.platform.PlatformAccessService import PlatformAccessService
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil


class QuantTradingService:
    STANDARD_ORDER_STATUS = {
        "NEW": "submitted",
        "NOT_REPORTED": "submitted",
        "SUBMITTED": "submitted",
        "SUBMITTING": "submitted",
        "WAIT_TO_NEW": "submitted",
        "WAIT_TO_DEAL": "accepted",
        "ACCEPTED": "accepted",
        "PENDING": "accepted",
        "PENDING_NEW": "accepted",
        "PARTIAL_FILLED": "partially_filled",
        "PARTIALLY_FILLED": "partially_filled",
        "PARTIALFILLED": "partially_filled",
        "FILLED": "filled",
        "EXECUTED": "filled",
        "CANCELED": "cancelled",
        "CANCELLED": "cancelled",
        "WITHDRAWN": "cancelled",
        "REJECTED": "rejected",
        "DENIED": "rejected",
        "EXPIRED": "expired",
        "FAILED": "failed",
        "DELETED": "cancelled",
    }
    TERMINAL_STANDARD_ORDER_STATUSES = {"filled", "cancelled", "rejected", "expired", "failed"}

    @staticmethod
    def job_name(user_id: int = 1) -> str:
        return f'ai_quant_trading:user:{int(user_id)}'

    @classmethod
    def ensure_schema(cls):
        DbUtil.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS quant_trade_decisions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                cycle_id VARCHAR(48) DEFAULT NULL,
                user_id INT NOT NULL DEFAULT 1,
                account_id INT DEFAULT NULL,
                symbol VARCHAR(32) DEFAULT NULL,
                market VARCHAR(10) DEFAULT NULL,
                side VARCHAR(16) DEFAULT 'HOLD',
                quantity INT DEFAULT 0,
                price DECIMAL(18, 4) DEFAULT 0,
                confidence INT DEFAULT 0,
                status VARCHAR(32) DEFAULT 'queued',
                reason TEXT,
                source VARCHAR(32) DEFAULT 'manual',
                order_id VARCHAR(64) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_quant_user_created (user_id, created_at),
                INDEX idx_quant_cycle (cycle_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        DbUtil.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS watchlist_quant_strategy_runs (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                cycle_id VARCHAR(64) NOT NULL,
                user_id INT NOT NULL DEFAULT 1,
                source VARCHAR(64) DEFAULT 'manual',
                strategy_profile VARCHAR(32) DEFAULT 'balanced',
                enabled TINYINT(1) DEFAULT 0,
                auto_execute TINYINT(1) DEFAULT 0,
                executed TINYINT(1) DEFAULT 0,
                target_count INT DEFAULT 0,
                evaluated_count INT DEFAULT 0,
                opportunity_count INT DEFAULT 0,
                auto_trade_json LONGTEXT,
                position_control_json LONGTEXT,
                skipped_json LONGTEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_watchlist_quant_cycle (user_id, cycle_id),
                INDEX idx_watchlist_quant_user_created (user_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        DbUtil.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS watchlist_quant_strategy_run_items (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                run_id BIGINT DEFAULT NULL,
                cycle_id VARCHAR(64) NOT NULL,
                user_id INT NOT NULL DEFAULT 1,
                symbol VARCHAR(32) NOT NULL,
                name VARCHAR(128) DEFAULT NULL,
                market VARCHAR(10) DEFAULT NULL,
                side VARCHAR(16) DEFAULT 'HOLD',
                status VARCHAR(32) DEFAULT 'observed',
                is_opportunity TINYINT(1) DEFAULT 0,
                price DECIMAL(18, 4) DEFAULT 0,
                confidence INT DEFAULT 0,
                risk_level VARCHAR(16) DEFAULT 'medium',
                reason TEXT,
                tags_json LONGTEXT,
                metrics_json LONGTEXT,
                score_json LONGTEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_watchlist_quant_item_cycle (user_id, cycle_id),
                INDEX idx_watchlist_quant_item_symbol (user_id, symbol, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        DbUtil.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS watchlist_us_open_ai_trade_runs (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                cycle_id VARCHAR(64) NOT NULL,
                user_id INT NOT NULL DEFAULT 1,
                source VARCHAR(64) DEFAULT 'scheduler',
                status VARCHAR(32) DEFAULT 'running',
                reason VARCHAR(128) DEFAULT NULL,
                message TEXT,
                settings_json LONGTEXT,
                target_count INT DEFAULT 0,
                evaluated_count INT DEFAULT 0,
                opportunity_count INT DEFAULT 0,
                submitted_count INT DEFAULT 0,
                skipped_count INT DEFAULT 0,
                executed TINYINT(1) DEFAULT 0,
                auto_trade_json LONGTEXT,
                position_control_json LONGTEXT,
                candidates_json LONGTEXT,
                opportunities_json LONGTEXT,
                skipped_json LONGTEXT,
                error TEXT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                finished_at TIMESTAMP NULL DEFAULT NULL,
                UNIQUE KEY uniq_us_open_ai_trade_cycle (user_id, cycle_id),
                INDEX idx_us_open_ai_trade_user_started (user_id, started_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def get_status(cls, user_id: int = 1) -> Dict[str, Any]:
        cls.ensure_schema()
        access = PlatformAccessService.get_user_capabilities(user_id)
        manager = get_broker_manager()
        accounts = manager.list_accounts(user_id=user_id) or []
        rows = DbUtil.fetch_all(
            """
            SELECT cycle_id, account_id, symbol, market, side, quantity, price,
                   confidence, status, reason, source, order_id, created_at
            FROM quant_trade_decisions
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT 12
            """,
            (user_id,)
        ) or []

        job = DbUtil.fetch_one(
            """
            SELECT last_run_at, status, message
            FROM scheduled_jobs
            WHERE job_name = %s
            """,
            (cls.job_name(user_id),)
        )

        signals = []
        for row in rows:
            signals.append({
                "cycleId": row.get('cycle_id'),
                "accountId": row.get('account_id'),
                "symbol": row.get('symbol'),
                "market": row.get('market'),
                "side": row.get('side'),
                "quantity": int(row.get('quantity') or 0),
                "price": float(row.get('price') or 0),
                "confidence": int(row.get('confidence') or 0),
                "status": row.get('status') or 'queued',
                "reason": row.get('reason') or '',
                "source": row.get('source') or 'manual',
                "orderId": row.get('order_id'),
                "createdAt": row.get('created_at').strftime('%Y-%m-%d %H:%M:%S') if row.get('created_at') else None
            })

        default_account = next(
            (account for account in accounts if account.get('is_default')),
            accounts[0] if accounts else None
        )

        return {
            "hasBoundAccount": bool(access.get("hasBoundAccount")),
            "boundAccountCount": int(access.get("boundAccountCount") or len(accounts)),
            "defaultAccountId": default_account.get('id') if default_account else None,
            "enabled": bool(AppConfig.get('AI_QUANT_TRADING_ENABLED', user_id=user_id, default=False)),
            "autoExecute": bool(AppConfig.get('AI_QUANT_AUTO_EXECUTE', user_id=user_id, default=False)),
            "interval": int(AppConfig.get('AI_QUANT_INTERVAL', user_id=user_id, default=900) or 900),
            "lastRunAt": job.get('last_run_at').strftime('%Y-%m-%d %H:%M:%S') if job and job.get('last_run_at') else None,
            "schedulerStatus": job.get('status') if job else 'idle',
            "schedulerMessage": job.get('message') if job else '',
            "canUseQuantTrading": bool(access.get("canUseQuantTrading")),
            "quantApiEnabled": bool(access.get("quantApiEnabled")),
            "roleCode": access.get("roleCode") or "analyst",
            "signals": signals
        }

    @classmethod
    def run_cycle(
        cls,
        user_id: int = 1,
        account_id: Optional[int] = None,
        source: str = 'manual',
        execute: Optional[bool] = None
    ) -> Dict[str, Any]:
        max_buy_amount = float(AppConfig.get('AI_QUANT_MAX_BUY_AMOUNT', user_id=user_id, default=2000) or 2000)
        confidence_threshold = int(AppConfig.get('AI_QUANT_CONFIDENCE_THRESHOLD', user_id=user_id, default=72) or 72)
        return cls.run_watchlist_strategy_cycle(
            user_id=user_id,
            account_id=account_id,
            source=source,
            execute=execute,
            max_amount=max_buy_amount,
            min_confidence=confidence_threshold,
        )

    @classmethod
    def run_watchlist_strategy_cycle(
        cls,
        *,
        user_id: int = 1,
        account_id: Optional[int] = None,
        source: str = 'manual',
        execute: Optional[bool] = False,
        strategy_profile: str = 'balanced',
        limit: int = 80,
        max_symbols: int = 2,
        max_amount: float = 2000,
        max_position_ratio: float = 0.08,
        min_confidence: int = 72,
    ) -> Dict[str, Any]:
        cls.ensure_schema()
        cycle_id = cls._cycle_id()
        safe_limit = max(1, min(int(limit or 80), 200))
        safe_max_symbols = max(1, min(int(max_symbols or 2), 10))
        safe_max_amount = max(0.0, float(max_amount or 0))
        safe_position_ratio = max(0.0, min(float(max_position_ratio or 0.08), 1.0))
        safe_min_confidence = max(0, min(int(min_confidence or 72), 100))
        safe_profile = str(strategy_profile or 'balanced').strip().lower()
        if safe_profile not in {'balanced', 'momentum', 'breakout', 'reversion'}:
            safe_profile = 'balanced'

        enabled = bool(AppConfig.get('AI_QUANT_TRADING_ENABLED', user_id=user_id, default=False))
        auto_execute = bool(AppConfig.get('AI_QUANT_AUTO_EXECUTE', user_id=user_id, default=False))
        execute_requested = bool(execute if execute is not None else auto_execute)
        should_execute = execute_requested and enabled

        targets = cls._load_watchlist_scan_targets(user_id=user_id, session_filter='all')
        targets = targets[:safe_limit]
        evaluations: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        opportunities: List[Dict[str, Any]] = []

        seen_symbols: set[str] = set()
        for target in targets:
            if isinstance(target, dict):
                raw_symbol = target.get('symbol') or target.get('ticker') or target.get('code')
            else:
                raw_symbol = target
                target = {"symbol": raw_symbol}
            symbol = cls._normalize_watchlist_symbol(raw_symbol, market=(target or {}).get('market'))
            if not symbol or symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)

            evaluation = cls._evaluate_watchlist_quant_target(
                target=dict(target or {}),
                symbol=symbol,
                user_id=user_id,
                strategy_profile=safe_profile,
            )
            if evaluation.get('status') == 'skipped':
                skipped.append(evaluation)
                continue
            evaluations.append(evaluation)
            if bool(evaluation.get('isOpportunity')) and int(evaluation.get('confidence') or 0) >= safe_min_confidence:
                opportunities.append(evaluation)

        opportunities = sorted(
            opportunities,
            key=lambda item: (
                int(item.get('confidence') or 0),
                float(item.get('scoreBreakdown', {}).get('total') or 0),
            ),
            reverse=True,
        )

        auto_trade: Dict[str, Any] = {
            "enabled": execute_requested,
            "executed": False,
            "reason": "not-requested" if not execute_requested else "quant-disabled",
            "signals": [],
        }
        if execute_requested and not enabled:
            auto_trade["message"] = "AI_QUANT_TRADING_ENABLED 未开启，本次仅输出自选池策略候选"
        elif should_execute and not opportunities:
            auto_trade["reason"] = "no-opportunities"
        elif should_execute:
            execution = cls.execute_watchlist_opportunities(
                user_id=user_id,
                opportunities=opportunities,
                account_id=account_id,
                source='watchlist-quant-strategy',
                max_symbols=safe_max_symbols,
                max_amount=safe_max_amount,
                max_position_ratio=safe_position_ratio,
                min_confidence=safe_min_confidence,
                require_paper=True,
            )
            auto_trade = {"enabled": True, **execution}

        result = {
            "cycleId": cycle_id,
            "source": source,
            "strategyProfile": safe_profile,
            "enabled": enabled,
            "autoExecute": auto_execute,
            "executed": bool(auto_trade.get("executed")),
            "targetCount": len(targets),
            "evaluatedCount": len(evaluations),
            "opportunityCount": len(opportunities),
            "candidates": evaluations,
            "opportunities": opportunities,
            "skipped": skipped,
            "autoTrade": auto_trade,
            "positionControl": {
                "maxSymbols": safe_max_symbols,
                "maxAmount": safe_max_amount,
                "maxPositionRatio": safe_position_ratio,
                "minConfidence": safe_min_confidence,
            },
            "strategyReferences": cls._strategy_references(),
            "candidateSchema": cls._opportunity_candidate_schema(),
            "executionBoundary": {
                "owner": "trade-service",
                "mode": "order-intent-to-trade-service",
                "description": "策略服务只生成候选和订单意图，受控执行统一提交到 trade-service，再由 Longbridge 权威下单。",
            },
            "factorSchema": [
                {
                    "key": "trend",
                    "label": "趋势因子",
                    "inputs": [
                        "latestClose", "ma5", "ma10", "ma20", "ma30", "ma60", "ma120",
                        "ema12", "ema26", "return20", "return60", "maSpread20_60",
                        "maSlope20", "adx14", "macdHist",
                    ],
                    "source": "Qlib-style factor pipeline",
                },
                {
                    "key": "priceAction",
                    "label": "价型因子",
                    "inputs": [
                        "kMid", "kLen", "upperShadow", "lowerShadow",
                        "pricePosition20", "pricePosition60", "bollPercentB20",
                    ],
                    "source": "Qlib Alpha158-style candle and rolling position factors",
                },
                {
                    "key": "momentum",
                    "label": "动量因子",
                    "inputs": [
                        "rsi6", "rsi14", "rsi28", "roc12", "stochK14",
                        "williamsR14", "cci20", "momentumScore",
                    ],
                    "source": "TA-Lib/pandas-ta style momentum factors",
                },
                {
                    "key": "breakout",
                    "label": "突破因子",
                    "inputs": ["distanceHigh20", "distanceHigh60", "volumeRatio20", "volumeRatio60", "dayChangePercent", "bollBandwidth20"],
                    "source": "Qlib-style factor pipeline",
                },
                {
                    "key": "volumeFlow",
                    "label": "量能资金因子",
                    "inputs": ["volumeRatio5", "volumeRatio20", "obvSlope20", "mfi14", "cmf20", "closeVolumeCorr20"],
                    "source": "TA-Lib/pandas-ta style volume factors",
                },
                {
                    "key": "reversion",
                    "label": "回归因子",
                    "inputs": ["rsi14", "stochK14", "bollPercentB20", "supportDistance", "distanceLow20", "return20"],
                    "source": "Qlib-style factor pipeline",
                },
                {
                    "key": "volatility",
                    "label": "波动因子",
                    "inputs": ["volatility5", "volatility20", "volatility60", "atr14Percent", "bollBandwidth20", "downsideVol20"],
                    "source": "TA-Lib/pandas-ta style volatility factors",
                },
                {
                    "key": "liquidity",
                    "label": "流动性因子",
                    "inputs": ["avgVolume20", "avgDollarVolume20", "volumeTrend20", "vwapDistance20"],
                    "source": "Qlib-style volume/liquidity factors",
                },
                {
                    "key": "riskPenalty",
                    "label": "风险扣分",
                    "inputs": [
                        "trendScanRisk", "volatility20", "atr14Percent", "rsi14",
                        "distanceHigh20", "maxDrawdown20", "maxDrawdown60", "downsideVol20",
                    ],
                    "source": "vn.py/Lean-style pre-trade gate",
                },
                {
                    "key": "factorSet",
                    "label": "高维 Alpha 因子集",
                    "inputs": ["factorSet", "factorSetVersion", "factorCount", "factorFamilies"],
                    "source": "Qlib Alpha158/Alpha360-style OHLCV lag, rolling, rank and correlation factors",
                },
            ],
        }
        result["history"] = cls._save_watchlist_strategy_run(
            user_id=user_id,
            result=result,
            candidates=evaluations,
            opportunities=opportunities,
            skipped=skipped,
        )
        return result

    @classmethod
    def run_us_open_watchlist_ai_trade(
        cls,
        *,
        user_id: int = 1,
        account_id: Optional[int] = None,
        source: str = 'scheduler',
        force: bool = False,
        now: Optional[datetime] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        cls.ensure_schema()
        policy_settings = cls._load_us_open_ai_trade_settings(settings)
        cycle_id = cls._cycle_id()
        cls._start_us_open_ai_trade_run(
            user_id=user_id,
            cycle_id=cycle_id,
            source=source,
            settings=policy_settings,
        )

        try:
            if not policy_settings["autoTradeEnabled"]:
                result = cls._build_us_open_trade_result(
                    cycle_id=cycle_id,
                    source=source,
                    settings=policy_settings,
                    skipped=True,
                    reason="auto-trade-disabled",
                    message="美股开盘 AI 自动交易开关未开启",
                )
                cls._finish_us_open_ai_trade_run(user_id=user_id, result=result, status="skipped")
                return result

            if policy_settings["regularSessionOnly"] and not force and not cls._is_us_regular_session_now(now):
                result = cls._build_us_open_trade_result(
                    cycle_id=cycle_id,
                    source=source,
                    settings=policy_settings,
                    skipped=True,
                    reason="outside-us-regular-session",
                    message="当前不在美股常规交易时段，已跳过自动交易",
                )
                cls._finish_us_open_ai_trade_run(user_id=user_id, result=result, status="skipped")
                return result

            targets = cls._load_watchlist_scan_targets(user_id=user_id, session_filter='all')
            targets = [
                item for item in targets
                if cls._target_market(item) == policy_settings["market"]
            ][:200]
            evaluations: List[Dict[str, Any]] = []
            skipped: List[Dict[str, Any]] = []
            buy_opportunities: List[Dict[str, Any]] = []
            sell_opportunities: List[Dict[str, Any]] = []

            broker = cls._get_broker(account_id, user_id=user_id)
            if not broker:
                raise ValueError('当前用户未绑定可用交易账户，无法执行美股开盘 AI 自动交易')
            if not broker.is_connected and not broker.connect():
                raise ConnectionError('券商连接失败')

            bound_account_id = int(getattr(broker, 'account_id', account_id or 0) or account_id or 0) or None
            cls._assert_paper_trading_account(account_id=bound_account_id, user_id=user_id)

            positions = broker.get_positions() or []
            holdings = cls._build_holdings_index(positions)

            seen_symbols: set[str] = set()
            for target in targets:
                if isinstance(target, dict):
                    raw_symbol = target.get('symbol') or target.get('ticker') or target.get('code')
                else:
                    raw_symbol = target
                    target = {"symbol": raw_symbol}
                symbol = cls._normalize_watchlist_symbol(raw_symbol, market=(target or {}).get('market') or policy_settings["market"])
                if not symbol or symbol in seen_symbols:
                    continue
                seen_symbols.add(symbol)

                evaluation = cls._evaluate_watchlist_quant_target(
                    target=dict(target or {}),
                    symbol=symbol,
                    user_id=user_id,
                    strategy_profile=policy_settings["strategyProfile"],
                )
                if evaluation.get('status') == 'skipped':
                    skipped.append(evaluation)
                    continue
                holding = holdings.get(symbol)
                trade_side = cls._derive_us_open_trade_side(
                    evaluation=evaluation,
                    is_holding=holding is not None,
                    min_confidence=policy_settings["minConfidence"],
                )
                evaluation["side"] = trade_side
                evaluation["status"] = "sell_candidate" if trade_side == "SELL" else evaluation.get("status")
                evaluation["isOpportunity"] = trade_side in {"BUY", "SELL"}
                evaluation["source"] = "watchlist-us-open-ai-trade"
                evaluations.append(evaluation)
                if trade_side == "SELL":
                    sell_opportunities.append(evaluation)
                elif trade_side == "BUY":
                    buy_opportunities.append(evaluation)

            buy_opportunities = sorted(
                buy_opportunities,
                key=lambda item: (
                    int(item.get('confidence') or 0),
                    float(item.get('scoreBreakdown', {}).get('total') or 0),
                ),
                reverse=True,
            )[:policy_settings["maxSymbols"]]
            sell_opportunities = sorted(
                sell_opportunities,
                key=lambda item: (
                    1 if str(item.get("riskLevel") or "").lower() == "high" else 0,
                    -int(item.get('confidence') or 0),
                ),
                reverse=True,
            )
            opportunities = sell_opportunities + buy_opportunities
            price_refresh = {
                "enabled": bool(policy_settings["refreshRealtimePrice"]),
                "required": bool(policy_settings["requireRealtimePrice"]),
                "requestedCount": len(opportunities),
                "refreshedCount": 0,
                "skippedCount": 0,
                "quoteCount": 0,
            }
            if opportunities and policy_settings["refreshRealtimePrice"]:
                price_refresh = cls._refresh_opportunity_realtime_prices(
                    broker=broker,
                    opportunities=opportunities,
                    require_realtime=policy_settings["requireRealtimePrice"],
                )
                opportunities = price_refresh["opportunities"]
                skipped.extend(price_refresh["skipped"])

            if not opportunities:
                reason = "realtime-price-missing" if price_refresh.get("skippedCount") else "no-opportunities"
                message = (
                    "本轮机会标的缺少券商实时行情，已按配置阻止自动下单"
                    if reason == "realtime-price-missing" else
                    "自选股池本轮没有达到买入或卖出条件的标的"
                )
                result = cls._build_us_open_trade_result(
                    cycle_id=cycle_id,
                    source=source,
                    settings=policy_settings,
                    skipped=False,
                    reason=reason,
                    message=message,
                    targets=targets,
                    evaluations=evaluations,
                    opportunities=[],
                    skipped_items=skipped,
                    auto_trade={
                        "enabled": True,
                        "executed": False,
                        "reason": reason,
                        "signals": [],
                        "priceRefresh": price_refresh,
                    },
                )
                result["history"] = cls._save_watchlist_strategy_run(
                    user_id=user_id,
                    result=result,
                    candidates=evaluations,
                    opportunities=[],
                    skipped=skipped,
                )
                cls._finish_us_open_ai_trade_run(user_id=user_id, result=result, status="completed")
                return result

            execution = cls.execute_watchlist_opportunities(
                user_id=user_id,
                opportunities=opportunities,
                account_id=bound_account_id,
                source='watchlist-us-open-ai-trade',
                max_symbols=policy_settings["maxSymbols"],
                max_amount=0,
                max_position_ratio=1,
                min_confidence=policy_settings["minConfidence"],
                target_portfolio_ratio=policy_settings["targetPortfolioRatio"],
                allow_sells=True,
                require_paper=True,
                broker=broker,
                max_daily_submitted_orders=policy_settings["maxDailySubmittedOrders"],
                max_daily_notional_ratio=policy_settings["maxDailyNotionalRatio"],
            )
            result = cls._build_us_open_trade_result(
                cycle_id=cycle_id,
                source=source,
                settings=policy_settings,
                skipped=False,
                reason=execution.get("reason") or "executed",
                message="美股开盘 AI 自动交易已完成",
                targets=targets,
                evaluations=evaluations,
                opportunities=opportunities,
                skipped_items=skipped,
                auto_trade={"enabled": True, "priceRefresh": price_refresh, **execution},
            )
            result["history"] = cls._save_watchlist_strategy_run(
                user_id=user_id,
                result=result,
                candidates=evaluations,
                opportunities=opportunities,
                skipped=skipped,
            )
            cls._finish_us_open_ai_trade_run(user_id=user_id, result=result, status="completed")
            return result
        except Exception as exc:
            cls._fail_us_open_ai_trade_run(
                user_id=user_id,
                cycle_id=cycle_id,
                source=source,
                settings=policy_settings,
                error=str(exc),
            )
            raise

    @classmethod
    def list_watchlist_strategy_history(cls, user_id: int = 1, limit: int = 20) -> Dict[str, Any]:
        cls.ensure_schema()
        safe_limit = max(1, min(int(limit or 20), 100))
        rows = DbUtil.fetch_all(
            """
            SELECT id, cycle_id, source, strategy_profile, enabled, auto_execute, executed,
                   target_count, evaluated_count, opportunity_count, auto_trade_json,
                   position_control_json, skipped_json, created_at
            FROM watchlist_quant_strategy_runs
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT %s
            """,
            (user_id, safe_limit)
        ) or []

        cycle_ids = [
            str(row.get('cycle_id') or '').strip()
            for row in rows
            if str(row.get('cycle_id') or '').strip()
        ]
        items_by_cycle_id: Dict[str, List[Dict[str, Any]]] = {cycle_id: [] for cycle_id in cycle_ids}
        if cycle_ids:
            placeholders = ", ".join(["%s"] * len(cycle_ids))
            item_rows = DbUtil.fetch_all(
                f"""
                SELECT cycle_id, symbol, name, market, side, status, is_opportunity, price,
                       confidence, risk_level, reason, tags_json, metrics_json,
                       score_json, created_at
                FROM watchlist_quant_strategy_run_items
                WHERE user_id = %s AND cycle_id IN ({placeholders})
                ORDER BY cycle_id ASC, is_opportunity DESC, confidence DESC, id ASC
                """,
                (user_id, *cycle_ids)
            ) or []
            for item in item_rows:
                cycle_id = str(item.get('cycle_id') or '').strip()
                if cycle_id in items_by_cycle_id and len(items_by_cycle_id[cycle_id]) < 20:
                    items_by_cycle_id[cycle_id].append(item)

        runs = []
        for row in rows:
            cycle_id = str(row.get('cycle_id') or '').strip()
            items = items_by_cycle_id.get(cycle_id, [])
            runs.append({
                "id": row.get('id'),
                "cycleId": row.get('cycle_id'),
                "source": row.get('source') or 'manual',
                "strategyProfile": row.get('strategy_profile') or 'balanced',
                "enabled": bool(row.get('enabled')),
                "autoExecute": bool(row.get('auto_execute')),
                "executed": bool(row.get('executed')),
                "targetCount": int(row.get('target_count') or 0),
                "evaluatedCount": int(row.get('evaluated_count') or 0),
                "opportunityCount": int(row.get('opportunity_count') or 0),
                "autoTrade": cls._parse_json(row.get('auto_trade_json'), {}),
                "positionControl": cls._parse_json(row.get('position_control_json'), {}),
                "skipped": cls._parse_json(row.get('skipped_json'), []),
                "items": [cls._format_history_item(item) for item in items],
                "createdAt": cls._format_datetime(row.get('created_at')),
            })

        return {
            "items": runs,
            "total": len(runs),
        }

    @classmethod
    def list_us_open_ai_trade_runs(cls, user_id: int = 1, limit: int = 50) -> Dict[str, Any]:
        cls.ensure_schema()
        safe_limit = max(1, min(int(limit or 50), 200))
        rows = DbUtil.fetch_all(
            """
            SELECT id, cycle_id, source, status, reason, message, settings_json,
                   target_count, evaluated_count, opportunity_count, submitted_count,
                   skipped_count, executed, auto_trade_json, position_control_json,
                   candidates_json, opportunities_json, skipped_json, error,
                   started_at, finished_at
            FROM watchlist_us_open_ai_trade_runs
            WHERE user_id = %s
            ORDER BY started_at DESC, id DESC
            LIMIT %s
            """,
            (user_id, safe_limit)
        ) or []
        items = [cls._format_us_open_ai_trade_run(row) for row in rows]
        return {
            "items": items,
            "total": len(items),
        }

    @classmethod
    def run_watchlist_strategy_backtest(
        cls,
        *,
        user_id: int = 1,
        symbol: str,
        market: Optional[str] = None,
        strategy_profile: str = 'balanced',
        lookback_days: int = 90,
        min_confidence: int = 72,
    ) -> Dict[str, Any]:
        safe_symbol = cls._normalize_watchlist_symbol(symbol, market=market)
        if not safe_symbol:
            raise ValueError('缺少有效标的')
        safe_profile = str(strategy_profile or 'balanced').strip().lower()
        if safe_profile not in {'balanced', 'momentum', 'breakout', 'reversion'}:
            safe_profile = 'balanced'
        safe_lookback = max(20, min(int(lookback_days or 90), 260))
        safe_min_confidence = max(0, min(int(min_confidence or 72), 100))

        series = HistoricalMarketDataService.get_daily_series_until(
            safe_symbol,
            end_date=date.today(),
            limit=safe_lookback + 260,
        )
        if len(series) < 60:
            return {
                "symbol": safe_symbol,
                "strategyProfile": safe_profile,
                "lookbackDays": safe_lookback,
                "minConfidence": safe_min_confidence,
                "status": "skipped",
                "reason": "历史行情少于 60 条，无法进行策略复盘",
                "points": [],
                "summary": {"signalCount": 0, "hitRate": 0, "avgScore": 0},
            }

        start_index = max(59, len(series) - safe_lookback)
        points = []
        signal_returns: List[float] = []
        scores: List[int] = []
        for index in range(start_index, len(series)):
            sample = series[max(0, index - 259):index + 1]
            metrics = cls._build_watchlist_quant_metrics(series=sample, snapshot={}, trend_scan=None)
            score = cls._score_watchlist_quant_metrics(metrics=metrics, strategy_profile=safe_profile)
            confidence = int(round(score["total"]))
            scores.append(confidence)
            is_signal = confidence >= safe_min_confidence and score.get("riskLevel") != 'high'
            forward_5d_return = 0.0
            if index + 5 < len(series):
                base = cls._safe_float(series[index].get('close'))
                forward = cls._safe_float(series[index + 5].get('close'))
                forward_5d_return = round(((forward - base) / base) * 100, 2) if base else 0.0
            if is_signal:
                signal_returns.append(forward_5d_return)
            points.append({
                "tradeDate": metrics.get("tradeDate") or series[index].get('date'),
                "price": metrics.get("latestClose"),
                "confidence": confidence,
                "signal": "BUY" if is_signal else "HOLD",
                "riskLevel": score.get("riskLevel"),
                "trendDirection": score.get("trendDirection"),
                "forward5dReturn": forward_5d_return,
                "tags": score.get("tags") or [],
                "scoreBreakdown": score,
                "metrics": metrics,
            })

        signal_count = len(signal_returns)
        hit_count = len([item for item in signal_returns if item > 0])
        latest = points[-1] if points else {}
        return {
            "symbol": safe_symbol,
            "market": HistoricalMarketDataService.detect_market(safe_symbol),
            "strategyProfile": safe_profile,
            "lookbackDays": safe_lookback,
            "minConfidence": safe_min_confidence,
            "status": "completed",
            "mode": "historical-price-replay",
            "points": points,
            "summary": {
                "pointCount": len(points),
                "signalCount": signal_count,
                "hitRate": round((hit_count / signal_count) * 100, 2) if signal_count else 0,
                "avgForward5dReturn": round(sum(signal_returns) / signal_count, 2) if signal_count else 0,
                "avgScore": round(sum(scores) / len(scores), 2) if scores else 0,
                "latestSignal": latest.get("signal") or "HOLD",
                "latestConfidence": latest.get("confidence") or 0,
                "latestTradeDate": latest.get("tradeDate"),
            },
        }

    @classmethod
    def execute_watchlist_opportunities(
        cls,
        *,
        user_id: int = 1,
        opportunities: Optional[List[Dict[str, Any]]] = None,
        account_id: Optional[int] = None,
        source: str = 'watchlist-review',
        max_symbols: int = 2,
        max_amount: float = 2000,
        max_position_ratio: float = 0.08,
        min_confidence: int = 72,
        target_portfolio_ratio: Optional[float] = None,
        allow_sells: bool = False,
        require_paper: bool = False,
        broker: Any = None,
        max_daily_submitted_orders: Optional[int] = None,
        max_daily_notional_ratio: Optional[float] = None,
    ) -> Dict[str, Any]:
        cls.ensure_schema()
        access = PlatformAccessService.get_user_capabilities(user_id)
        if not access.get("hasBoundAccount"):
            raise ValueError('当前用户未绑定可用交易账户，无法执行自选机会股自动交易')
        if not access.get("quantApiEnabled"):
            raise ValueError('当前用户未开通量化交易 API，请先在用户管理中开启后再使用')
        if not access.get("canUseQuantTrading"):
            raise ValueError('当前用户角色暂未授权量化交易能力')

        safe_opportunities = opportunities if isinstance(opportunities, list) else []
        max_symbols_cap = 20 if target_portfolio_ratio is not None else 10
        safe_max_symbols = max(1, min(int(max_symbols or 2), max_symbols_cap))
        safe_max_amount = max(0.0, float(max_amount or 0))
        safe_position_ratio = max(0.0, min(cls._safe_float(max_position_ratio, 0.08), 1.0))
        safe_min_confidence = max(0, min(int(min_confidence or 72), 100))
        safe_target_ratio = (
            max(0.0, min(cls._safe_float(target_portfolio_ratio, 0.70), 1.0))
            if target_portfolio_ratio is not None else None
        )
        safe_daily_order_limit = (
            max(0, int(cls._safe_float(max_daily_submitted_orders, 0)))
            if max_daily_submitted_orders is not None else 0
        )
        safe_daily_notional_ratio = (
            max(0.0, min(cls._safe_float(max_daily_notional_ratio, 0.0), 1.0))
            if max_daily_notional_ratio is not None else 0.0
        )
        allowed_symbols = cls._load_watchlist_symbols(user_id=user_id)

        broker = broker or cls._get_broker(account_id, user_id=user_id)
        if not broker:
            raise ValueError('当前用户未绑定可用交易账户，无法执行自选机会股自动交易')
        if not broker.is_connected and not broker.connect():
            raise ConnectionError('券商连接失败')

        bound_account_id = int(getattr(broker, 'account_id', account_id or 0) or account_id or 0) or None
        if require_paper:
            cls._assert_paper_trading_account(account_id=bound_account_id, user_id=user_id)
        account_info = broker.get_account_info()
        positions = broker.get_positions() or []
        holdings = cls._build_holdings_index(positions)
        available_cash = cls._read_number(account_info, 'cash')
        if available_cash <= 0:
            available_cash = cls._read_number(account_info, 'buying_power')
        total_equity = float(
            cls._read_number(account_info, 'total_equity')
            or (available_cash + sum(cls._read_number(position, 'market_value') for position in positions))
            or 0
        )
        current_market_value = (
            cls._read_number(account_info, 'market_value')
            or sum(cls._read_number(position, 'market_value') for position in positions)
        )
        per_symbol_cap = total_equity * safe_position_ratio if total_equity > 0 and safe_position_ratio > 0 else safe_max_amount
        portfolio_budget = total_equity * safe_target_ratio if safe_target_ratio is not None and total_equity > 0 else None
        remaining_portfolio_buy_budget = (
            min(available_cash, max(0.0, float(portfolio_budget or 0) - current_market_value))
            if portfolio_budget is not None else None
        )
        daily_guardrail = cls._load_auto_trade_daily_guardrail(
            user_id=user_id,
            account_id=bound_account_id,
            source=source,
            total_equity=total_equity,
            max_submitted_orders=safe_daily_order_limit,
            max_notional_ratio=safe_daily_notional_ratio,
        )

        cycle_id = cls._cycle_id()
        decisions: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []
        seen_symbols: set[str] = set()
        buy_decision_count = 0
        for item in safe_opportunities:
            raw_symbol = str(item.get('symbol') or '').strip().upper()
            if not raw_symbol:
                continue
            normalized_symbol = cls._normalize_watchlist_symbol(raw_symbol, market=item.get('market'))
            if normalized_symbol in seen_symbols:
                skipped.append({"symbol": normalized_symbol, "reason": "重复机会标的已合并"})
                continue
            seen_symbols.add(normalized_symbol)
            if normalized_symbol not in allowed_symbols:
                skipped.append({"symbol": normalized_symbol or raw_symbol, "reason": "不在当前用户自选股池，禁止自动下单"})
                continue
            symbol = normalized_symbol
            requested_side = str(item.get('side') or 'BUY').strip().upper()
            side = 'SELL' if requested_side == 'SELL' and allow_sells else 'BUY'
            if side == 'BUY' and buy_decision_count >= safe_max_symbols:
                skipped.append({"symbol": symbol, "reason": f"已达到本轮最多买入标的数 {safe_max_symbols}"})
                continue
            confidence = int(float(item.get('confidence') or 0))
            price = float(
                item.get('price')
                or item.get('lastPrice')
                or item.get('latestClose')
                or item.get('closePrice')
                or 0
            )
            holding = holdings.get(symbol)
            if price <= 0 and holding is not None:
                price = cls._read_number(holding, 'market_price') or cls._read_number(holding, 'average_cost')

            if side == 'SELL':
                if holding is None:
                    skipped.append({"symbol": symbol, "reason": "无持仓可卖出"})
                    continue
                quantity = cls._position_quantity(holding)
                if quantity <= 0:
                    skipped.append({"symbol": symbol, "reason": "无可用持仓数量"})
                    continue
                if price <= 0:
                    skipped.append({"symbol": symbol, "reason": "缺少有效卖出价格"})
                    continue
                budget_meta = {
                    "holdingQuantity": quantity,
                    "price": round(price, 4),
                    "quantity": quantity,
                    "budgetRule": "sell full available holding",
                }
                decisions.append({
                    "symbol": symbol,
                    "market": item.get('market') or StrategyMonitorService.detect_market(symbol),
                    "side": "SELL",
                    "quantity": quantity,
                    "price": price,
                    "confidence": confidence,
                    "reason": str(item.get('reason') or item.get('summary') or '自选池 AI 扫描触发卖出')[:500],
                    "budget": budget_meta,
                    "scoreBreakdown": item.get("scoreBreakdown") if isinstance(item.get("scoreBreakdown"), dict) else {},
                    "factorInputs": item.get("metrics") if isinstance(item.get("metrics"), dict) else {},
                    "priceSource": item.get("priceSource"),
                    "quoteUpdatedAt": item.get("quoteUpdatedAt"),
                    "source": source,
                    "status": "queued"
                })
                continue

            if holding is not None:
                skipped.append({"symbol": symbol, "reason": "已有持仓"})
                continue
            if confidence < safe_min_confidence:
                skipped.append({"symbol": symbol, "reason": f"置信度低于 {safe_min_confidence}"})
                continue
            if price <= 0:
                skipped.append({"symbol": symbol, "reason": "缺少有效价格"})
                continue

            if remaining_portfolio_buy_budget is not None:
                remaining_slots = max(1, safe_max_symbols - buy_decision_count)
                slot_budget = remaining_portfolio_buy_budget / remaining_slots if remaining_portfolio_buy_budget > 0 else 0.0
                one_share_budget = price if remaining_portfolio_buy_budget >= price and available_cash >= price else slot_budget
                budget = min(available_cash, per_symbol_cap, max(slot_budget, one_share_budget))
                budget_rule = "min(availableCash, perSymbolCap, remainingPortfolioBudget / remainingSlots; US min 1 share)"
            else:
                budget = min(safe_max_amount, available_cash, per_symbol_cap)
                budget_rule = "min(maxAmount, availableCash, totalEquity * maxPositionRatio)"
            quantity = int(budget / price) if budget > 0 else 0
            if quantity <= 0:
                skipped.append({"symbol": symbol, "reason": "仓位预算不足"})
                continue

            budget_meta = {
                "maxAmount": round(safe_max_amount, 4),
                "availableCashBefore": round(available_cash, 4),
                "perSymbolCap": round(per_symbol_cap, 4),
                "portfolioBudget": round(portfolio_budget, 4) if portfolio_budget is not None else None,
                "remainingPortfolioBuyBudgetBefore": round(remaining_portfolio_buy_budget, 4) if remaining_portfolio_buy_budget is not None else None,
                "budget": round(budget, 4),
                "price": round(price, 4),
                "quantity": quantity,
                "budgetRule": budget_rule,
            }
            decisions.append({
                "symbol": symbol,
                "market": item.get('market') or StrategyMonitorService.detect_market(symbol),
                "side": "BUY",
                "quantity": quantity,
                "price": price,
                "confidence": confidence,
                "reason": str(item.get('reason') or item.get('summary') or '自选复核识别为机会股')[:500],
                "budget": budget_meta,
                "scoreBreakdown": item.get("scoreBreakdown") if isinstance(item.get("scoreBreakdown"), dict) else {},
                "factorInputs": item.get("metrics") if isinstance(item.get("metrics"), dict) else {},
                "priceSource": item.get("priceSource"),
                "quoteUpdatedAt": item.get("quoteUpdatedAt"),
                "source": source,
                "status": "queued"
            })
            spent = quantity * price
            available_cash -= spent
            if remaining_portfolio_buy_budget is not None:
                remaining_portfolio_buy_budget = max(0.0, remaining_portfolio_buy_budget - spent)
            buy_decision_count += 1
            if buy_decision_count >= safe_max_symbols:
                continue

        persisted = []
        today_orders, today_orders_error = cls._load_broker_today_orders(
            account_id=bound_account_id,
            user_id=user_id,
        )
        for decision in decisions:
            decision_notional = float(decision.get("quantity") or 0) * float(decision.get("price") or 0)
            guardrail_reason = cls._daily_guardrail_skip_reason(daily_guardrail, decision_notional, decision.get("side"))
            if guardrail_reason:
                skipped.append({"symbol": decision['symbol'], "reason": guardrail_reason})
                continue
            if cls._has_recent_duplicate(user_id, decision['symbol'], decision['side']):
                skipped.append({"symbol": decision['symbol'], "reason": "60 分钟内已有同向决策"})
                continue
            if today_orders_error:
                skipped.append({
                    "symbol": decision['symbol'],
                    "reason": f"券商当日委托核验失败，已阻止自动下单: {today_orders_error}",
                })
                continue
            active_order = cls._find_active_broker_order(today_orders, decision['symbol'], decision['side'])
            if active_order:
                skipped.append({
                    "symbol": decision['symbol'],
                    "reason": f"券商当日已有未完成同向委托 {active_order.get('orderId') or ''} ({active_order.get('status') or 'active'})",
                    "orderId": active_order.get('orderId'),
                    "status": active_order.get('status'),
                })
                continue
            execution = cls._execute_decision(bound_account_id, decision, user_id=user_id)
            persisted.append(cls._save_decision(
                cycle_id=cycle_id,
                user_id=user_id,
                account_id=bound_account_id,
                decision=decision,
                status=execution.get('status', 'failed'),
                source=source,
                order_id=execution.get('order_id')
            ))
            standard_status = cls._standard_order_status(execution.get('standardStatus') or execution.get('status', 'failed'))
            if standard_status in {"submitted", "accepted", "partially_filled", "filled"}:
                daily_guardrail["submittedCount"] = int(daily_guardrail.get("submittedCount") or 0) + 1
                if str(decision.get("side") or "").strip().upper() == "BUY":
                    daily_guardrail["submittedNotional"] = float(daily_guardrail.get("submittedNotional") or 0.0) + decision_notional

        return {
            "cycleId": cycle_id,
            "executed": True,
            "accountId": bound_account_id,
            "executionBoundary": "trade-service",
            "opportunityCount": len(safe_opportunities),
            "submittedCount": len(persisted),
            "skipped": skipped,
            "signals": persisted,
            "positionControl": {
                "maxSymbols": safe_max_symbols,
                "maxAmount": safe_max_amount,
                "maxPositionRatio": safe_position_ratio,
                "minConfidence": safe_min_confidence,
                "perSymbolCap": per_symbol_cap,
                "targetPortfolioRatio": safe_target_ratio,
                "portfolioBudget": portfolio_budget,
                "currentMarketValue": current_market_value,
                "dailySubmittedCount": daily_guardrail.get("submittedCount"),
                "dailySubmittedNotional": daily_guardrail.get("submittedNotional"),
                "maxDailySubmittedOrders": daily_guardrail.get("maxSubmittedOrders"),
                "maxDailyNotional": daily_guardrail.get("maxNotional"),
                "maxDailyNotionalRatio": daily_guardrail.get("maxNotionalRatio"),
                "budgetRule": (
                    "min(availableCash, perSymbolCap, remainingPortfolioBudget / remainingSlots; US min 1 share)"
                    if safe_target_ratio is not None else
                    "min(maxAmount, availableCash, totalEquity * maxPositionRatio)"
                ),
            }
        }

    @classmethod
    def _evaluate_watchlist_quant_target(
        cls,
        *,
        target: Dict[str, Any],
        symbol: str,
        user_id: int,
        strategy_profile: str,
    ) -> Dict[str, Any]:
        market = str(target.get('market') or HistoricalMarketDataService.detect_market(symbol)).upper()
        name = str(target.get('name') or target.get('displayName') or symbol)
        try:
            series = HistoricalMarketDataService.get_daily_series_until(symbol, limit=260)
        except Exception as exc:
            return {
                "symbol": symbol,
                "name": name,
                "market": market,
                "status": "skipped",
                "reason": f"历史行情读取失败: {str(exc)[:120]}",
            }

        if len(series) < 60:
            return {
                "symbol": symbol,
                "name": name,
                "market": market,
                "status": "skipped",
                "reason": "历史行情少于 60 条，暂不参与自选池量化评分",
                "historyCount": len(series),
            }

        snapshot = cls._safe_get_indicator_snapshot(symbol, user_id=user_id)
        trend_scan = cls._safe_get_trend_scan(symbol)
        metrics = cls._build_watchlist_quant_metrics(series=series, snapshot=snapshot, trend_scan=trend_scan)
        score = cls._score_watchlist_quant_metrics(metrics=metrics, strategy_profile=strategy_profile)
        risk_level = score["riskLevel"]
        confidence = int(round(score["total"]))
        is_opportunity = confidence >= 60 and risk_level != 'high' and metrics["latestClose"] > 0

        tags = score["tags"]
        if trend_scan and trend_scan.get("trendDirection") == "up":
            tags.append("AI趋势偏多")
        tags = list(dict.fromkeys(tags))
        reason_parts = [
            f"多因子 {confidence} 分",
            f"20日收益 {metrics['return20']:+.2f}%",
            f"RSI {metrics['rsi14']:.1f}",
        ]
        if metrics["volumeRatio20"] > 0:
            reason_parts.append(f"量比 {metrics['volumeRatio20']:.2f}")
        if risk_level == 'high':
            reason_parts.append("高风险过滤")

        return {
            "symbol": symbol,
            "name": name,
            "market": market,
            "side": "BUY" if is_opportunity else "HOLD",
            "status": "candidate" if is_opportunity else "observed",
            "isOpportunity": is_opportunity,
            "price": metrics["latestClose"],
            "priceSource": "historical-close",
            "latestClose": metrics["latestClose"],
            "confidence": confidence,
            "reason": "，".join(reason_parts),
            "summary": trend_scan.get("summary") if isinstance(trend_scan, dict) else "",
            "strategyTags": tags,
            "riskLevel": risk_level,
            "trendDirection": (trend_scan or {}).get("trendDirection") or score["trendDirection"],
            "scoreBreakdown": score,
            "metrics": metrics,
            "source": "watchlist-quant-strategy",
            }

    @classmethod
    def _load_us_open_ai_trade_settings(cls, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        policy = SystemTaskService.get_policy("watchlist_us_open_ai_trade") or {}
        policy_settings = policy.get("settings") if isinstance(policy.get("settings"), dict) else {}
        raw_settings = {**policy_settings, **(overrides or {})}
        profile = str(raw_settings.get("strategyProfile") or "balanced").strip().lower()
        if profile not in {"balanced", "momentum", "breakout", "reversion"}:
            profile = "balanced"
        return {
            "autoTradeEnabled": cls._coerce_bool(raw_settings.get("autoTradeEnabled"), True),
            "maxSymbols": max(1, min(int(cls._safe_float(raw_settings.get("maxSymbols"), 5)), 20)),
            "targetPortfolioRatio": max(0.0, min(cls._safe_float(raw_settings.get("targetPortfolioRatio"), 0.70), 1.0)),
            "minConfidence": max(0, min(int(cls._safe_float(raw_settings.get("minConfidence"), 72)), 100)),
            "strategyProfile": profile,
            "market": str(raw_settings.get("market") or "US").strip().upper() or "US",
            "regularSessionOnly": cls._coerce_bool(raw_settings.get("regularSessionOnly"), True),
            "refreshRealtimePrice": cls._coerce_bool(raw_settings.get("refreshRealtimePrice"), True),
            "requireRealtimePrice": cls._coerce_bool(raw_settings.get("requireRealtimePrice"), True),
            "maxDailySubmittedOrders": max(0, min(int(cls._safe_float(raw_settings.get("maxDailySubmittedOrders"), 10)), 200)),
            "maxDailyNotionalRatio": max(0.0, min(cls._safe_float(raw_settings.get("maxDailyNotionalRatio"), 0.70), 1.0)),
        }

    @classmethod
    def _build_us_open_trade_result(
        cls,
        *,
        cycle_id: str,
        source: str,
        settings: Dict[str, Any],
        skipped: bool,
        reason: str,
        message: str,
        targets: Optional[List[Dict[str, Any]]] = None,
        evaluations: Optional[List[Dict[str, Any]]] = None,
        opportunities: Optional[List[Dict[str, Any]]] = None,
        skipped_items: Optional[List[Dict[str, Any]]] = None,
        auto_trade: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        candidates = evaluations or []
        trade_payload = auto_trade or {
            "enabled": bool(settings.get("autoTradeEnabled")),
            "executed": False,
            "reason": reason,
            "signals": [],
        }
        return {
            "cycleId": cycle_id,
            "source": source,
            "strategyProfile": settings.get("strategyProfile") or "balanced",
            "enabled": bool(settings.get("autoTradeEnabled")),
            "autoExecute": bool(settings.get("autoTradeEnabled")),
            "executed": bool(trade_payload.get("executed") and trade_payload.get("submittedCount", 0) > 0),
            "skipped": skipped_items or [],
            "skippedRun": bool(skipped),
            "reason": reason,
            "message": message,
            "targetCount": len(targets or []),
            "evaluatedCount": len(candidates),
            "opportunityCount": len(opportunities or []),
            "candidates": candidates,
            "opportunities": opportunities or [],
            "autoTrade": trade_payload,
            "positionControl": {
                "maxSymbols": int(settings.get("maxSymbols") or 5),
                "targetPortfolioRatio": float(settings.get("targetPortfolioRatio") or 0),
                "minConfidence": int(settings.get("minConfidence") or 72),
                "market": settings.get("market") or "US",
                "regularSessionOnly": bool(settings.get("regularSessionOnly")),
                "refreshRealtimePrice": bool(settings.get("refreshRealtimePrice")),
                "requireRealtimePrice": bool(settings.get("requireRealtimePrice")),
                "maxDailySubmittedOrders": int(settings.get("maxDailySubmittedOrders") or 0),
                "maxDailyNotionalRatio": float(settings.get("maxDailyNotionalRatio") or 0),
                "budgetRule": "target portfolio exposure with even remaining-slot allocation; US minimum 1 share",
            },
            "executionBoundary": {
                "owner": "trade-service",
                "mode": "paper-account-only-order-intent",
                "description": "美股开盘自动交易只生成受控订单意图，必须经 trade-service 纸账户边界后提交。",
            },
        }

    @classmethod
    def _refresh_opportunity_realtime_prices(
        cls,
        *,
        broker: Any,
        opportunities: List[Dict[str, Any]],
        require_realtime: bool = True,
    ) -> Dict[str, Any]:
        symbols = list(dict.fromkeys([
            str(item.get("symbol") or "").strip().upper()
            for item in opportunities or []
            if str(item.get("symbol") or "").strip()
        ]))
        skipped: List[Dict[str, Any]] = []
        if not symbols or not hasattr(broker, "get_quote"):
            if require_realtime:
                skipped = [
                    {"symbol": str(item.get("symbol") or ""), "reason": "券商实时行情接口不可用，已阻止自动下单"}
                    for item in opportunities or []
                ]
                return {
                    "enabled": True,
                    "required": True,
                    "requestedCount": len(opportunities or []),
                    "refreshedCount": 0,
                    "skippedCount": len(skipped),
                    "quoteCount": 0,
                    "opportunities": [],
                    "skipped": skipped,
                    "error": "broker-quote-unavailable",
                }
            return {
                "enabled": True,
                "required": False,
                "requestedCount": len(opportunities or []),
                "refreshedCount": 0,
                "skippedCount": 0,
                "quoteCount": 0,
                "opportunities": opportunities or [],
                "skipped": [],
            }

        quotes: Dict[str, Any] = {}
        quote_error = ""
        try:
            raw_quotes = broker.get_quote(symbols) or {}
            if isinstance(raw_quotes, dict):
                quotes = {
                    HistoricalMarketDataService.normalize_symbol(key): value
                    for key, value in raw_quotes.items()
                    if key
                }
        except Exception as exc:
            quote_error = str(exc)[:160]

        refreshed: List[Dict[str, Any]] = []
        refreshed_count = 0
        for item in opportunities or []:
            symbol = HistoricalMarketDataService.normalize_symbol(str(item.get("symbol") or ""))
            quote = quotes.get(symbol)
            price = cls._quote_price(quote)
            if price <= 0 and require_realtime:
                skipped.append({"symbol": symbol, "reason": "缺少券商实时行情，已阻止自动下单"})
                continue

            next_item = dict(item)
            if price > 0:
                next_item["price"] = price
                next_item["lastPrice"] = price
                next_item["priceSource"] = "broker-realtime"
                next_item["quoteUpdatedAt"] = cls._format_datetime(cls._quote_timestamp(quote))
                refreshed_count += 1
            else:
                next_item["priceSource"] = next_item.get("priceSource") or "history-fallback"
            refreshed.append(next_item)

        return {
            "enabled": True,
            "required": bool(require_realtime),
            "requestedCount": len(opportunities or []),
            "refreshedCount": refreshed_count,
            "skippedCount": len(skipped),
            "quoteCount": len(quotes),
            "opportunities": refreshed,
            "skipped": skipped,
            "error": quote_error,
        }

    @classmethod
    def _quote_price(cls, quote: Any) -> float:
        for name in ("last_price", "lastPrice", "last", "last_done", "lastDone", "price", "current_price", "currentPrice", "latest_price", "latestPrice"):
            value = cls._read_order_attr(quote, name, None)
            number = cls._safe_float(value, 0.0)
            if number > 0:
                return number
        return 0.0

    @classmethod
    def _quote_timestamp(cls, quote: Any) -> Any:
        for name in ("timestamp", "time", "updated_at", "updatedAt"):
            value = cls._read_order_attr(quote, name, None)
            if value:
                return value
        return None

    @classmethod
    def _load_auto_trade_daily_guardrail(
        cls,
        *,
        user_id: int,
        account_id: Optional[int],
        source: str,
        total_equity: float,
        max_submitted_orders: int,
        max_notional_ratio: float,
    ) -> Dict[str, Any]:
        row = DbUtil.fetch_one_primary(
            """
            SELECT
                COUNT(1) AS submitted_count,
                COALESCE(SUM(CASE WHEN side = 'BUY' THEN quantity * price ELSE 0 END), 0) AS submitted_notional
            FROM quant_trade_decisions
            WHERE user_id = %s
              AND (%s IS NULL OR account_id = %s)
              AND source = %s
              AND created_at >= CURDATE()
              AND side IN ('BUY', 'SELL')
              AND status NOT IN ('failed', 'rejected', 'cancelled', 'canceled', 'expired')
            """,
            (user_id, account_id, account_id, source),
        ) or {}
        max_notional = float(total_equity or 0) * max_notional_ratio if max_notional_ratio > 0 and total_equity > 0 else 0.0
        return {
            "submittedCount": int(cls._safe_float(row.get("submitted_count"), 0)),
            "submittedNotional": cls._safe_float(row.get("submitted_notional"), 0.0),
            "maxSubmittedOrders": max(0, int(max_submitted_orders or 0)),
            "maxNotional": max_notional,
            "maxNotionalRatio": max_notional_ratio,
        }

    @staticmethod
    def _daily_guardrail_skip_reason(guardrail: Dict[str, Any], decision_notional: float, side: Any = None) -> str:
        max_orders = int(guardrail.get("maxSubmittedOrders") or 0)
        if max_orders > 0 and int(guardrail.get("submittedCount") or 0) >= max_orders:
            return f"已达到今日自动交易最多提交 {max_orders} 单"
        max_notional = float(guardrail.get("maxNotional") or 0.0)
        if max_notional > 0 and str(side or "").strip().upper() == "BUY":
            submitted = float(guardrail.get("submittedNotional") or 0.0)
            if submitted + max(0.0, decision_notional) > max_notional:
                return f"超过今日自动交易名义金额上限 {round(max_notional, 2)} USD"
        return ""

    @staticmethod
    def _target_market(target: Any) -> str:
        if isinstance(target, dict):
            raw_symbol = target.get("symbol") or target.get("ticker") or target.get("code")
            market = target.get("market") or target.get("region")
        else:
            raw_symbol = target
            market = None
        if market:
            return str(market).strip().upper()
        return HistoricalMarketDataService.detect_market(str(raw_symbol or ""))

    @staticmethod
    def _is_us_regular_session_now(now: Optional[datetime] = None) -> bool:
        ny_tz = ZoneInfo("America/New_York")
        current = now or datetime.now(tz=ny_tz)
        if current.tzinfo is None:
            current = current.replace(tzinfo=ny_tz)
        current = current.astimezone(ny_tz)
        if current.weekday() >= 5:
            return False
        return time(9, 30) <= current.time() <= time(16, 0)

    @classmethod
    def _derive_us_open_trade_side(
        cls,
        *,
        evaluation: Dict[str, Any],
        is_holding: bool,
        min_confidence: int,
    ) -> str:
        confidence = int(evaluation.get("confidence") or 0)
        risk_level = str(evaluation.get("riskLevel") or "").lower()
        trend_direction = str(evaluation.get("trendDirection") or "").lower()
        score = evaluation.get("scoreBreakdown") if isinstance(evaluation.get("scoreBreakdown"), dict) else {}
        score_direction = str(score.get("trendDirection") or "").lower()
        metrics = evaluation.get("metrics") if isinstance(evaluation.get("metrics"), dict) else {}
        trend_scan_direction = str(metrics.get("trendScanDirection") or "").lower()
        return20 = cls._safe_float(metrics.get("return20"))

        if is_holding:
            if risk_level == "high":
                return "SELL"
            if trend_direction == "down" or score_direction == "down" or trend_scan_direction == "down":
                return "SELL"
            if confidence < max(45, min_confidence - 20) and return20 <= -5:
                return "SELL"
            return "HOLD"
        if bool(evaluation.get("isOpportunity")) and confidence >= min_confidence and risk_level != "high":
            return "BUY"
        return "HOLD"

    @classmethod
    def _build_holdings_index(cls, positions: List[Any]) -> Dict[str, Any]:
        holdings: Dict[str, Any] = {}
        for position in positions or []:
            raw_symbol = str(cls._read_order_attr(position, 'symbol', '') or '').upper()
            if not raw_symbol:
                continue
            holdings[raw_symbol] = position
            holdings[HistoricalMarketDataService.normalize_symbol(raw_symbol)] = position
        return holdings

    @classmethod
    def _assert_paper_trading_account(cls, account_id: Optional[int], user_id: int) -> Dict[str, Any]:
        account = cls._load_trade_service_account(account_id=account_id, user_id=user_id)
        if cls._is_paper_account(account):
            return account
        raise PermissionError("自动交易仅允许纸账户/模拟账户执行，当前账户未通过 paper 校验")

    @classmethod
    def _load_trade_service_account(cls, account_id: Optional[int], user_id: int) -> Dict[str, Any]:
        try:
            if account_id:
                response = cls._request_trade_service(
                    method="GET",
                    path="/api/v1/trade/accounts",
                    user_id=user_id,
                    timeout=30,
                )
                accounts = response.get("data") if isinstance(response.get("data"), list) else []
                for account in accounts:
                    if int(cls._read_order_attr(account, "id", 0) or 0) == int(account_id):
                        return dict(account)
                raise PermissionError("指定账户不存在或不可用")
            response = cls._request_trade_service(
                method="GET",
                path="/api/v1/trade/accounts/default",
                user_id=user_id,
                timeout=30,
            )
            data = response.get("data") if isinstance(response.get("data"), dict) else response
            return dict(data or {})
        except Exception as exc:
            raise PermissionError(f"纸账户校验失败: {exc}") from exc

    @classmethod
    def _is_paper_account(cls, account: Dict[str, Any]) -> bool:
        if not account:
            return False
        trading_mode = str(account.get("trading_mode") or account.get("tradingMode") or "").strip().lower()
        if trading_mode == "paper":
            return True
        if bool(account.get("isPaper") or account.get("is_paper")):
            return True
        descriptor = " ".join(
            str(account.get(key) or "")
            for key in ("account_id", "accountId", "display_name", "displayName", "broker_name", "brokerName", "name")
        ).upper()
        return any(keyword in descriptor for keyword in ("PAPER", "PAPERTRADING", "LBPT", "SIM", "SIMULAT", "DEMO", "SANDBOX", "模拟"))

    @staticmethod
    def _coerce_bool(value: Any, default: bool = False) -> bool:
        if value is None or value == "":
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value > 0
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on", "enabled"}:
            return True
        if text in {"0", "false", "no", "off", "disabled"}:
            return False
        return default

    @staticmethod
    def _read_number(item: Any, name: str, default: float = 0.0) -> float:
        if isinstance(item, dict):
            value = item.get(name)
        else:
            value = getattr(item, name, None)
        try:
            return float(value or default)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _position_quantity(cls, position: Any) -> int:
        for name in ("available_quantity", "availableQuantity", "quantity", "qty"):
            try:
                quantity = int(float(cls._read_order_attr(position, name, 0) or 0))
            except (TypeError, ValueError):
                quantity = 0
            if quantity > 0:
                return quantity
        return 0

    @classmethod
    def _build_watchlist_quant_metrics(
        cls,
        *,
        series: List[Dict[str, Any]],
        snapshot: Dict[str, Any],
        trend_scan: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        opens = [cls._safe_float(item.get('open') or item.get('close')) for item in series]
        closes = [cls._safe_float(item.get('close')) for item in series]
        highs = [cls._safe_float(item.get('high') or item.get('close')) for item in series]
        lows = [cls._safe_float(item.get('low') or item.get('close')) for item in series]
        volumes = [cls._safe_float(item.get('volume')) for item in series]
        latest = series[-1] if series else {}
        previous_close = closes[-2] if len(closes) >= 2 else 0.0
        latest_close = closes[-1] if closes else 0.0
        latest_open = opens[-1] if opens else latest_close
        latest_high = highs[-1] if highs else latest_close
        latest_low = lows[-1] if lows else latest_close
        ma5 = cls._moving_average(closes, 5)
        ma10 = cls._moving_average(closes, 10)
        ma20 = cls._moving_average(closes, 20)
        ma30 = cls._moving_average(closes, 30)
        ma60 = cls._moving_average(closes, 60)
        ma120 = cls._moving_average(closes, 120)
        ema12 = cls._ema(closes, 12)
        ema26 = cls._ema(closes, 26)
        return5 = cls._period_return(closes, 5)
        return10 = cls._period_return(closes, 10)
        return20 = cls._period_return(closes, 20)
        return30 = cls._period_return(closes, 30)
        return60 = cls._period_return(closes, 60)
        return120 = cls._period_return(closes, 120)
        rsi6 = cls._rsi(closes, 6)
        computed_rsi14 = cls._rsi(closes, 14)
        rsi14 = cls._safe_float(snapshot.get('rsi'), computed_rsi14) or computed_rsi14
        rsi28 = cls._rsi(closes, 28)
        macd_hist = cls._safe_float(snapshot.get('macdHist'), cls._macd_hist(closes))
        roc12 = cls._safe_float(snapshot.get('roc'), cls._period_return(closes, 12))
        volatility20 = cls._volatility(closes, 20)
        volatility5 = cls._volatility(closes, 5)
        volatility10 = cls._volatility(closes, 10)
        volatility60 = cls._volatility(closes, 60)
        high20_previous = max(highs[-21:-1]) if len(highs) >= 21 else max(highs[:-1] or highs or [0.0])
        high60_previous = max(highs[-61:-1]) if len(highs) >= 61 else max(highs[:-1] or highs or [0.0])
        low20 = min(lows[-20:]) if lows else 0.0
        low60 = min(lows[-60:]) if lows else 0.0
        avg_volume20 = cls._moving_average(volumes[:-1], 20) if len(volumes) > 1 else 0.0
        avg_volume5 = cls._moving_average(volumes[:-1], 5) if len(volumes) > 1 else 0.0
        avg_volume60 = cls._moving_average(volumes[:-1], 60) if len(volumes) > 1 else 0.0
        latest_volume = volumes[-1] if volumes else 0.0
        volume_ratio5 = round(latest_volume / avg_volume5, 2) if latest_volume and avg_volume5 else 0.0
        volume_ratio20 = round(volumes[-1] / avg_volume20, 2) if volumes and avg_volume20 else 0.0
        volume_ratio60 = round(latest_volume / avg_volume60, 2) if latest_volume and avg_volume60 else 0.0
        volume_trend20 = round(((avg_volume5 - avg_volume20) / avg_volume20) * 100, 2) if avg_volume5 and avg_volume20 else 0.0
        distance_high20 = round(((latest_close - high20_previous) / high20_previous) * 100, 2) if latest_close and high20_previous else 0.0
        distance_high60 = round(((latest_close - high60_previous) / high60_previous) * 100, 2) if latest_close and high60_previous else 0.0
        distance_low20 = round(((latest_close - low20) / low20) * 100, 2) if latest_close and low20 else 0.0
        distance_low60 = round(((latest_close - low60) / low60) * 100, 2) if latest_close and low60 else 0.0
        day_change_percent = round(((latest_close - previous_close) / previous_close) * 100, 2) if latest_close and previous_close else 0.0
        computed_atr14 = cls._atr(highs, lows, closes, 14)
        atr = cls._safe_float(snapshot.get('atr'), computed_atr14) or computed_atr14
        atr_percent = round((atr / latest_close) * 100, 2) if atr and latest_close else 0.0
        support_price = cls._safe_float(snapshot.get('supportPrice'))
        boll_mid = cls._moving_average(closes, 20)
        boll_std = cls._stddev(closes[-20:])
        boll_upper = cls._safe_float(snapshot.get('bollUpper'), boll_mid + boll_std * 2 if boll_mid else 0.0)
        boll_lower = cls._safe_float(snapshot.get('bollLower'), boll_mid - boll_std * 2 if boll_mid else 0.0)
        support_distance = cls._distance_percent(latest_close, support_price or boll_lower)
        boll_bandwidth = round(((boll_upper - boll_lower) / boll_mid) * 100, 2) if boll_mid else 0.0
        boll_percent_b = round(((latest_close - boll_lower) / (boll_upper - boll_lower)) * 100, 2) if boll_upper != boll_lower else 50.0
        true_range = max(latest_high - latest_low, abs(latest_high - previous_close), abs(latest_low - previous_close)) if previous_close else latest_high - latest_low
        k_len = round((latest_high - latest_low) / latest_close * 100, 2) if latest_close else 0.0
        k_mid = round((latest_close - latest_open) / latest_open * 100, 2) if latest_open else 0.0
        upper_shadow = round((latest_high - max(latest_open, latest_close)) / latest_close * 100, 2) if latest_close else 0.0
        lower_shadow = round((min(latest_open, latest_close) - latest_low) / latest_close * 100, 2) if latest_close else 0.0
        price_position20 = cls._price_position(latest_close, high20_previous, low20)
        price_position60 = cls._price_position(latest_close, high60_previous, low60)
        vwap20 = cls._vwap(highs, lows, closes, volumes, 20)
        vwap_distance20 = round(((latest_close - vwap20) / vwap20) * 100, 2) if latest_close and vwap20 else 0.0
        avg_dollar_volume20 = round(cls._moving_average([closes[index] * volumes[index] for index in range(len(closes))], 20), 2) if closes and volumes else 0.0
        ma_slope20 = cls._moving_average_slope(closes, 20)
        ma_spread20_60 = round(((ma20 - ma60) / ma60) * 100, 2) if ma20 and ma60 else 0.0
        obv_series = cls._obv_series(closes, volumes)
        obv_value = round(obv_series[-1], 2) if obv_series else 0.0
        obv_slope20 = cls._series_slope_percent(obv_series, 20)
        mfi14 = cls._money_flow_index(highs, lows, closes, volumes, 14)
        cmf20 = cls._chaikin_money_flow(highs, lows, closes, volumes, 20)
        stoch_k14 = cls._stochastic_k(closes, highs, lows, 14)
        williams_r14 = cls._williams_r(closes, highs, lows, 14)
        cci20 = cls._cci(highs, lows, closes, 20)
        adx14 = cls._adx(highs, lows, closes, 14)
        max_drawdown20 = cls._max_drawdown(closes, 20)
        max_drawdown60 = cls._max_drawdown(closes, 60)
        downside_vol20 = cls._downside_volatility(closes, 20)
        close_volume_corr20 = cls._rolling_correlation(closes, volumes, 20)
        return_volatility_ratio20 = round(return20 / volatility20, 2) if volatility20 else 0.0
        trend_strength = cls._safe_float((trend_scan or {}).get('trendStrength'))
        technical_score = cls._safe_float((trend_scan or {}).get('technicalScore'))
        factor_set = cls._build_alpha_factor_set(
            opens=opens,
            highs=highs,
            lows=lows,
            closes=closes,
            volumes=volumes,
        )

        return {
            "tradeDate": latest.get('date') or snapshot.get('tradeDate'),
            "historyCount": len(series),
            "factorSetVersion": factor_set["version"],
            "factorCount": factor_set["count"],
            "factorFamilies": factor_set["families"],
            "factorSet": factor_set,
            "latestClose": round(latest_close, 4),
            "latestOpen": round(latest_open, 4),
            "latestHigh": round(latest_high, 4),
            "latestLow": round(latest_low, 4),
            "latestVolume": round(latest_volume, 2),
            "dayChangePercent": day_change_percent,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "ma30": ma30,
            "ma60": ma60,
            "ma120": ma120,
            "ema12": ema12,
            "ema26": ema26,
            "return5": return5,
            "return10": return10,
            "return20": return20,
            "return30": return30,
            "return60": return60,
            "return120": return120,
            "returnVolatilityRatio20": return_volatility_ratio20,
            "rsi6": round(rsi6, 2),
            "rsi14": round(rsi14, 2),
            "rsi28": round(rsi28, 2),
            "macdHist": macd_hist,
            "roc": roc12,
            "roc12": roc12,
            "momentumScore": cls._safe_float(snapshot.get('momentumScore')),
            "stochK14": stoch_k14,
            "williamsR14": williams_r14,
            "cci20": cci20,
            "adx14": adx14,
            "volatility5": volatility5,
            "volatility10": volatility10,
            "volatility20": volatility20,
            "volatility60": volatility60,
            "atr14": round(atr, 4),
            "atrPercent": atr_percent,
            "atr14Percent": atr_percent,
            "bollMid20": round(boll_mid, 4),
            "bollUpper20": round(boll_upper, 4),
            "bollLower20": round(boll_lower, 4),
            "bollBandwidth20": boll_bandwidth,
            "bollPercentB20": boll_percent_b,
            "trueRangePercent": round((true_range / latest_close) * 100, 2) if true_range and latest_close else 0.0,
            "avgVolume5": round(avg_volume5, 2),
            "volumeRatio20": volume_ratio20,
            "avgVolume20": round(avg_volume20, 2),
            "avgVolume60": round(avg_volume60, 2),
            "volumeRatio5": volume_ratio5,
            "volumeRatio60": volume_ratio60,
            "volumeTrend20": volume_trend20,
            "avgDollarVolume20": avg_dollar_volume20,
            "obv": obv_value,
            "obvSlope20": obv_slope20,
            "mfi14": mfi14,
            "cmf20": cmf20,
            "closeVolumeCorr20": close_volume_corr20,
            "distanceHigh20": distance_high20,
            "distanceHigh60": distance_high60,
            "distanceLow20": distance_low20,
            "distanceLow60": distance_low60,
            "supportDistance": support_distance,
            "pricePosition20": price_position20,
            "pricePosition60": price_position60,
            "vwap20": vwap20,
            "vwapDistance20": vwap_distance20,
            "kMid": k_mid,
            "kLen": k_len,
            "upperShadow": upper_shadow,
            "lowerShadow": lower_shadow,
            "maSlope20": ma_slope20,
            "maSpread20_60": ma_spread20_60,
            "maxDrawdown20": max_drawdown20,
            "maxDrawdown60": max_drawdown60,
            "downsideVol20": downside_vol20,
            "trendStrength": trend_strength,
            "technicalScore": technical_score,
            "trendScanRisk": str((trend_scan or {}).get('riskLevel') or '').lower(),
            "trendScanDirection": str((trend_scan or {}).get('trendDirection') or '').lower(),
        }

    @classmethod
    def _score_watchlist_quant_metrics(cls, *, metrics: Dict[str, Any], strategy_profile: str) -> Dict[str, Any]:
        latest_close = cls._safe_float(metrics.get("latestClose"))
        ma5 = cls._safe_float(metrics.get("ma5"))
        ma10 = cls._safe_float(metrics.get("ma10"))
        ma20 = cls._safe_float(metrics.get("ma20"))
        ma30 = cls._safe_float(metrics.get("ma30"))
        ma60 = cls._safe_float(metrics.get("ma60"))
        ma120 = cls._safe_float(metrics.get("ma120"))
        ema12 = cls._safe_float(metrics.get("ema12"))
        ema26 = cls._safe_float(metrics.get("ema26"))
        rsi6 = cls._safe_float(metrics.get("rsi6"), 50.0)
        rsi14 = cls._safe_float(metrics.get("rsi14"), 50.0)
        rsi28 = cls._safe_float(metrics.get("rsi28"), 50.0)
        tags: List[str] = []

        trend_score = 0.0
        if latest_close and ma20 and latest_close >= ma20:
            trend_score += 11
            tags.append("站上20日线")
        if ma5 and ma10 and ma5 >= ma10:
            trend_score += 4
        if ma20 and ma60 and ma20 >= ma60:
            trend_score += 10
            tags.append("20/60多头")
        if ma60 and ma120 and ma60 >= ma120:
            trend_score += 6
            tags.append("中期趋势顺")
        if ma20 and ma30 and ma20 >= ma30:
            trend_score += 3
        if ema12 and ema26 and ema12 >= ema26:
            trend_score += 5
        trend_score += max(-8, min(10, cls._safe_float(metrics.get("return20")) / 1.8))
        trend_score += max(-6, min(8, cls._safe_float(metrics.get("return60")) / 3.5))
        trend_score += max(-5, min(6, cls._safe_float(metrics.get("maSlope20")) / 1.8))
        trend_score += max(-4, min(6, cls._safe_float(metrics.get("maSpread20_60")) / 2.2))
        if cls._safe_float(metrics.get("adx14")) >= 25:
            trend_score += 5
            tags.append("ADX趋势确认")
        if cls._safe_float(metrics.get("macdHist")) > 0:
            trend_score += 4
            tags.append("MACD偏多")
        trend_score += max(-5, min(6, (cls._safe_float(metrics.get("technicalScore")) - 55) / 8)) if metrics.get("technicalScore") else 0

        price_action_score = 0.0
        price_position20 = cls._safe_float(metrics.get("pricePosition20"), 50.0)
        price_position60 = cls._safe_float(metrics.get("pricePosition60"), 50.0)
        k_mid = cls._safe_float(metrics.get("kMid"))
        if 55 <= price_position20 <= 92:
            price_action_score += 7
        elif price_position20 >= 92:
            price_action_score += 3
        elif price_position20 <= 18:
            price_action_score -= 5
        if 50 <= price_position60 <= 90:
            price_action_score += 5
        if k_mid > 0:
            price_action_score += min(5, k_mid * 1.2)
        if cls._safe_float(metrics.get("lowerShadow")) >= cls._safe_float(metrics.get("upperShadow")) * 1.4 and k_mid >= -1.0:
            price_action_score += 4
            tags.append("下影承接")
        if cls._safe_float(metrics.get("upperShadow")) >= 3.0 and k_mid < 0:
            price_action_score -= 5
        boll_percent_b = cls._safe_float(metrics.get("bollPercentB20"), 50.0)
        if 45 <= boll_percent_b <= 88:
            price_action_score += 4
        elif boll_percent_b > 115:
            price_action_score -= 4
        price_action_score += max(-4, min(4, cls._safe_float(metrics.get("vwapDistance20")) / 2.5))

        momentum_score = 0.0
        momentum_score += max(-7, min(8, cls._safe_float(metrics.get("roc12")) / 2.0))
        momentum_score += max(-6, min(8, cls._safe_float(metrics.get("returnVolatilityRatio20")) * 2.0))
        if 52 <= rsi14 <= 72:
            momentum_score += 7
            tags.append("RSI强势区")
        elif rsi14 > 78:
            momentum_score -= 6
        elif rsi14 < 35:
            momentum_score -= 4
        if rsi6 >= rsi14 >= rsi28 and rsi14 >= 50:
            momentum_score += 5
        stoch_k14 = cls._safe_float(metrics.get("stochK14"), 50.0)
        if 45 <= stoch_k14 <= 82:
            momentum_score += 4
        elif stoch_k14 > 92:
            momentum_score -= 4
        williams_r14 = cls._safe_float(metrics.get("williamsR14"), -50.0)
        if -65 <= williams_r14 <= -20:
            momentum_score += 3
        elif williams_r14 > -10:
            momentum_score -= 3
        cci20 = cls._safe_float(metrics.get("cci20"))
        if 0 <= cci20 <= 180:
            momentum_score += 4
        elif cci20 > 240 or cci20 < -180:
            momentum_score -= 4
        momentum_score += max(-5, min(6, (cls._safe_float(metrics.get("momentumScore")) - 50) / 7)) if metrics.get("momentumScore") else 0

        breakout_score = 0.0
        distance_high20 = cls._safe_float(metrics.get("distanceHigh20"))
        distance_high60 = cls._safe_float(metrics.get("distanceHigh60"))
        volume_ratio20 = cls._safe_float(metrics.get("volumeRatio20"))
        if distance_high20 >= 0:
            breakout_score += 11
            tags.append("20日突破")
        elif distance_high20 >= -2.0:
            breakout_score += 7
            tags.append("接近20日高点")
        if distance_high60 >= 0:
            breakout_score += 8
            tags.append("60日突破")
        elif distance_high60 >= -3.5:
            breakout_score += 4
        if volume_ratio20 >= 1.5:
            breakout_score += 7
            tags.append("明显放量")
        elif volume_ratio20 >= 1.15:
            breakout_score += 4
            tags.append("温和放量")
        if cls._safe_float(metrics.get("volumeRatio60")) >= 1.2:
            breakout_score += 3
        if cls._safe_float(metrics.get("return20")) > 0 and cls._safe_float(metrics.get("dayChangePercent")) > 0:
            breakout_score += 4
        if cls._safe_float(metrics.get("bollBandwidth20")) <= 8 and distance_high20 >= -4:
            breakout_score += 3

        volume_flow_score = 0.0
        if cls._safe_float(metrics.get("volumeRatio5")) >= 1.1 and cls._safe_float(metrics.get("dayChangePercent")) > 0:
            volume_flow_score += 5
        if cls._safe_float(metrics.get("obvSlope20")) > 0:
            volume_flow_score += min(7, cls._safe_float(metrics.get("obvSlope20")) / 4)
            tags.append("OBV走强")
        mfi14 = cls._safe_float(metrics.get("mfi14"), 50.0)
        if 45 <= mfi14 <= 75:
            volume_flow_score += 5
        elif mfi14 > 85:
            volume_flow_score -= 4
        elif mfi14 < 25:
            volume_flow_score -= 3
        cmf20 = cls._safe_float(metrics.get("cmf20"))
        if cmf20 > 0.05:
            volume_flow_score += 5
            tags.append("资金流入")
        elif cmf20 < -0.08:
            volume_flow_score -= 5
        volume_flow_score += max(-4, min(4, cls._safe_float(metrics.get("closeVolumeCorr20")) * 5))

        reversion_score = 0.0
        support_distance = cls._safe_float(metrics.get("supportDistance"), 100.0)
        if 28 <= rsi14 <= 45 and support_distance <= 4.0:
            reversion_score += 10
            tags.append("支撑回升")
        if rsi14 < 35 and cls._safe_float(metrics.get("dayChangePercent")) > 0:
            reversion_score += 7
            tags.append("RSI低位反弹")
        if latest_close and ma20 and latest_close < ma20 and cls._safe_float(metrics.get("return20")) > -8:
            reversion_score += 4
        if cls._safe_float(metrics.get("bollPercentB20"), 50.0) <= 18 and cls._safe_float(metrics.get("dayChangePercent")) > 0:
            reversion_score += 6
            tags.append("布林下轨反弹")
        if cls._safe_float(metrics.get("distanceLow20")) <= 4 and cls._safe_float(metrics.get("return5")) > 0:
            reversion_score += 4

        volatility_score = 0.0
        volatility20 = cls._safe_float(metrics.get("volatility20"))
        atr_percent = cls._safe_float(metrics.get("atr14Percent"), cls._safe_float(metrics.get("atrPercent")))
        boll_bandwidth = cls._safe_float(metrics.get("bollBandwidth20"))
        if 0.8 <= volatility20 <= 3.4:
            volatility_score += 7
        elif volatility20 < 0.8 and cls._safe_float(metrics.get("return20")) > 0:
            volatility_score += 2
        elif volatility20 >= 5.2:
            volatility_score -= 8
        if 0.4 <= atr_percent <= 4.0:
            volatility_score += 5
        elif atr_percent > 6.0:
            volatility_score -= 7
        if 4 <= boll_bandwidth <= 18:
            volatility_score += 4
        elif boll_bandwidth > 30:
            volatility_score -= 4
        volatility_score -= max(0, min(6, (cls._safe_float(metrics.get("downsideVol20")) - 2.5) * 1.5))

        liquidity_score = 0.0
        avg_dollar_volume20 = cls._safe_float(metrics.get("avgDollarVolume20"))
        avg_volume20 = cls._safe_float(metrics.get("avgVolume20"))
        if avg_dollar_volume20 >= 50_000_000:
            liquidity_score += 8
        elif avg_dollar_volume20 >= 5_000_000:
            liquidity_score += 5
        elif avg_volume20 > 0:
            liquidity_score += 2
        if cls._safe_float(metrics.get("volumeTrend20")) > 0:
            liquidity_score += min(4, cls._safe_float(metrics.get("volumeTrend20")) / 12)
        if abs(cls._safe_float(metrics.get("vwapDistance20"))) <= 5:
            liquidity_score += 3

        ai_score = 0.0
        if str(metrics.get("trendScanDirection") or "").lower() == "up":
            ai_score += 6
        if metrics.get("trendStrength"):
            ai_score += max(-4, min(6, (cls._safe_float(metrics.get("trendStrength")) - 50) / 8))
        if metrics.get("technicalScore"):
            ai_score += max(-4, min(6, (cls._safe_float(metrics.get("technicalScore")) - 55) / 8))

        risk_penalty = 0.0
        risk_level = 'low'
        if str(metrics.get("trendScanRisk") or "").lower() == 'high':
            risk_penalty += 16
            risk_level = 'high'
        elif str(metrics.get("trendScanRisk") or "").lower() == 'medium':
            risk_penalty += 5
            risk_level = 'medium'
        if volatility20 >= 5.2 or atr_percent >= 6.0:
            risk_penalty += 14
            risk_level = 'high'
        elif volatility20 >= 3.4 or atr_percent >= 4.0:
            risk_penalty += 6
            if risk_level == 'low':
                risk_level = 'medium'
        if rsi14 >= 82:
            risk_penalty += 9
            if risk_level == 'low':
                risk_level = 'medium'
        if cls._safe_float(metrics.get("return20")) <= -12 or distance_high20 <= -18:
            risk_penalty += 12
            risk_level = 'high'
        if cls._safe_float(metrics.get("maxDrawdown20")) <= -14 or cls._safe_float(metrics.get("maxDrawdown60")) <= -22:
            risk_penalty += 9
            risk_level = 'high'
        if cls._safe_float(metrics.get("downsideVol20")) >= 4.5:
            risk_penalty += 6
            if risk_level == 'low':
                risk_level = 'medium'

        weights = {
            "balanced": {
                "trend": 0.30,
                "priceAction": 0.14,
                "momentum": 0.18,
                "breakout": 0.16,
                "volumeFlow": 0.12,
                "reversion": 0.08,
                "volatility": 0.10,
                "liquidity": 0.06,
            },
            "momentum": {
                "trend": 0.38,
                "priceAction": 0.12,
                "momentum": 0.28,
                "breakout": 0.15,
                "volumeFlow": 0.12,
                "reversion": 0.02,
                "volatility": 0.08,
                "liquidity": 0.05,
            },
            "breakout": {
                "trend": 0.26,
                "priceAction": 0.16,
                "momentum": 0.14,
                "breakout": 0.34,
                "volumeFlow": 0.18,
                "reversion": 0.02,
                "volatility": 0.08,
                "liquidity": 0.06,
            },
            "reversion": {
                "trend": 0.16,
                "priceAction": 0.16,
                "momentum": 0.10,
                "breakout": 0.04,
                "volumeFlow": 0.08,
                "reversion": 0.46,
                "volatility": 0.12,
                "liquidity": 0.05,
            },
        }.get(strategy_profile, {})
        weights = weights or {
            "trend": 0.30,
            "priceAction": 0.14,
            "momentum": 0.18,
            "breakout": 0.16,
            "volumeFlow": 0.12,
            "reversion": 0.08,
            "volatility": 0.10,
            "liquidity": 0.06,
        }
        raw_total = (
            42
            + trend_score * weights["trend"]
            + price_action_score * weights["priceAction"]
            + momentum_score * weights["momentum"]
            + breakout_score * weights["breakout"]
            + volume_flow_score * weights["volumeFlow"]
            + reversion_score * weights["reversion"]
            + volatility_score * weights["volatility"]
            + liquidity_score * weights["liquidity"]
            + ai_score
            - risk_penalty
        )
        total = round(max(0.0, min(100.0, raw_total)), 2)
        trend_direction = 'up' if trend_score + momentum_score * 0.35 >= 22 else 'down' if trend_score <= -5 else 'sideways'

        return {
            "factorVersion": "watchlist-factor-v2",
            "total": total,
            "trend": round(trend_score, 2),
            "priceAction": round(price_action_score, 2),
            "momentum": round(momentum_score, 2),
            "breakout": round(breakout_score, 2),
            "volumeFlow": round(volume_flow_score, 2),
            "reversion": round(reversion_score, 2),
            "volatility": round(volatility_score, 2),
            "liquidity": round(liquidity_score, 2),
            "aiTrend": round(ai_score, 2),
            "riskPenalty": round(risk_penalty, 2),
            "riskLevel": risk_level,
            "trendDirection": trend_direction,
            "tags": tags or ["持续观察"],
        }

    @classmethod
    def _safe_get_indicator_snapshot(cls, symbol: str, user_id: int) -> Dict[str, Any]:
        try:
            return IndicatorSnapshotService.get_snapshot(symbol, timeframe='daily', user_id=user_id) or {}
        except Exception:
            return {}

    @classmethod
    def _safe_get_trend_scan(cls, symbol: str) -> Optional[Dict[str, Any]]:
        try:
            return DailySymbolTrendScanService.get_latest_for_symbol(symbol)
        except Exception:
            return None

    @classmethod
    def _load_watchlist_scan_targets(
        cls,
        *,
        user_id: int,
        session_filter: str = 'all',
    ) -> List[Dict[str, Any]]:
        WatchlistService = cls._load_watchlist_service()
        if not WatchlistService:
            return []
        try:
            payload = WatchlistService.list_scan_targets(
                user_id=int(user_id),
                session_filter=session_filter,
            )
            items = payload.get('items') if isinstance(payload, dict) else []
            return items if isinstance(items, list) else []
        except Exception:
            return []

    @classmethod
    def _load_watchlist_symbols(cls, *, user_id: int) -> set[str]:
        symbols = set()
        for item in cls._load_watchlist_scan_targets(user_id=user_id, session_filter='all'):
            raw_symbol = item.get('symbol') if isinstance(item, dict) else item
            market = item.get('market') if isinstance(item, dict) else None
            normalized_symbol = cls._normalize_watchlist_symbol(raw_symbol, market=market)
            if normalized_symbol:
                symbols.add(normalized_symbol)
        return symbols

    @staticmethod
    def _normalize_watchlist_symbol(raw_symbol: Any, market: Optional[str] = None) -> str:
        symbol = str(raw_symbol or '').strip().upper()
        if not symbol:
            return ''
        if '.' in symbol:
            return HistoricalMarketDataService.normalize_symbol(symbol)

        safe_market = str(market or '').strip().upper()
        if safe_market == 'HK':
            return f"{symbol}.HK"
        if safe_market == 'CN':
            if symbol.startswith(('60', '68', '90')):
                return f"{symbol}.SH"
            if symbol.startswith(('43', '83', '87', '92')):
                return f"{symbol}.BJ"
            return f"{symbol}.SZ"
        if safe_market == 'US':
            return f"{symbol}.US"
        return HistoricalMarketDataService.normalize_symbol(symbol)

    @staticmethod
    def _load_watchlist_service():
        try:
            from apps.market.market_service.src.watchlist_service import WatchlistService  # type: ignore
            return WatchlistService
        except Exception:
            service_path = Path(__file__).resolve().parents[4] / "apps" / "market" / "market-service" / "src" / "watchlist_service.py"
            try:
                spec = importlib.util.spec_from_file_location("quant_watchlist_service", str(service_path))
                if not spec or not spec.loader:
                    return None
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return getattr(module, "WatchlistService", None)
            except Exception:
                return None

    @classmethod
    def _build_alpha_factor_set(
        cls,
        *,
        opens: List[float],
        highs: List[float],
        lows: List[float],
        closes: List[float],
        volumes: List[float],
    ) -> Dict[str, Any]:
        count = min(len(opens), len(highs), len(lows), len(closes), len(volumes))
        if count <= 0:
            return {"version": "watchlist-alpha-factor-v1", "count": 0, "families": {}, "values": {}}

        opens = [float(item or 0.0) for item in opens[-count:]]
        highs = [float(item or 0.0) for item in highs[-count:]]
        lows = [float(item or 0.0) for item in lows[-count:]]
        closes = [float(item or 0.0) for item in closes[-count:]]
        volumes = [float(item or 0.0) for item in volumes[-count:]]
        typical = [(highs[index] + lows[index] + closes[index]) / 3 for index in range(count)]
        hl2 = [(highs[index] + lows[index]) / 2 for index in range(count)]
        oc2 = [(opens[index] + closes[index]) / 2 for index in range(count)]
        dollar_volume = [closes[index] * volumes[index] for index in range(count)]
        range_percent = [cls._safe_factor_ratio(highs[index] - lows[index], closes[index]) * 100 for index in range(count)]
        body_percent = [cls._safe_factor_ratio(closes[index] - opens[index], opens[index]) * 100 for index in range(count)]
        absolute_body_percent = [abs(item) for item in body_percent]
        upper_shadow_percent = [
            cls._safe_factor_ratio(highs[index] - max(opens[index], closes[index]), closes[index]) * 100
            for index in range(count)
        ]
        lower_shadow_percent = [
            cls._safe_factor_ratio(min(opens[index], closes[index]) - lows[index], closes[index]) * 100
            for index in range(count)
        ]
        close_location = [
            cls._safe_factor_ratio(closes[index] - lows[index], highs[index] - lows[index]) * 100
            if highs[index] != lows[index] else 50.0
            for index in range(count)
        ]
        intraday_strength = [
            cls._safe_factor_ratio((closes[index] - lows[index]) - (highs[index] - closes[index]), highs[index] - lows[index])
            if highs[index] != lows[index] else 0.0
            for index in range(count)
        ]
        signed_volume = [
            volumes[index] if index > 0 and closes[index] > closes[index - 1]
            else -volumes[index] if index > 0 and closes[index] < closes[index - 1]
            else 0.0
            for index in range(count)
        ]
        money_flow_proxy = [intraday_strength[index] * volumes[index] for index in range(count)]

        def returns(values: List[float]) -> List[float]:
            output: List[float] = [0.0]
            for index in range(1, len(values)):
                output.append(cls._safe_factor_ratio(values[index] - values[index - 1], values[index - 1]) * 100)
            return output

        close_returns = returns(closes)
        typical_returns = returns(typical)
        hl2_returns = returns(hl2)
        volume_returns = returns(volumes)
        dollar_volume_returns = returns(dollar_volume)
        obv = cls._obv_series(closes, volumes)
        if len(obv) < count:
            obv = ([0.0] * (count - len(obv))) + obv

        values: Dict[str, float] = {}
        families: Dict[str, int] = {}

        def add(family: str, name: str, value: Any) -> None:
            key = f"{family}.{name}"
            if key in values:
                return
            values[key] = cls._finite_factor_value(value)
            families[family] = families.get(family, 0) + 1

        def last(values_: List[float], lag: int = 0) -> float:
            index = len(values_) - 1 - max(0, int(lag or 0))
            return float(values_[index] or 0.0) if 0 <= index < len(values_) else 0.0

        def window(values_: List[float], size: int, lag: int = 0) -> List[float]:
            end = len(values_) - max(0, int(lag or 0))
            if end <= 0:
                return []
            start = max(0, end - max(1, int(size or 1)))
            return [float(item or 0.0) for item in values_[start:end]]

        def mean(sample: List[float]) -> float:
            return sum(sample) / len(sample) if sample else 0.0

        def std(sample: List[float]) -> float:
            if not sample:
                return 0.0
            average = mean(sample)
            return (sum((item - average) ** 2 for item in sample) / len(sample)) ** 0.5

        def rank_percent(sample: List[float], value: float) -> float:
            if not sample:
                return 50.0
            below_or_equal = len([item for item in sample if item <= value])
            return (below_or_equal / len(sample)) * 100

        def period_return(values_: List[float], period: int, lag: int = 0) -> float:
            end = len(values_) - max(0, int(lag or 0))
            latest_index = end - 1
            base_index = latest_index - max(1, int(period or 1))
            if latest_index < 0 or base_index < 0:
                return 0.0
            return cls._safe_factor_ratio(values_[latest_index] - values_[base_index], values_[base_index]) * 100

        def correlation(left: List[float], right: List[float], size: int, lag: int = 0) -> float:
            left_sample = window(left, size, lag)
            right_sample = window(right, size, lag)
            sample_count = min(len(left_sample), len(right_sample))
            if sample_count < 2:
                return 0.0
            left_sample = left_sample[-sample_count:]
            right_sample = right_sample[-sample_count:]
            left_mean = mean(left_sample)
            right_mean = mean(right_sample)
            numerator = sum((left_sample[index] - left_mean) * (right_sample[index] - right_mean) for index in range(sample_count))
            left_var = sum((item - left_mean) ** 2 for item in left_sample)
            right_var = sum((item - right_mean) ** 2 for item in right_sample)
            denominator = (left_var * right_var) ** 0.5
            return numerator / denominator if denominator else 0.0

        windows = [3, 5, 7, 10, 14, 20, 30, 40, 60, 90]
        long_windows = [5, 10, 14, 20, 30, 40, 60, 90, 120]
        periods = [1, 2, 3, 5, 7, 10, 14, 20, 30, 40, 60, 90]
        lag_range = range(0, 3)
        raw_lag_range = range(0, 12)

        raw_fields = {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
            "typical": typical,
            "hl2": hl2,
            "oc2": oc2,
            "range_pct": range_percent,
            "body_pct": body_percent,
            "upper_shadow": upper_shadow_percent,
            "lower_shadow": lower_shadow_percent,
            "dollar_volume": dollar_volume,
        }
        for field_name, field_values in raw_fields.items():
            for lag in raw_lag_range:
                add("lag", f"{field_name}_l{lag}", last(field_values, lag))

        trend_fields = {"close": closes, "typical": typical, "hl2": hl2, "oc2": oc2}
        for field_name, field_values in trend_fields.items():
            for size in windows:
                for lag in lag_range:
                    sample = window(field_values, size, lag)
                    current = last(field_values, lag)
                    average = mean(sample)
                    previous_average = mean(window(field_values, size, lag + 5))
                    add("trend", f"{field_name}_ma_ratio_w{size}_l{lag}", cls._safe_factor_ratio(current - average, average) * 100)
                    add("trend", f"{field_name}_ma_slope_w{size}_l{lag}", cls._safe_factor_ratio(average - previous_average, previous_average) * 100)
        for short_index, short_window in enumerate(windows[:-1]):
            for long_window in windows[short_index + 1:]:
                short_average = mean(window(closes, short_window, 0))
                long_average = mean(window(closes, long_window, 0))
                add("trend", f"close_ma_spread_w{short_window}_{long_window}", cls._safe_factor_ratio(short_average - long_average, long_average) * 100)
                add("trend", f"close_ma_spread_rank_w{short_window}_{long_window}", rank_percent(window(closes, long_window, 0), short_average))

        momentum_fields = {"close": closes, "open": opens, "high": highs, "low": lows, "typical": typical}
        for field_name, field_values in momentum_fields.items():
            for period in periods:
                for lag in lag_range:
                    ret = period_return(field_values, period, lag)
                    return_sample = window(returns(field_values), max(period, 5), lag)
                    ret_std = std(return_sample)
                    add("momentum", f"{field_name}_ret_p{period}_l{lag}", ret)
                    add("momentum", f"{field_name}_ret_vol_adj_p{period}_l{lag}", cls._safe_factor_ratio(ret, ret_std))
        for size in windows:
            for lag in range(0, 3):
                sample = window(close_returns, size, lag)
                positive_ratio = len([item for item in sample if item > 0]) / len(sample) if sample else 0.0
                negative_ratio = len([item for item in sample if item < 0]) / len(sample) if sample else 0.0
                add("momentum", f"close_positive_ratio_w{size}_l{lag}", positive_ratio * 100)
                add("momentum", f"close_negative_ratio_w{size}_l{lag}", negative_ratio * 100)

        volatility_return_fields = {"close": close_returns, "typical": typical_returns, "hl2": hl2_returns}
        for field_name, field_values in volatility_return_fields.items():
            for size in windows:
                for lag in lag_range:
                    sample = window(field_values, size, lag)
                    downside_sample = [item for item in sample if item < 0]
                    current = last(field_values, lag)
                    average = mean(sample)
                    dispersion = std(sample)
                    add("volatility", f"{field_name}_ret_std_w{size}_l{lag}", dispersion)
                    add("volatility", f"{field_name}_ret_downside_std_w{size}_l{lag}", std(downside_sample))
                    add("volatility", f"{field_name}_ret_z_w{size}_l{lag}", cls._safe_factor_ratio(current - average, dispersion))
        for size in windows:
            for lag in lag_range:
                range_sample = window(range_percent, size, lag)
                body_sample = window(absolute_body_percent, size, lag)
                add("volatility", f"range_mean_w{size}_l{lag}", mean(range_sample))
                add("volatility", f"range_std_w{size}_l{lag}", std(range_sample))
                add("volatility", f"body_std_w{size}_l{lag}", std(body_sample))

        flow_fields = {
            "volume": volumes,
            "dollar_volume": dollar_volume,
            "signed_volume": signed_volume,
            "money_flow": money_flow_proxy,
            "obv": obv,
        }
        for field_name, field_values in flow_fields.items():
            for size in windows:
                for lag in lag_range:
                    sample = window(field_values, size, lag)
                    current = last(field_values, lag)
                    average = mean(sample)
                    dispersion = std(sample)
                    previous_average = mean(window(field_values, size, lag + 5))
                    add("volume_flow", f"{field_name}_avg_ratio_w{size}_l{lag}", cls._safe_factor_ratio(current - average, average) * 100)
                    add("volume_flow", f"{field_name}_z_w{size}_l{lag}", cls._safe_factor_ratio(current - average, dispersion))
                    add("volume_flow", f"{field_name}_trend_w{size}_l{lag}", cls._safe_factor_ratio(average - previous_average, previous_average) * 100)

        candle_fields = {
            "range_pct": range_percent,
            "body_pct": body_percent,
            "abs_body_pct": absolute_body_percent,
            "upper_shadow": upper_shadow_percent,
            "lower_shadow": lower_shadow_percent,
            "close_location": close_location,
            "intraday_strength": intraday_strength,
        }
        for field_name, field_values in candle_fields.items():
            for lag in raw_lag_range:
                add("price_action", f"{field_name}_l{lag}", last(field_values, lag))
            for size in windows:
                for lag in range(0, 2):
                    sample = window(field_values, size, lag)
                    current = last(field_values, lag)
                    dispersion = std(sample)
                    add("price_action", f"{field_name}_mean_w{size}_l{lag}", mean(sample))
                    add("price_action", f"{field_name}_z_w{size}_l{lag}", cls._safe_factor_ratio(current - mean(sample), dispersion))
                    add("price_action", f"{field_name}_rank_w{size}_l{lag}", rank_percent(sample, current))

        range_fields = {"close": closes, "high": highs, "low": lows, "typical": typical}
        for field_name, field_values in range_fields.items():
            for size in long_windows:
                for lag in range(0, 3):
                    sample = window(field_values, size, lag)
                    current = last(field_values, lag)
                    high = max(sample) if sample else 0.0
                    low = min(sample) if sample else 0.0
                    peak = high
                    add("range_drawdown", f"{field_name}_pos_w{size}_l{lag}", cls._safe_factor_ratio(current - low, high - low) * 100 if high != low else 50.0)
                    add("range_drawdown", f"{field_name}_dist_high_w{size}_l{lag}", cls._safe_factor_ratio(current - high, high) * 100)
                    add("range_drawdown", f"{field_name}_dist_low_w{size}_l{lag}", cls._safe_factor_ratio(current - low, low) * 100)
                    add("range_drawdown", f"{field_name}_drawdown_w{size}_l{lag}", cls._safe_factor_ratio(current - peak, peak) * 100)

        liquidity_fields = {"volume": volumes, "dollar_volume": dollar_volume}
        for field_name, field_values in liquidity_fields.items():
            for size in windows:
                for lag in lag_range:
                    sample = window(field_values, size, lag)
                    current = last(field_values, lag)
                    average = mean(sample)
                    dispersion = std(sample)
                    zero_rate = len([item for item in sample if item <= 0]) / len(sample) if sample else 0.0
                    add("liquidity", f"{field_name}_avg_w{size}_l{lag}", average)
                    add("liquidity", f"{field_name}_latest_to_avg_w{size}_l{lag}", cls._safe_factor_ratio(current, average))
                    add("liquidity", f"{field_name}_cv_w{size}_l{lag}", cls._safe_factor_ratio(dispersion, average))
                    add("liquidity", f"{field_name}_zero_rate_w{size}_l{lag}", zero_rate * 100)

        correlation_pairs = {
            "close_ret_volume_ret": (close_returns, volume_returns),
            "close_ret_dollar_ret": (close_returns, dollar_volume_returns),
            "close_ret_range": (close_returns, range_percent),
            "close_ret_body": (close_returns, body_percent),
            "volume_body": (volume_returns, body_percent),
            "volume_range": (volume_returns, range_percent),
            "obv_close": (obv, closes),
            "money_flow_close": (money_flow_proxy, closes),
        }
        for pair_name, (left, right) in correlation_pairs.items():
            for size in [5, 10, 14, 20, 30, 60, 90]:
                for lag in lag_range:
                    add("correlation", f"{pair_name}_corr_w{size}_l{lag}", correlation(left, right, size, lag))

        return {
            "version": "watchlist-alpha-factor-v1",
            "count": len(values),
            "families": families,
            "values": values,
        }

    @staticmethod
    def _moving_average(values: List[float], window: int) -> float:
        sample = values[-window:] if len(values) >= window else values
        return round(sum(sample) / len(sample), 4) if sample else 0.0

    @staticmethod
    def _stddev(values: List[float]) -> float:
        sample = [float(item or 0.0) for item in values if item is not None]
        if not sample:
            return 0.0
        mean = sum(sample) / len(sample)
        variance = sum((item - mean) ** 2 for item in sample) / len(sample)
        return round(variance ** 0.5, 4)

    @staticmethod
    def _ema(values: List[float], window: int) -> float:
        sample = [float(item or 0.0) for item in values if item is not None]
        if not sample:
            return 0.0
        span = max(1, int(window or 1))
        alpha = 2 / (span + 1)
        ema = sample[0]
        for value in sample[1:]:
            ema = value * alpha + ema * (1 - alpha)
        return round(ema, 4)

    @classmethod
    def _macd_hist(cls, values: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> float:
        sample = [float(item or 0.0) for item in values if item is not None]
        if len(sample) < slow:
            return 0.0
        alpha_fast = 2 / (fast + 1)
        alpha_slow = 2 / (slow + 1)
        alpha_signal = 2 / (signal + 1)
        ema_fast = sample[0]
        ema_slow = sample[0]
        signal_line = 0.0
        for index, value in enumerate(sample):
            if index == 0:
                continue
            ema_fast = value * alpha_fast + ema_fast * (1 - alpha_fast)
            ema_slow = value * alpha_slow + ema_slow * (1 - alpha_slow)
            dif = ema_fast - ema_slow
            signal_line = dif if index == 1 else dif * alpha_signal + signal_line * (1 - alpha_signal)
        return round((ema_fast - ema_slow) - signal_line, 4)

    @staticmethod
    def _period_return(values: List[float], periods: int) -> float:
        if len(values) <= periods:
            return 0.0
        base = float(values[-periods - 1] or 0)
        latest = float(values[-1] or 0)
        return round(((latest - base) / base) * 100, 2) if base else 0.0

    @staticmethod
    def _rsi(values: List[float], periods: int = 14) -> float:
        if len(values) <= periods:
            return 50.0
        changes = [values[index] - values[index - 1] for index in range(1, len(values))]
        sample = changes[-periods:]
        gains = [max(change, 0) for change in sample]
        losses = [abs(min(change, 0)) for change in sample]
        avg_gain = sum(gains) / periods
        avg_loss = sum(losses) / periods
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    @staticmethod
    def _volatility(values: List[float], periods: int = 20) -> float:
        if len(values) <= periods:
            return 0.0
        returns = []
        sample = values[-periods - 1:]
        for index in range(1, len(sample)):
            base = float(sample[index - 1] or 0)
            current = float(sample[index] or 0)
            if base:
                returns.append(((current - base) / base) * 100)
        if not returns:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((item - mean) ** 2 for item in returns) / len(returns)
        return round(variance ** 0.5, 2)

    @staticmethod
    def _downside_volatility(values: List[float], periods: int = 20) -> float:
        if len(values) <= periods:
            return 0.0
        sample = values[-periods - 1:]
        downside_returns = []
        for index in range(1, len(sample)):
            base = float(sample[index - 1] or 0)
            current = float(sample[index] or 0)
            if base:
                value = ((current - base) / base) * 100
                if value < 0:
                    downside_returns.append(value)
        if not downside_returns:
            return 0.0
        mean = sum(downside_returns) / len(downside_returns)
        variance = sum((item - mean) ** 2 for item in downside_returns) / len(downside_returns)
        return round(variance ** 0.5, 2)

    @staticmethod
    def _atr(highs: List[float], lows: List[float], closes: List[float], periods: int = 14) -> float:
        if not highs or not lows or not closes:
            return 0.0
        start = max(1, len(closes) - max(1, periods))
        true_ranges: List[float] = []
        for index in range(start, len(closes)):
            high = float(highs[index] or 0.0)
            low = float(lows[index] or 0.0)
            previous_close = float(closes[index - 1] or 0.0)
            true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        return round(sum(true_ranges) / len(true_ranges), 4) if true_ranges else 0.0

    @staticmethod
    def _price_position(value: float, high: float, low: float) -> float:
        if not value or not high or not low or high == low:
            return 50.0
        return round(((value - low) / (high - low)) * 100, 2)

    @staticmethod
    def _vwap(highs: List[float], lows: List[float], closes: List[float], volumes: List[float], periods: int = 20) -> float:
        if not closes or not volumes:
            return 0.0
        start = max(0, len(closes) - max(1, periods))
        weighted = 0.0
        volume_total = 0.0
        for index in range(start, len(closes)):
            typical = (float(highs[index] or 0.0) + float(lows[index] or 0.0) + float(closes[index] or 0.0)) / 3
            volume = float(volumes[index] or 0.0)
            weighted += typical * volume
            volume_total += volume
        return round(weighted / volume_total, 4) if volume_total else 0.0

    @classmethod
    def _moving_average_slope(cls, values: List[float], window: int = 20) -> float:
        span = max(2, int(window or 2))
        if len(values) < span + 5:
            return 0.0
        current = cls._moving_average(values, span)
        previous = cls._moving_average(values[:-5], span)
        return round(((current - previous) / previous) * 100, 2) if previous else 0.0

    @staticmethod
    def _obv_series(closes: List[float], volumes: List[float]) -> List[float]:
        if not closes or not volumes:
            return []
        values = [0.0]
        for index in range(1, min(len(closes), len(volumes))):
            previous = float(closes[index - 1] or 0.0)
            current = float(closes[index] or 0.0)
            volume = float(volumes[index] or 0.0)
            if current > previous:
                values.append(values[-1] + volume)
            elif current < previous:
                values.append(values[-1] - volume)
            else:
                values.append(values[-1])
        return values

    @staticmethod
    def _series_slope_percent(values: List[float], window: int = 20) -> float:
        if len(values) <= window:
            return 0.0
        current = float(values[-1] or 0.0)
        previous = float(values[-window - 1] or 0.0)
        scale = max(abs(previous), 1.0)
        return round(((current - previous) / scale) * 100, 2)

    @staticmethod
    def _money_flow_index(highs: List[float], lows: List[float], closes: List[float], volumes: List[float], periods: int = 14) -> float:
        if len(closes) <= periods or not volumes:
            return 50.0
        positive = 0.0
        negative = 0.0
        start = len(closes) - periods
        for index in range(start, len(closes)):
            typical = (float(highs[index] or 0.0) + float(lows[index] or 0.0) + float(closes[index] or 0.0)) / 3
            previous_typical = (float(highs[index - 1] or 0.0) + float(lows[index - 1] or 0.0) + float(closes[index - 1] or 0.0)) / 3
            money_flow = typical * float(volumes[index] or 0.0)
            if typical > previous_typical:
                positive += money_flow
            elif typical < previous_typical:
                negative += money_flow
        if negative == 0:
            return 100.0 if positive > 0 else 50.0
        ratio = positive / negative
        return round(100 - (100 / (1 + ratio)), 2)

    @staticmethod
    def _chaikin_money_flow(highs: List[float], lows: List[float], closes: List[float], volumes: List[float], periods: int = 20) -> float:
        if not closes or not volumes:
            return 0.0
        start = max(0, len(closes) - max(1, periods))
        flow_volume = 0.0
        volume_total = 0.0
        for index in range(start, len(closes)):
            high = float(highs[index] or 0.0)
            low = float(lows[index] or 0.0)
            close = float(closes[index] or 0.0)
            volume = float(volumes[index] or 0.0)
            multiplier = ((close - low) - (high - close)) / (high - low) if high != low else 0.0
            flow_volume += multiplier * volume
            volume_total += volume
        return round(flow_volume / volume_total, 4) if volume_total else 0.0

    @staticmethod
    def _stochastic_k(closes: List[float], highs: List[float], lows: List[float], periods: int = 14) -> float:
        if not closes:
            return 50.0
        sample_highs = highs[-periods:] if len(highs) >= periods else highs
        sample_lows = lows[-periods:] if len(lows) >= periods else lows
        highest = max(sample_highs or [0.0])
        lowest = min(sample_lows or [0.0])
        latest = float(closes[-1] or 0.0)
        return round(((latest - lowest) / (highest - lowest)) * 100, 2) if highest != lowest else 50.0

    @staticmethod
    def _williams_r(closes: List[float], highs: List[float], lows: List[float], periods: int = 14) -> float:
        if not closes:
            return -50.0
        sample_highs = highs[-periods:] if len(highs) >= periods else highs
        sample_lows = lows[-periods:] if len(lows) >= periods else lows
        highest = max(sample_highs or [0.0])
        lowest = min(sample_lows or [0.0])
        latest = float(closes[-1] or 0.0)
        return round(-100 * ((highest - latest) / (highest - lowest)), 2) if highest != lowest else -50.0

    @staticmethod
    def _cci(highs: List[float], lows: List[float], closes: List[float], periods: int = 20) -> float:
        if not closes:
            return 0.0
        start = max(0, len(closes) - max(1, periods))
        typical_prices = [
            (float(highs[index] or 0.0) + float(lows[index] or 0.0) + float(closes[index] or 0.0)) / 3
            for index in range(start, len(closes))
        ]
        if not typical_prices:
            return 0.0
        average = sum(typical_prices) / len(typical_prices)
        mean_deviation = sum(abs(item - average) for item in typical_prices) / len(typical_prices)
        if mean_deviation == 0:
            return 0.0
        return round((typical_prices[-1] - average) / (0.015 * mean_deviation), 2)

    @staticmethod
    def _adx(highs: List[float], lows: List[float], closes: List[float], periods: int = 14) -> float:
        if len(closes) <= periods or len(highs) <= periods or len(lows) <= periods:
            return 0.0
        true_ranges: List[float] = []
        plus_dm: List[float] = []
        minus_dm: List[float] = []
        start = max(1, len(closes) - periods)
        for index in range(start, len(closes)):
            high = float(highs[index] or 0.0)
            low = float(lows[index] or 0.0)
            previous_high = float(highs[index - 1] or 0.0)
            previous_low = float(lows[index - 1] or 0.0)
            previous_close = float(closes[index - 1] or 0.0)
            up_move = high - previous_high
            down_move = previous_low - low
            plus_dm.append(up_move if up_move > down_move and up_move > 0 else 0.0)
            minus_dm.append(down_move if down_move > up_move and down_move > 0 else 0.0)
            true_ranges.append(max(high - low, abs(high - previous_close), abs(low - previous_close)))
        tr_sum = sum(true_ranges)
        if tr_sum == 0:
            return 0.0
        plus_di = 100 * sum(plus_dm) / tr_sum
        minus_di = 100 * sum(minus_dm) / tr_sum
        denominator = plus_di + minus_di
        return round(100 * abs(plus_di - minus_di) / denominator, 2) if denominator else 0.0

    @staticmethod
    def _max_drawdown(values: List[float], periods: int = 20) -> float:
        sample = [float(item or 0.0) for item in (values[-periods:] if len(values) >= periods else values) if item is not None]
        peak = 0.0
        max_drawdown = 0.0
        for value in sample:
            peak = max(peak, value)
            if peak:
                max_drawdown = min(max_drawdown, ((value - peak) / peak) * 100)
        return round(max_drawdown, 2)

    @staticmethod
    def _rolling_correlation(left: List[float], right: List[float], periods: int = 20) -> float:
        if not left or not right:
            return 0.0
        count = min(len(left), len(right), max(2, periods))
        x_values = [float(item or 0.0) for item in left[-count:]]
        y_values = [float(item or 0.0) for item in right[-count:]]
        if len(x_values) < 2 or len(y_values) < 2:
            return 0.0
        x_mean = sum(x_values) / len(x_values)
        y_mean = sum(y_values) / len(y_values)
        numerator = sum((x_values[index] - x_mean) * (y_values[index] - y_mean) for index in range(len(x_values)))
        x_var = sum((item - x_mean) ** 2 for item in x_values)
        y_var = sum((item - y_mean) ** 2 for item in y_values)
        denominator = (x_var * y_var) ** 0.5
        return round(numerator / denominator, 4) if denominator else 0.0

    @staticmethod
    def _distance_percent(value: float, anchor: float) -> float:
        if not value or not anchor:
            return 100.0
        return round(abs((value - anchor) / anchor) * 100, 2)

    @staticmethod
    def _safe_factor_ratio(numerator: Any, denominator: Any) -> float:
        try:
            denominator_value = float(denominator or 0.0)
            if denominator_value == 0:
                return 0.0
            return float(numerator or 0.0) / denominator_value
        except (TypeError, ValueError, OverflowError):
            return 0.0

    @staticmethod
    def _finite_factor_value(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return 0.0
        if number != number or number in (float("inf"), float("-inf")):
            return 0.0
        number = max(-1_000_000_000.0, min(1_000_000_000.0, number))
        return round(number, 6)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError, OverflowError):
            return default
        if number != number or number in (float("inf"), float("-inf")):
            return default
        return number

    @classmethod
    def _save_decision(
        cls,
        cycle_id: str,
        user_id: int,
        account_id: Optional[int],
        decision: Dict[str, Any],
        status: str,
        source: str,
        order_id: Optional[str]
    ) -> Dict[str, Any]:
        DbUtil.execute_sql(
            """
            INSERT INTO quant_trade_decisions (
                cycle_id, user_id, account_id, symbol, market, side, quantity,
                price, confidence, status, reason, source, order_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cycle_id,
                user_id,
                account_id,
                decision.get('symbol'),
                decision.get('market'),
                decision.get('side'),
                int(decision.get('quantity') or 0),
                float(decision.get('price') or 0),
                int(decision.get('confidence') or 0),
                status,
                decision.get('reason'),
                source,
                order_id
            )
        )
        return {
            **decision,
            "status": status,
            "orderId": order_id
        }

    @classmethod
    def _execute_decision(cls, account_id: Optional[int], decision: Dict[str, Any], user_id: int = 1) -> Dict[str, Any]:
        if not account_id:
            return {"status": "failed", "message": "缺少账户"}
        return cls._submit_order_via_trade_service(account_id, decision, user_id=user_id)

    @classmethod
    def _has_recent_duplicate(cls, user_id: int, symbol: str, side: str) -> bool:
        row = DbUtil.query_one(
            """
            SELECT id
            FROM quant_trade_decisions
            WHERE user_id = %s
              AND symbol = %s
              AND side = %s
              AND created_at >= DATE_SUB(NOW(), INTERVAL 60 MINUTE)
            LIMIT 1
            """,
            (user_id, symbol, side)
        )
        return bool(row)

    @classmethod
    def _load_broker_today_orders(cls, account_id: Optional[int], user_id: int) -> tuple[List[Any], str]:
        if not account_id:
            return [], "缺少账户"
        return cls._load_trade_service_orders(account_id=account_id, user_id=user_id)

    @classmethod
    def _find_active_broker_order(cls, orders: List[Any], symbol: str, side: str) -> Optional[Dict[str, Any]]:
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        wanted_side = str(side or '').strip().upper()
        terminal_statuses = {
            'FILLED', 'CANCELED', 'CANCELLED', 'WITHDRAWN', 'REJECTED',
            'EXPIRED', 'FAILED', 'DELETED',
        }
        for order in orders or []:
            order_symbol = HistoricalMarketDataService.normalize_symbol(
                cls._read_order_attr(order, 'symbol', '')
            )
            if order_symbol != normalized_symbol:
                continue
            order_side = cls._normalize_order_side(cls._read_order_attr(order, 'side', cls._read_order_attr(order, 'action', '')))
            if order_side and wanted_side and order_side != wanted_side:
                continue
            status = cls._normalize_order_status(cls._read_order_attr(order, 'status', ''))
            standard_status = cls._standard_order_status(status)
            if status not in terminal_statuses and standard_status not in cls.TERMINAL_STANDARD_ORDER_STATUSES:
                return {
                    "orderId": cls._read_order_attr(order, 'order_id', cls._read_order_attr(order, 'orderId', '')),
                    "symbol": order_symbol,
                    "side": order_side or wanted_side,
                    "status": standard_status or status or 'active',
                    "brokerStatus": status,
                }
        return None

    @staticmethod
    def _read_order_attr(order: Any, name: str, default: Any = None) -> Any:
        if isinstance(order, dict):
            return order.get(name, default)
        return getattr(order, name, default)

    @staticmethod
    def _normalize_order_side(value: Any) -> str:
        text = str(value or '').strip().lower()
        if '.' in text:
            text = text.split('.')[-1]
        if text in {'buy', 'b', 'long'} or '买' in text:
            return 'BUY'
        if text in {'sell', 's', 'short'} or '卖' in text:
            return 'SELL'
        return text.upper()

    @staticmethod
    def _normalize_order_status(value: Any) -> str:
        text = str(value or '').strip()
        if '.' in text:
            text = text.split('.')[-1]
        return text.replace('-', '_').replace(' ', '_').upper()

    @classmethod
    def _standard_order_status(cls, value: Any) -> str:
        normalized = cls._normalize_order_status(value)
        return cls.STANDARD_ORDER_STATUS.get(normalized, normalized.lower() if normalized else "unknown")

    @classmethod
    def _is_terminal_order_status(cls, value: Any) -> bool:
        return cls._standard_order_status(value) in cls.TERMINAL_STANDARD_ORDER_STATUSES

    @staticmethod
    def _trade_service_base_url() -> str:
        return str(
            os.getenv("REF_TRADE_SERVICE_URL")
            or os.getenv("TRADE_SERVICE_URL")
            or f"http://127.0.0.1:{os.getenv('REF_TRADE_SERVICE_PORT', '8105')}"
        ).strip().rstrip("/")

    @classmethod
    def _trade_service_headers(cls, user_id: int) -> Dict[str, str]:
        try:
            from apps.runtime_shared.auth import generate_token
            token = generate_token(int(user_id), "quant-trading-service", "user")
            return {"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
        except Exception:
            return {"Content-Type": "application/json"}

    @classmethod
    def _request_trade_service(
        cls,
        *,
        method: str,
        path: str,
        user_id: int,
        payload: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: int = 30,
    ) -> Dict[str, Any]:
        base_url = cls._trade_service_base_url()
        if not base_url:
            raise RuntimeError("REF_TRADE_SERVICE_URL 未配置")
        query = f"?{urlparse.urlencode(params or {})}" if params else ""
        body = json.dumps(payload or {}).encode("utf-8") if payload is not None else None
        request = urlrequest.Request(
            f"{base_url}{path}{query}",
            data=body,
            headers=cls._trade_service_headers(user_id),
            method=method.upper(),
        )
        try:
            with urlrequest.urlopen(request, timeout=max(3, int(timeout or 30))) as response:
                response_body = response.read().decode("utf-8")
                return json.loads(response_body) if response_body else {}
        except urlerror.HTTPError as exc:
            response_body = exc.read().decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(response_body) if response_body else {}
            except ValueError:
                parsed = {}
            message = parsed.get("error") or parsed.get("message") or parsed.get("detail") or response_body or exc.reason
            raise RuntimeError(str(message)[:300]) from exc
        except Exception as exc:
            raise RuntimeError(f"trade-service 调用失败: {exc}") from exc

    @classmethod
    def _order_factor_inputs(cls, factor_inputs: Any) -> Dict[str, Any]:
        if not isinstance(factor_inputs, dict):
            return {}
        compact = {key: value for key, value in factor_inputs.items() if key != "factorSet"}
        factor_set = factor_inputs.get("factorSet")
        if isinstance(factor_set, dict):
            compact["factorSetVersion"] = factor_set.get("version") or factor_inputs.get("factorSetVersion")
            compact["factorCount"] = int(factor_set.get("count") or factor_inputs.get("factorCount") or 0)
            compact["factorFamilies"] = (
                factor_set.get("families")
                if isinstance(factor_set.get("families"), dict)
                else factor_inputs.get("factorFamilies") if isinstance(factor_inputs.get("factorFamilies"), dict)
                else {}
            )
        return compact

    @classmethod
    def _submit_order_via_trade_service(cls, account_id: int, decision: Dict[str, Any], user_id: int = 1) -> Dict[str, Any]:
        payload = {
            "account_id": int(account_id),
            "symbol": decision.get("symbol"),
            "action": decision.get("side") or "BUY",
            "quantity": int(decision.get("quantity") or 0),
            "price": float(decision.get("price") or 0),
            "order_type": "LIMIT",
            "time_in_force": "DAY",
            "source": decision.get("source") or "watchlist-quant-strategy",
            "strategy_context": {
                "confidence": int(decision.get("confidence") or 0),
                "reason": decision.get("reason") or "",
                "budget": decision.get("budget") or {},
                "scoreBreakdown": decision.get("scoreBreakdown") or {},
                "factorInputs": cls._order_factor_inputs(decision.get("factorInputs") or {}),
                "priceSource": decision.get("priceSource") or "unknown",
                "quoteUpdatedAt": decision.get("quoteUpdatedAt"),
            },
        }
        response = cls._request_trade_service(
            method="POST",
            path="/api/v1/trade/orders/submit",
            user_id=user_id,
            payload=payload,
        )
        data = response.get("data") if isinstance(response.get("data"), dict) else response
        if response and response.get("success") is False:
            return {"status": "failed", "message": response.get("error") or response.get("message") or "trade-service 拒绝下单"}
        order_id = data.get("orderId") or data.get("order_id") or response.get("order_id")
        status = cls._standard_order_status(data.get("status") or response.get("status") or "submitted")
        return {
            "status": "executed" if status in {"submitted", "accepted", "partially_filled", "filled"} else status,
            "order_id": order_id,
            "standardStatus": status,
            "boundary": "trade-service",
        }

    @classmethod
    def _load_trade_service_orders(cls, account_id: Optional[int], user_id: int) -> tuple[List[Any], str]:
        try:
            response = cls._request_trade_service(
                method="GET",
                path="/api/v1/trade/orders",
                user_id=user_id,
                params={
                    "account_id": int(account_id) if account_id else "",
                    "limit": 200,
                    "realtime": "true",
                },
                timeout=30,
            )
            data = response.get("data") if isinstance(response.get("data"), dict) else response
            orders = data.get("orders") or data.get("list") or response.get("orders") or []
            return list(orders or []), ""
        except Exception as exc:
            return [], str(exc)

    @staticmethod
    def _get_broker(account_id: Optional[int] = None, user_id: int = 1):
        manager = get_broker_manager()
        return manager.get_broker(account_id, user_id=user_id)

    @classmethod
    def _save_watchlist_strategy_run(
        cls,
        *,
        user_id: int,
        result: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        opportunities: List[Dict[str, Any]],
        skipped: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        try:
            run_id = DbUtil.execute_insert(
                """
                INSERT INTO watchlist_quant_strategy_runs (
                    cycle_id, user_id, source, strategy_profile, enabled, auto_execute,
                    executed, target_count, evaluated_count, opportunity_count,
                    auto_trade_json, position_control_json, skipped_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    source = VALUES(source),
                    strategy_profile = VALUES(strategy_profile),
                    enabled = VALUES(enabled),
                    auto_execute = VALUES(auto_execute),
                    executed = VALUES(executed),
                    target_count = VALUES(target_count),
                    evaluated_count = VALUES(evaluated_count),
                    opportunity_count = VALUES(opportunity_count),
                    auto_trade_json = VALUES(auto_trade_json),
                    position_control_json = VALUES(position_control_json),
                    skipped_json = VALUES(skipped_json)
                """,
                (
                    result.get('cycleId'),
                    user_id,
                    result.get('source'),
                    result.get('strategyProfile'),
                    1 if result.get('enabled') else 0,
                    1 if result.get('autoExecute') else 0,
                    1 if result.get('executed') else 0,
                    int(result.get('targetCount') or 0),
                    int(result.get('evaluatedCount') or 0),
                    int(result.get('opportunityCount') or 0),
                    cls._to_json(result.get('autoTrade')),
                    cls._to_json(result.get('positionControl')),
                    cls._to_json(skipped),
                )
            )
            if not run_id:
                row = DbUtil.fetch_one_primary(
                    """
                    SELECT id
                    FROM watchlist_quant_strategy_runs
                    WHERE user_id = %s AND cycle_id = %s
                    LIMIT 1
                    """,
                    (user_id, result.get('cycleId'))
                )
                run_id = int(row.get('id') or 0) if row else 0

            DbUtil.execute_sql(
                """
                DELETE FROM watchlist_quant_strategy_run_items
                WHERE user_id = %s AND cycle_id = %s
                """,
                (user_id, result.get('cycleId'))
            )
            item_by_symbol: Dict[str, Dict[str, Any]] = {}
            for item in candidates + opportunities:
                symbol = str(item.get('symbol') or '').upper()
                if symbol and symbol not in item_by_symbol:
                    item_by_symbol[symbol] = item
            for item in item_by_symbol.values():
                DbUtil.execute_sql(
                    """
                    INSERT INTO watchlist_quant_strategy_run_items (
                        run_id, cycle_id, user_id, symbol, name, market, side, status,
                        is_opportunity, price, confidence, risk_level, reason,
                        tags_json, metrics_json, score_json
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        run_id,
                        result.get('cycleId'),
                        user_id,
                        item.get('symbol'),
                        item.get('name'),
                        item.get('market'),
                        item.get('side') or 'HOLD',
                        item.get('status') or 'observed',
                        1 if item.get('isOpportunity') else 0,
                        float(item.get('price') or item.get('latestClose') or 0),
                        int(item.get('confidence') or 0),
                        item.get('riskLevel') or 'medium',
                        item.get('reason'),
                        cls._to_json(item.get('strategyTags') or []),
                        cls._to_json(item.get('metrics') or {}),
                        cls._to_json(item.get('scoreBreakdown') or {}),
                    )
                )
            return {"saved": True, "runId": run_id}
        except Exception as exc:
            return {"saved": False, "error": str(exc)}

    @classmethod
    def _start_us_open_ai_trade_run(
        cls,
        *,
        user_id: int,
        cycle_id: str,
        source: str,
        settings: Dict[str, Any],
    ) -> Dict[str, Any]:
        try:
            run_id = DbUtil.execute_insert(
                """
                INSERT INTO watchlist_us_open_ai_trade_runs (
                    cycle_id, user_id, source, status, settings_json, started_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    source = VALUES(source),
                    status = VALUES(status),
                    settings_json = VALUES(settings_json),
                    reason = NULL,
                    message = NULL,
                    error = NULL,
                    finished_at = NULL
                """,
                (
                    cycle_id,
                    user_id,
                    source,
                    "running",
                    cls._to_json(settings),
                )
            )
            return {"saved": True, "runId": run_id}
        except Exception as exc:
            return {"saved": False, "error": str(exc)}

    @classmethod
    def _finish_us_open_ai_trade_run(
        cls,
        *,
        user_id: int,
        result: Dict[str, Any],
        status: str = "completed",
        error: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            auto_trade = result.get("autoTrade") if isinstance(result.get("autoTrade"), dict) else {}
            skipped_items = result.get("skipped") if isinstance(result.get("skipped"), list) else []
            submitted_count = int(auto_trade.get("submittedCount") or len(auto_trade.get("signals") or []) or 0)
            DbUtil.execute_sql(
                """
                UPDATE watchlist_us_open_ai_trade_runs
                SET status = %s,
                    reason = %s,
                    message = %s,
                    target_count = %s,
                    evaluated_count = %s,
                    opportunity_count = %s,
                    submitted_count = %s,
                    skipped_count = %s,
                    executed = %s,
                    auto_trade_json = %s,
                    position_control_json = %s,
                    candidates_json = %s,
                    opportunities_json = %s,
                    skipped_json = %s,
                    error = %s,
                    finished_at = NOW()
                WHERE user_id = %s AND cycle_id = %s
                """,
                (
                    status,
                    result.get("reason"),
                    result.get("message"),
                    int(result.get("targetCount") or 0),
                    int(result.get("evaluatedCount") or 0),
                    int(result.get("opportunityCount") or 0),
                    submitted_count,
                    len(skipped_items),
                    1 if result.get("executed") else 0,
                    cls._to_json(auto_trade),
                    cls._to_json(result.get("positionControl") or {}),
                    cls._to_json(result.get("candidates") or []),
                    cls._to_json(result.get("opportunities") or []),
                    cls._to_json(skipped_items),
                    error,
                    user_id,
                    result.get("cycleId"),
                )
            )
            return {"saved": True}
        except Exception as exc:
            return {"saved": False, "error": str(exc)}

    @classmethod
    def _fail_us_open_ai_trade_run(
        cls,
        *,
        user_id: int,
        cycle_id: str,
        source: str,
        settings: Dict[str, Any],
        error: str,
    ) -> Dict[str, Any]:
        result = cls._build_us_open_trade_result(
            cycle_id=cycle_id,
            source=source,
            settings=settings,
            skipped=True,
            reason="failed",
            message="美股开盘 AI 自动交易扫描失败",
        )
        return cls._finish_us_open_ai_trade_run(
            user_id=user_id,
            result=result,
            status="failed",
            error=error,
        )

    @classmethod
    def _format_history_item(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        metrics = cls._compact_history_metrics(cls._parse_json(row.get('metrics_json'), {}))
        return {
            "symbol": row.get('symbol'),
            "name": row.get('name'),
            "market": row.get('market'),
            "side": row.get('side') or 'HOLD',
            "status": row.get('status') or 'observed',
            "isOpportunity": bool(row.get('is_opportunity')),
            "price": float(row.get('price') or 0),
            "confidence": int(row.get('confidence') or 0),
            "riskLevel": row.get('risk_level') or 'medium',
            "reason": row.get('reason') or '',
            "strategyTags": cls._parse_json(row.get('tags_json'), []),
            "metrics": metrics,
            "scoreBreakdown": cls._parse_json(row.get('score_json'), {}),
            "createdAt": cls._format_datetime(row.get('created_at')),
        }

    @classmethod
    def _compact_history_metrics(cls, metrics: Any) -> Dict[str, Any]:
        if not isinstance(metrics, dict):
            return {}
        compact = dict(metrics)
        factor_set = compact.pop("factorSet", None)
        if isinstance(factor_set, dict):
            compact["factorSetVersion"] = factor_set.get("version") or compact.get("factorSetVersion")
            compact["factorCount"] = int(cls._safe_float(factor_set.get("count") or compact.get("factorCount"), 0))
            compact["factorFamilies"] = (
                factor_set.get("families")
                if isinstance(factor_set.get("families"), dict)
                else compact.get("factorFamilies") if isinstance(compact.get("factorFamilies"), dict)
                else {}
            )
        return compact

    @classmethod
    def _format_us_open_ai_trade_run(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        auto_trade = cls._parse_json(row.get('auto_trade_json'), {})
        position_control = cls._parse_json(row.get('position_control_json'), {})
        settings = cls._parse_json(row.get('settings_json'), {})
        candidates = cls._parse_json(row.get('candidates_json'), [])
        opportunities = cls._parse_json(row.get('opportunities_json'), [])
        skipped = cls._parse_json(row.get('skipped_json'), [])
        return {
            "id": row.get('id'),
            "cycleId": row.get('cycle_id'),
            "source": row.get('source') or 'scheduler',
            "status": row.get('status') or 'running',
            "reason": row.get('reason') or '',
            "message": row.get('message') or '',
            "settings": settings if isinstance(settings, dict) else {},
            "targetCount": int(row.get('target_count') or 0),
            "evaluatedCount": int(row.get('evaluated_count') or 0),
            "opportunityCount": int(row.get('opportunity_count') or 0),
            "submittedCount": int(row.get('submitted_count') or 0),
            "skippedCount": int(row.get('skipped_count') or 0),
            "executed": bool(row.get('executed')),
            "autoTrade": auto_trade if isinstance(auto_trade, dict) else {},
            "positionControl": position_control if isinstance(position_control, dict) else {},
            "candidates": candidates if isinstance(candidates, list) else [],
            "opportunities": opportunities if isinstance(opportunities, list) else [],
            "skipped": skipped if isinstance(skipped, list) else [],
            "error": row.get('error') or '',
            "startedAt": cls._format_datetime(row.get('started_at')),
            "finishedAt": cls._format_datetime(row.get('finished_at')),
        }

    @staticmethod
    def _strategy_references() -> List[Dict[str, str]]:
        return [
            {
                "name": "QuantConnect Lean",
                "idea": "事件驱动、候选与执行分层、订单状态机",
                "license": "Apache-2.0",
            },
            {
                "name": "Microsoft Qlib",
                "idea": "多因子特征、因子解释和组合打分",
                "license": "MIT",
            },
            {
                "name": "vn.py",
                "idea": "交易网关、策略和风控分层",
                "license": "MIT",
            },
            {
                "name": "PyPortfolioOpt",
                "idea": "仓位预算与组合约束思想，当前仅做轻量预算器",
                "license": "MIT",
            },
            {
                "name": "Freqtrade/backtrader",
                "idea": "仅借鉴 dry-run、白名单和回测 UX，不复制 GPL 代码",
                "license": "GPL reference only",
            },
        ]

    @staticmethod
    def _opportunity_candidate_schema() -> Dict[str, Any]:
        return {
            "version": "watchlist-opportunity.v1",
            "required": ["symbol", "side", "price", "confidence", "riskLevel", "scoreBreakdown"],
            "boundary": "candidate-only; order intent must go through trade-service",
            "fields": {
                "symbol": "标准化市场标的，例如 AAPL.US",
                "side": "BUY、SELL 或 HOLD",
                "confidence": "0-100 多因子评分",
                "riskLevel": "low / medium / high",
                "scoreBreakdown": "trend / priceAction / momentum / breakout / volumeFlow / reversion / volatility / liquidity / aiTrend / riskPenalty",
                "metrics": "Qlib Alpha158/Alpha360 + TA-Lib/pandas-ta 风格因子输入快照；包含 1500+ OHLCV factorSet，候选保留完整值，历史列表和下单 factorInputs 仅透传摘要",
            },
        }

    @classmethod
    def _json_safe_value(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._json_safe_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe_value(item) for item in value]
        if isinstance(value, float):
            if value != value or value in (float("inf"), float("-inf")):
                return 0.0
        return value

    @staticmethod
    def _to_json(value: Any) -> str:
        safe_value = QuantTradingService._json_safe_value(value if value is not None else {})
        return json.dumps(safe_value, ensure_ascii=False, default=str, allow_nan=False)

    @staticmethod
    def _parse_json(value: Any, default: Any) -> Any:
        if value in (None, ''):
            return default
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _format_datetime(value: Any) -> Optional[str]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value.strftime('%Y-%m-%d %H:%M:%S')
        return str(value)

    @staticmethod
    def _cycle_id() -> str:
        return datetime.now().strftime('qt-%Y%m%d%H%M%S%f')
