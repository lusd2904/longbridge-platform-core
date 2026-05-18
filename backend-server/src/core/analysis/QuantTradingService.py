import json
from typing import Any, Dict, List, Optional

from config.Config import AppConfig
from core.analysis.MarketInsightService import MarketInsightService
from core.analysis.RecommendationService import RecommendationService
from core.analysis.StrategyMonitorService import StrategyMonitorService
from core.broker.BrokerInterface import get_broker_manager
from core.platform.PlatformAccessService import PlatformAccessService
from utils.DbUtil import DbUtil


class QuantTradingService:
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
        cls.ensure_schema()
        StrategyMonitorService.ensure_schema(user_id=user_id)
        access = PlatformAccessService.get_user_capabilities(user_id)

        if not access.get("hasBoundAccount"):
            raise ValueError('当前用户未绑定可用交易账户，无法执行 AI 量化交易')

        if not access.get("quantApiEnabled"):
            raise ValueError('当前用户未开通量化交易 API，请先在用户管理中开启后再使用')

        if not access.get("canUseQuantTrading"):
            raise ValueError('当前用户角色暂未授权量化交易能力')

        enabled = bool(AppConfig.get('AI_QUANT_TRADING_ENABLED', user_id=user_id, default=False))
        auto_execute = bool(AppConfig.get('AI_QUANT_AUTO_EXECUTE', user_id=user_id, default=False))
        should_execute = bool(execute if execute is not None else auto_execute) and enabled
        confidence_threshold = int(AppConfig.get('AI_QUANT_CONFIDENCE_THRESHOLD', user_id=user_id, default=72) or 72)
        max_buy_amount = float(AppConfig.get('AI_QUANT_MAX_BUY_AMOUNT', user_id=user_id, default=2000) or 2000)

        broker = cls._get_broker(account_id, user_id=user_id)
        if not broker:
            raise ValueError('当前用户未绑定可用交易账户，无法执行 AI 量化交易')

        if not broker.is_connected and not broker.connect():
            raise ConnectionError('券商连接失败')

        bound_account_id = int(getattr(broker, 'account_id', account_id or 0) or account_id or 0) or None
        account_info = broker.get_account_info()
        positions = broker.get_positions() or []
        holdings = {
            str(getattr(position, 'symbol', '')).upper(): position
            for position in positions
        }
        available_cash = float(getattr(account_info, 'cash', 0) or 0)
        cycle_id = cls._cycle_id()

        alerts_result = StrategyMonitorService.run_monitor(
            user_id=user_id,
            account_id=bound_account_id,
            source='quant-cycle'
        )
        latest_market = {
            item.get('market'): item
            for item in MarketInsightService.get_latest_snapshots(user_id=user_id)
        }
        recommendation = RecommendationService.refresh(
            profile='momentum',
            user_id=user_id,
            force=False
        )
        candidates = recommendation.get('items') or []

        decisions: List[Dict[str, Any]] = []
        sell_symbols = set()
        for alert in alerts_result.get('alerts') or []:
            symbol = str(alert.get('symbol') or '').upper()
            position = holdings.get(symbol)
            if not position or symbol in sell_symbols:
                continue

            quantity = int(float(getattr(position, 'quantity', 0) or 0))
            if quantity <= 0:
                continue

            action = str(alert.get('actionSuggested') or 'ALERT').upper()
            quantity = max(1, quantity // 2) if action == 'REDUCE' else quantity
            decisions.append({
                "symbol": symbol,
                "market": StrategyMonitorService.detect_market(symbol),
                "side": "SELL",
                "quantity": quantity,
                "price": float(getattr(position, 'market_price', 0) or 0),
                "confidence": 86 if alert.get('severity') == 'high' else 72,
                "reason": alert.get('message') or '监控规则触发减仓/卖出建议',
                "status": "queued"
            })
            sell_symbols.add(symbol)

        buy_count = 0
        for item in candidates:
            symbol = str(item.get('symbol') or '').upper()
            market = item.get('market') or StrategyMonitorService.detect_market(symbol)
            insight = latest_market.get(market, {})
            regime = insight.get('regime') or 'balanced'
            confidence = int(item.get('confidence') or 0)
            price = float(item.get('price') or 0)
            if (
                not enabled or
                symbol in holdings or
                symbol in sell_symbols or
                regime == 'risk_off' or
                confidence < confidence_threshold or
                price <= 0
            ):
                continue

            budget = min(max_buy_amount, max(0.0, available_cash * 0.08))
            quantity = int(budget / price) if budget > 0 else 0
            if quantity <= 0:
                continue

            decisions.append({
                "symbol": symbol,
                "market": market,
                "side": "BUY",
                "quantity": quantity,
                "price": price,
                "confidence": confidence,
                "reason": f"{market} 市场处于 {regime}，且 {symbol} 位于动量推荐前列",
                "status": "queued"
            })
            available_cash -= quantity * price
            buy_count += 1
            if buy_count >= 2:
                break

        persisted = []
        for decision in decisions:
            if cls._has_recent_duplicate(user_id, decision['symbol'], decision['side']):
                continue

            order_id = None
            status = 'queued'
            if should_execute:
                execution = cls._execute_decision(bound_account_id, decision, user_id=user_id)
                status = execution.get('status', 'failed')
                order_id = execution.get('order_id')

            persisted.append(cls._save_decision(
                cycle_id=cycle_id,
                user_id=user_id,
                account_id=bound_account_id,
                decision=decision,
                status=status,
                source=source,
                order_id=order_id
            ))

        return {
            "cycleId": cycle_id,
            "enabled": enabled,
            "autoExecute": auto_execute,
            "executed": should_execute,
            "marketSummary": latest_market,
            "alerts": alerts_result.get('alerts') or [],
            "recommendationSummary": recommendation.get('summary') or '',
            "signals": persisted
        }

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

        try:
            from api.trade_routes import get_trade_context_for_account
            from shared.longbridge import OrderSide, OrderType, TimeInForceType
        except Exception as exc:
            return {"status": "failed", "message": str(exc)}

        tc, _, config = get_trade_context_for_account(int(account_id), user_id=user_id)
        if not tc or not config:
            return {"status": "failed", "message": "交易上下文初始化失败或账户不属于当前用户"}

        symbol = decision.get('symbol')
        quantity = int(decision.get('quantity') or 0)
        price = float(decision.get('price') or 0)
        side = decision.get('side')
        broker_type = config.get('broker_type')

        if quantity <= 0 or price <= 0:
            return {"status": "failed", "message": "数量或价格无效"}

        try:
            if broker_type == 'longbridge':
                resp = tc.submit_order(
                    symbol=symbol,
                    order_type=OrderType.LO,
                    side=OrderSide.Buy if side == 'BUY' else OrderSide.Sell,
                    submitted_quantity=quantity,
                    submitted_price=price,
                    time_in_force=TimeInForceType.Day
                )
                return {"status": "executed", "order_id": getattr(resp, 'order_id', None)}

            if broker_type == 'tiger':
                resp = tc.place_order(
                    symbol=symbol,
                    action=side,
                    quantity=quantity,
                    order_type='LIMIT',
                    price=price,
                    time_in_force='DAY'
                )
                return {"status": "executed", "order_id": resp.get('order_id')}

            return {"status": "failed", "message": "不支持的券商类型"}
        except Exception as exc:
            return {"status": "failed", "message": str(exc)}

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

    @staticmethod
    def _get_broker(account_id: Optional[int] = None, user_id: int = 1):
        manager = get_broker_manager()
        return manager.get_broker(account_id, user_id=user_id)

    @staticmethod
    def _cycle_id() -> str:
        from datetime import datetime

        return datetime.now().strftime('qt-%Y%m%d%H%M%S')
