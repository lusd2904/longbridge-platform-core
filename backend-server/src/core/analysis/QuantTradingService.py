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
                    "inputs": ["latestClose", "ma20", "ma60", "ma120", "return20", "return60", "macdHist", "momentumScore"],
                    "source": "Qlib-style factor pipeline",
                },
                {
                    "key": "breakout",
                    "label": "突破因子",
                    "inputs": ["distanceHigh20", "volumeRatio20", "dayChangePercent"],
                    "source": "Qlib-style factor pipeline",
                },
                {
                    "key": "reversion",
                    "label": "回归因子",
                    "inputs": ["rsi14", "supportDistance", "return20"],
                    "source": "Qlib-style factor pipeline",
                },
                {
                    "key": "risk",
                    "label": "风险扣分",
                    "inputs": ["trendScanRisk", "volatility20", "atrPercent", "rsi14", "distanceHigh20"],
                    "source": "vn.py/Lean-style pre-trade gate",
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

        if not policy_settings["autoTradeEnabled"]:
            return cls._build_us_open_trade_result(
                cycle_id=cycle_id,
                source=source,
                settings=policy_settings,
                skipped=True,
                reason="auto-trade-disabled",
                message="美股开盘 AI 自动交易开关未开启",
            )

        if policy_settings["regularSessionOnly"] and not force and not cls._is_us_regular_session_now(now):
            return cls._build_us_open_trade_result(
                cycle_id=cycle_id,
                source=source,
                settings=policy_settings,
                skipped=True,
                reason="outside-us-regular-session",
                message="当前不在美股常规交易时段，已跳过自动交易",
            )

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

        if not opportunities:
            result = cls._build_us_open_trade_result(
                cycle_id=cycle_id,
                source=source,
                settings=policy_settings,
                skipped=False,
                reason="no-opportunities",
                message="自选股池本轮没有达到买入或卖出条件的标的",
                targets=targets,
                evaluations=evaluations,
                opportunities=[],
                skipped_items=skipped,
            )
            result["history"] = cls._save_watchlist_strategy_run(
                user_id=user_id,
                result=result,
                candidates=evaluations,
                opportunities=[],
                skipped=skipped,
            )
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
            auto_trade={"enabled": True, **execution},
        )
        result["history"] = cls._save_watchlist_strategy_run(
            user_id=user_id,
            result=result,
            candidates=evaluations,
            opportunities=opportunities,
            skipped=skipped,
        )
        return result

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

        runs = []
        for row in rows:
            items = DbUtil.fetch_all(
                """
                SELECT symbol, name, market, side, status, is_opportunity, price,
                       confidence, risk_level, reason, tags_json, metrics_json,
                       score_json, created_at
                FROM watchlist_quant_strategy_run_items
                WHERE user_id = %s AND cycle_id = %s
                ORDER BY is_opportunity DESC, confidence DESC, id ASC
                LIMIT 20
                """,
                (user_id, row.get('cycle_id'))
            ) or []
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
                "budgetRule": "target portfolio exposure with even remaining-slot allocation; US minimum 1 share",
            },
            "executionBoundary": {
                "owner": "trade-service",
                "mode": "paper-account-only-order-intent",
                "description": "美股开盘自动交易只生成受控订单意图，必须经 trade-service 纸账户边界后提交。",
            },
        }

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
        closes = [cls._safe_float(item.get('close')) for item in series]
        highs = [cls._safe_float(item.get('high') or item.get('close')) for item in series]
        lows = [cls._safe_float(item.get('low') or item.get('close')) for item in series]
        volumes = [cls._safe_float(item.get('volume')) for item in series]
        latest = series[-1] if series else {}
        previous_close = closes[-2] if len(closes) >= 2 else 0.0
        latest_close = closes[-1] if closes else 0.0
        ma20 = cls._moving_average(closes, 20)
        ma60 = cls._moving_average(closes, 60)
        ma120 = cls._moving_average(closes, 120)
        return20 = cls._period_return(closes, 20)
        return60 = cls._period_return(closes, 60)
        return120 = cls._period_return(closes, 120)
        rsi14 = cls._safe_float(snapshot.get('rsi'), cls._rsi(closes, 14)) or cls._rsi(closes, 14)
        volatility20 = cls._volatility(closes, 20)
        high20_previous = max(highs[-21:-1]) if len(highs) >= 21 else max(highs[:-1] or highs or [0.0])
        low20 = min(lows[-20:]) if lows else 0.0
        avg_volume20 = cls._moving_average(volumes[:-1], 20) if len(volumes) > 1 else 0.0
        volume_ratio20 = round(volumes[-1] / avg_volume20, 2) if volumes and avg_volume20 else 0.0
        distance_high20 = round(((latest_close - high20_previous) / high20_previous) * 100, 2) if latest_close and high20_previous else 0.0
        distance_low20 = round(((latest_close - low20) / low20) * 100, 2) if latest_close and low20 else 0.0
        day_change_percent = round(((latest_close - previous_close) / previous_close) * 100, 2) if latest_close and previous_close else 0.0
        atr = cls._safe_float(snapshot.get('atr'))
        atr_percent = round((atr / latest_close) * 100, 2) if atr and latest_close else 0.0
        support_price = cls._safe_float(snapshot.get('supportPrice'))
        boll_lower = cls._safe_float(snapshot.get('bollLower'))
        support_distance = cls._distance_percent(latest_close, support_price or boll_lower)
        trend_strength = cls._safe_float((trend_scan or {}).get('trendStrength'))
        technical_score = cls._safe_float((trend_scan or {}).get('technicalScore'))

        return {
            "tradeDate": latest.get('date') or snapshot.get('tradeDate'),
            "historyCount": len(series),
            "latestClose": round(latest_close, 4),
            "dayChangePercent": day_change_percent,
            "ma20": ma20,
            "ma60": ma60,
            "ma120": ma120,
            "return20": return20,
            "return60": return60,
            "return120": return120,
            "rsi14": round(rsi14, 2),
            "macdHist": cls._safe_float(snapshot.get('macdHist')),
            "roc": cls._safe_float(snapshot.get('roc')),
            "momentumScore": cls._safe_float(snapshot.get('momentumScore')),
            "volatility20": volatility20,
            "atrPercent": atr_percent,
            "volumeRatio20": volume_ratio20,
            "distanceHigh20": distance_high20,
            "distanceLow20": distance_low20,
            "supportDistance": support_distance,
            "trendStrength": trend_strength,
            "technicalScore": technical_score,
            "trendScanRisk": str((trend_scan or {}).get('riskLevel') or '').lower(),
            "trendScanDirection": str((trend_scan or {}).get('trendDirection') or '').lower(),
        }

    @classmethod
    def _score_watchlist_quant_metrics(cls, *, metrics: Dict[str, Any], strategy_profile: str) -> Dict[str, Any]:
        latest_close = metrics["latestClose"]
        ma20 = metrics["ma20"]
        ma60 = metrics["ma60"]
        ma120 = metrics["ma120"]
        rsi14 = metrics["rsi14"]
        tags: List[str] = []

        trend_score = 0.0
        if latest_close and ma20 and latest_close >= ma20:
            trend_score += 14
            tags.append("站上20日线")
        if ma20 and ma60 and ma20 >= ma60:
            trend_score += 14
            tags.append("20/60多头")
        if ma60 and ma120 and ma60 >= ma120:
            trend_score += 8
            tags.append("中期趋势顺")
        trend_score += max(-8, min(12, metrics["return20"] / 1.5))
        trend_score += max(-6, min(10, metrics["return60"] / 3.0))
        if metrics["macdHist"] > 0:
            trend_score += 5
            tags.append("MACD偏多")
        trend_score += max(-6, min(8, (metrics["momentumScore"] - 50) / 6)) if metrics["momentumScore"] else 0

        breakout_score = 0.0
        if metrics["distanceHigh20"] >= 0:
            breakout_score += 14
            tags.append("20日突破")
        elif metrics["distanceHigh20"] >= -2.0:
            breakout_score += 9
            tags.append("接近20日高点")
        if metrics["volumeRatio20"] >= 1.5:
            breakout_score += 8
            tags.append("明显放量")
        elif metrics["volumeRatio20"] >= 1.15:
            breakout_score += 5
            tags.append("温和放量")
        if metrics["return20"] > 0 and metrics["dayChangePercent"] > 0:
            breakout_score += 4

        reversion_score = 0.0
        if 28 <= rsi14 <= 45 and metrics["supportDistance"] <= 4.0:
            reversion_score += 12
            tags.append("支撑回升")
        if rsi14 < 35 and metrics["dayChangePercent"] > 0:
            reversion_score += 8
            tags.append("RSI低位反弹")
        if latest_close and ma20 and latest_close < ma20 and metrics["return20"] > -8:
            reversion_score += 4

        ai_score = 0.0
        if metrics["trendScanDirection"] == "up":
            ai_score += 6
        if metrics["trendStrength"]:
            ai_score += max(-4, min(6, (metrics["trendStrength"] - 50) / 8))
        if metrics["technicalScore"]:
            ai_score += max(-4, min(6, (metrics["technicalScore"] - 55) / 8))

        risk_penalty = 0.0
        risk_level = 'low'
        if metrics["trendScanRisk"] == 'high':
            risk_penalty += 16
            risk_level = 'high'
        elif metrics["trendScanRisk"] == 'medium':
            risk_penalty += 5
            risk_level = 'medium'
        if metrics["volatility20"] >= 5.2 or metrics["atrPercent"] >= 6.0:
            risk_penalty += 14
            risk_level = 'high'
        elif metrics["volatility20"] >= 3.4 or metrics["atrPercent"] >= 4.0:
            risk_penalty += 6
            if risk_level == 'low':
                risk_level = 'medium'
        if rsi14 >= 82:
            risk_penalty += 9
            if risk_level == 'low':
                risk_level = 'medium'
        if metrics["return20"] <= -12 or metrics["distanceHigh20"] <= -18:
            risk_penalty += 12
            risk_level = 'high'

        weights = {
            "balanced": (0.58, 0.30, 0.22),
            "momentum": (0.72, 0.32, 0.05),
            "breakout": (0.48, 0.52, 0.04),
            "reversion": (0.28, 0.08, 0.78),
        }.get(strategy_profile, (0.58, 0.30, 0.22))
        raw_total = (
            46
            + trend_score * weights[0]
            + breakout_score * weights[1]
            + reversion_score * weights[2]
            + ai_score
            - risk_penalty
        )
        total = round(max(0.0, min(100.0, raw_total)), 2)
        trend_direction = 'up' if trend_score >= 24 else 'down' if trend_score <= -4 else 'sideways'

        return {
            "total": total,
            "trend": round(trend_score, 2),
            "breakout": round(breakout_score, 2),
            "reversion": round(reversion_score, 2),
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

    @staticmethod
    def _moving_average(values: List[float], window: int) -> float:
        sample = values[-window:] if len(values) >= window else values
        return round(sum(sample) / len(sample), 4) if sample else 0.0

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
    def _distance_percent(value: float, anchor: float) -> float:
        if not value or not anchor:
            return 100.0
        return round(abs((value - anchor) / anchor) * 100, 2)

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

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
                "factorInputs": decision.get("factorInputs") or {},
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
    def _format_history_item(cls, row: Dict[str, Any]) -> Dict[str, Any]:
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
            "metrics": cls._parse_json(row.get('metrics_json'), {}),
            "scoreBreakdown": cls._parse_json(row.get('score_json'), {}),
            "createdAt": cls._format_datetime(row.get('created_at')),
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
                "scoreBreakdown": "trend / breakout / reversion / aiTrend / riskPenalty",
                "metrics": "Qlib 风格因子输入快照",
            },
        }

    @staticmethod
    def _to_json(value: Any) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False, default=str)

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
