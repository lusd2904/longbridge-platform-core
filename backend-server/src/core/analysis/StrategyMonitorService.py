import hashlib
import json
import math
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest

from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.analysis.MarketInsightService import MarketInsightService
from core.broker.BrokerInterface import get_broker_manager
from utils.DbUtil import DbUtil


class StrategyMonitorService:
    _schema_ready = False
    _lock = threading.Lock()
    EXECUTION_MODE_MANUAL = "manual"
    EXECUTION_MODE_AUTO = "auto"
    SCHEDULE_PERIOD_MINUTE = "minute"
    SCHEDULE_PERIOD_HOUR = "hour"
    SCHEDULE_PERIOD_DAY = "day"
    SCHEDULE_PERIOD_WEEK = "week"
    SCHEDULE_PERIOD_SECONDS = {
        SCHEDULE_PERIOD_MINUTE: 60,
        SCHEDULE_PERIOD_HOUR: 3600,
        SCHEDULE_PERIOD_DAY: 86400,
        SCHEDULE_PERIOD_WEEK: 604800,
    }
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
    STRATEGY_TEMPLATES = [
        {
            "templateCode": "fixed_stop_loss",
            "name": "固定止损",
            "type": "stop_loss",
            "category": "risk",
            "featured": True,
            "summary": "浮亏达到固定阈值后止损退出。",
            "description": "适合大多数持仓风控，亏损达到阈值时提醒卖出或减仓。",
            "executionMode": "auto",
            "scheduleFrequency": 5,
            "schedulePeriod": "minute",
            "params": {"threshold": 6, "action": "SELL"},
            "tags": ["风控", "止损", "通用"],
        },
        {
            "templateCode": "tight_stop_loss",
            "name": "紧凑止损",
            "type": "stop_loss",
            "category": "risk",
            "featured": True,
            "summary": "更短容错区间，适合短线仓位。",
            "description": "适合高波动短线持仓，更强调纪律性，亏损超过 3% 即触发。",
            "executionMode": "auto",
            "scheduleFrequency": 5,
            "schedulePeriod": "minute",
            "params": {"threshold": 3, "action": "SELL"},
            "tags": ["风控", "短线", "纪律"],
        },
        {
            "templateCode": "wide_stop_loss",
            "name": "宽幅止损",
            "type": "stop_loss",
            "category": "risk",
            "featured": False,
            "summary": "适合趋势持仓，保留更大回撤空间。",
            "description": "适合波动较大的趋势仓位，给价格留更宽空间，避免过早洗出。",
            "executionMode": "auto",
            "scheduleFrequency": 15,
            "schedulePeriod": "minute",
            "params": {"threshold": 8, "action": "SELL"},
            "tags": ["风控", "趋势", "中线"],
        },
        {
            "templateCode": "atr_style_stop",
            "name": "波动自适应止损",
            "type": "stop_loss",
            "category": "risk",
            "featured": True,
            "summary": "以更宽的阈值模拟 ATR 风控思路。",
            "description": "当前版本以固定阈值承载 ATR 风格思路，适合波动较大的标的。",
            "executionMode": "auto",
            "scheduleFrequency": 15,
            "schedulePeriod": "minute",
            "params": {"threshold": 5, "action": "SELL", "style": "atr_like"},
            "tags": ["风控", "ATR", "波动"],
        },
        {
            "templateCode": "ladder_take_profit",
            "name": "分段止盈",
            "type": "take_profit",
            "category": "profit",
            "featured": True,
            "summary": "达到目标收益后提示分批落袋。",
            "description": "适合波段和趋势仓位，当收益达到目标值时提醒减仓锁利。",
            "executionMode": "auto",
            "scheduleFrequency": 10,
            "schedulePeriod": "minute",
            "params": {"threshold": 12, "action": "REDUCE"},
            "tags": ["止盈", "锁利", "波段"],
        },
        {
            "templateCode": "fast_take_profit",
            "name": "快进快出止盈",
            "type": "take_profit",
            "category": "profit",
            "featured": True,
            "summary": "更低止盈阈值，适合短线。",
            "description": "短线策略模板，盈利达到 8% 时优先考虑减仓止盈。",
            "executionMode": "auto",
            "scheduleFrequency": 5,
            "schedulePeriod": "minute",
            "params": {"threshold": 8, "action": "REDUCE"},
            "tags": ["止盈", "短线", "兑现"],
        },
        {
            "templateCode": "trend_take_profit",
            "name": "趋势持仓止盈",
            "type": "take_profit",
            "category": "profit",
            "featured": False,
            "summary": "更高收益目标，保留趋势延续空间。",
            "description": "适合中线趋势策略，盈利更充分后再提示分批退出。",
            "executionMode": "auto",
            "scheduleFrequency": 15,
            "schedulePeriod": "minute",
            "params": {"threshold": 18, "action": "REDUCE"},
            "tags": ["止盈", "趋势", "中线"],
        },
        {
            "templateCode": "overweight_trim",
            "name": "仓位过重调仓",
            "type": "overweight_trim",
            "category": "position",
            "featured": True,
            "summary": "单一持仓占比过高时提醒降集中度。",
            "description": "适合控制个股集中风险，单只标的仓位占比过高时减仓。",
            "executionMode": "manual",
            "scheduleFrequency": 1,
            "schedulePeriod": "day",
            "params": {"threshold": 35, "action": "REDUCE"},
            "tags": ["仓位", "集中度", "调仓"],
        },
        {
            "templateCode": "balanced_position_control",
            "name": "均衡仓位控制",
            "type": "overweight_trim",
            "category": "position",
            "featured": False,
            "summary": "更严格的仓位上限，适合分散配置。",
            "description": "适合组合投资者，将单一标的仓位控制在 25% 附近。",
            "executionMode": "auto",
            "scheduleFrequency": 30,
            "schedulePeriod": "minute",
            "params": {"threshold": 25, "action": "REDUCE"},
            "tags": ["仓位", "组合", "分散"],
        },
        {
            "templateCode": "market_guard",
            "name": "大盘转弱防守",
            "type": "market_guard",
            "category": "market",
            "featured": True,
            "summary": "市场转入 risk-off 时加强防守。",
            "description": "适合系统性风险控制，当市场进入防守态且持仓偏弱时提醒降低暴露。",
            "executionMode": "auto",
            "scheduleFrequency": 15,
            "schedulePeriod": "minute",
            "params": {"threshold": 0, "action": "SELL"},
            "tags": ["大盘", "防守", "系统性风险"],
        },
        {
            "templateCode": "slow_market_guard",
            "name": "低频市场防守",
            "type": "market_guard",
            "category": "market",
            "featured": False,
            "summary": "更低检查频率，适合中线账户。",
            "description": "用于中线组合的宏观风控，降低执行频率以减少干扰。",
            "executionMode": "auto",
            "scheduleFrequency": 1,
            "schedulePeriod": "hour",
            "params": {"threshold": 0, "action": "SELL"},
            "tags": ["大盘", "中线", "防守"],
        },
        {
            "templateCode": "manual_review",
            "name": "人工复核策略",
            "type": "custom",
            "category": "review",
            "featured": True,
            "summary": "保留手动执行入口，用于人工判断。",
            "description": "适合需要人工参与判断的规则，可先建立模板，再按需调整参数。",
            "executionMode": "manual",
            "scheduleFrequency": 1,
            "schedulePeriod": "day",
            "params": {"threshold": 0, "action": "ALERT"},
            "tags": ["人工", "复核", "自定义"],
        },
    ]

    DEFAULT_STRATEGIES = [
        {
            "name": "固定止损",
            "type": "stop_loss",
            "description": "当单只持仓浮亏达到阈值时触发减仓或退出提醒。",
            "params": {"threshold": 6, "action": "SELL"},
            "status": "active",
            "execution_mode": "auto",
            "schedule_frequency": 5,
            "schedule_period": "minute",
            "total_return": 8.6,
            "sharpe_ratio": 1.22,
            "max_drawdown": 5.4,
            "win_rate": 63.0
        },
        {
            "name": "分段止盈",
            "type": "take_profit",
            "description": "当持仓达到目标收益后，提醒分批锁定利润。",
            "params": {"threshold": 12, "action": "REDUCE"},
            "status": "active",
            "execution_mode": "auto",
            "schedule_frequency": 10,
            "schedule_period": "minute",
            "total_return": 14.2,
            "sharpe_ratio": 1.35,
            "max_drawdown": 7.1,
            "win_rate": 58.0
        },
        {
            "name": "仓位过重调仓",
            "type": "overweight_trim",
            "description": "单只标的仓位过重时提示降低集中度。",
            "params": {"threshold": 35, "action": "REDUCE"},
            "status": "stopped",
            "execution_mode": "manual",
            "schedule_frequency": 1,
            "schedule_period": "day",
            "total_return": 10.4,
            "sharpe_ratio": 1.04,
            "max_drawdown": 4.2,
            "win_rate": 71.0
        },
        {
            "name": "大盘转弱防守",
            "type": "market_guard",
            "description": "当大盘进入风险规避阶段时，自动加强对弱势持仓的防守。",
            "params": {"threshold": 0, "action": "SELL"},
            "status": "active",
            "execution_mode": "auto",
            "schedule_frequency": 15,
            "schedule_period": "minute",
            "total_return": 11.8,
            "sharpe_ratio": 1.41,
            "max_drawdown": 3.9,
            "win_rate": 66.0
        }
    ]

    @classmethod
    def ensure_schema(cls, user_id: int = 1):
        if cls._schema_ready:
            return

        with cls._lock:
            if cls._schema_ready:
                return

            DbUtil.execute_sql(
                """
                CREATE TABLE IF NOT EXISTS strategies (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL DEFAULT 1,
                    name VARCHAR(120) NOT NULL,
                    type VARCHAR(32) DEFAULT 'custom',
                    description TEXT,
                    params_json LONGTEXT,
                    status VARCHAR(20) DEFAULT 'stopped',
                    execution_mode VARCHAR(16) DEFAULT 'auto',
                    schedule_frequency INT DEFAULT 1,
                    schedule_period VARCHAR(16) DEFAULT 'day',
                    last_executed_at DATETIME DEFAULT NULL,
                    total_return DECIMAL(10, 2) DEFAULT 0,
                    sharpe_ratio DECIMAL(10, 2) DEFAULT 0,
                    max_drawdown DECIMAL(10, 2) DEFAULT 0,
                    win_rate DECIMAL(10, 2) DEFAULT 0,
                    trigger_count INT DEFAULT 0,
                    last_triggered_at DATETIME DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_strategy_user_status (user_id, status)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cls._ensure_strategy_schema_extensions()
            DbUtil.execute_sql(
                """
                CREATE TABLE IF NOT EXISTS backtest_results (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL DEFAULT 1,
                    strategy_id INT DEFAULT NULL,
                    name VARCHAR(140) NOT NULL,
                    strategy_name VARCHAR(120) DEFAULT NULL,
                    symbol VARCHAR(32) DEFAULT NULL,
                    start_date DATE DEFAULT NULL,
                    end_date DATE DEFAULT NULL,
                    final_pnl DECIMAL(14, 2) DEFAULT 0,
                    total_return DECIMAL(10, 2) DEFAULT 0,
                    annual_return DECIMAL(10, 2) DEFAULT 0,
                    sharpe_ratio DECIMAL(10, 2) DEFAULT 0,
                    max_drawdown DECIMAL(10, 2) DEFAULT 0,
                    win_rate DECIMAL(10, 2) DEFAULT 0,
                    trade_count INT DEFAULT 0,
                    status VARCHAR(20) DEFAULT 'completed',
                    performance_json LONGTEXT,
                    equity_curve_json LONGTEXT,
                    trades_json LONGTEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_backtest_user_created (user_id, created_at),
                    INDEX idx_backtest_strategy (strategy_id)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            DbUtil.execute_sql(
                """
                CREATE TABLE IF NOT EXISTS strategy_alerts (
                    id BIGINT AUTO_INCREMENT PRIMARY KEY,
                    user_id INT NOT NULL DEFAULT 1,
                    strategy_id INT DEFAULT NULL,
                    account_id INT DEFAULT NULL,
                    symbol VARCHAR(32) DEFAULT NULL,
                    market VARCHAR(10) DEFAULT NULL,
                    severity VARCHAR(20) DEFAULT 'medium',
                    action_suggested VARCHAR(32) DEFAULT 'ALERT',
                    message VARCHAR(255) DEFAULT NULL,
                    pnl_percent DECIMAL(10, 2) DEFAULT 0,
                    weight DECIMAL(10, 2) DEFAULT 0,
                    current_price DECIMAL(18, 4) DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_alert_user_created (user_id, created_at),
                    INDEX idx_alert_strategy_symbol (strategy_id, symbol)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            cls._schema_ready = True

        cls.seed_defaults(user_id=user_id)

    @classmethod
    def seed_defaults(cls, user_id: int = 1):
        existing = DbUtil.query_one("SELECT COUNT(1) FROM strategies WHERE user_id = %s", (user_id,))
        if existing and int(existing[0] or 0) > 0:
            return

        for item in cls.DEFAULT_STRATEGIES:
            DbUtil.execute_sql(
                """
                INSERT INTO strategies (
                    user_id, name, type, description, params_json, status,
                    execution_mode, schedule_frequency, schedule_period,
                    total_return, sharpe_ratio, max_drawdown, win_rate
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    item["name"],
                    item["type"],
                    item["description"],
                    json.dumps(item["params"], ensure_ascii=False),
                    item["status"],
                    item.get("execution_mode") or cls.EXECUTION_MODE_AUTO,
                    int(item.get("schedule_frequency") or 1),
                    item.get("schedule_period") or cls.SCHEDULE_PERIOD_DAY,
                    item["total_return"],
                    item["sharpe_ratio"],
                    item["max_drawdown"],
                    item["win_rate"]
                )
            )

    @classmethod
    def list_strategies(cls, user_id: int = 1) -> List[Dict[str, Any]]:
        cls.ensure_schema(user_id=user_id)
        rows = DbUtil.fetch_all(
            """
            SELECT id, name, type, description, params_json, status, execution_mode,
                   schedule_frequency, schedule_period, last_executed_at, total_return,
                   sharpe_ratio, max_drawdown, win_rate, trigger_count,
                   last_triggered_at, created_at
            FROM strategies
            WHERE user_id = %s
            ORDER BY status = 'active' DESC, id ASC
            """,
            (user_id,)
        ) or []
        return [cls._normalize_strategy(row) for row in rows]

    @classmethod
    def save_strategy(cls, user_id: int, payload: Dict[str, Any], strategy_id: Optional[int] = None) -> Dict[str, Any]:
        cls.ensure_schema(user_id=user_id)

        if strategy_id:
            current = DbUtil.fetch_one(
                """
                SELECT id, name, type, description, params_json, status, execution_mode,
                       schedule_frequency, schedule_period, last_executed_at, total_return,
                       sharpe_ratio, max_drawdown, win_rate, trigger_count,
                       last_triggered_at, created_at
                FROM strategies
                WHERE id = %s AND user_id = %s
                """,
                (strategy_id, user_id)
            )
            if not current:
                raise ValueError('策略不存在')
        else:
            current = {}

        name = str(payload.get('name', current.get('name') or '') or '').strip()
        strategy_type = str(payload.get('type', current.get('type') or 'custom') or 'custom').strip() or 'custom'
        description = str(payload.get('description', current.get('description') or '') or '').strip()
        raw_params = payload.get('params', cls._json_load(current.get('params_json')) or {})
        if isinstance(raw_params, list):
            params = {
                str(item.get('name') or f'param_{index}'): item.get('value')
                for index, item in enumerate(raw_params)
                if str(item.get('name') or '').strip() or item.get('value') not in (None, '')
            }
        elif isinstance(raw_params, dict):
            params = raw_params
        else:
            params = {}
        params_json = json.dumps(params, ensure_ascii=False)
        status = str(payload.get('status', current.get('status') or 'stopped') or 'stopped').strip() or 'stopped'
        execution_mode = cls._normalize_execution_mode(
            payload.get('executionMode', payload.get('execution_mode', current.get('execution_mode')))
        )
        schedule_frequency = cls._normalize_schedule_frequency(
            payload.get('scheduleFrequency', payload.get('schedule_frequency', current.get('schedule_frequency')))
        )
        schedule_period = cls._normalize_schedule_period(
            payload.get('schedulePeriod', payload.get('schedule_period', current.get('schedule_period')))
        )

        if not name:
            raise ValueError('策略名称不能为空')

        if strategy_id:
            DbUtil.execute_sql(
                """
                UPDATE strategies
                SET name = %s,
                    type = %s,
                    description = %s,
                    params_json = %s,
                    status = %s,
                    execution_mode = %s,
                    schedule_frequency = %s,
                    schedule_period = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
                """,
                (
                    name,
                    strategy_type,
                    description,
                    params_json,
                    status,
                    execution_mode,
                    schedule_frequency,
                    schedule_period,
                    strategy_id,
                    user_id,
                )
            )
            row = DbUtil.fetch_one(
                """
                SELECT id, name, type, description, params_json, status, execution_mode,
                       schedule_frequency, schedule_period, last_executed_at, total_return,
                       sharpe_ratio, max_drawdown, win_rate, trigger_count,
                       last_triggered_at, created_at
                FROM strategies
                WHERE id = %s AND user_id = %s
                """,
                (strategy_id, user_id)
            )
            return cls._normalize_strategy(row)

        DbUtil.execute_sql(
            """
            INSERT INTO strategies (
                user_id, name, type, description, params_json, status,
                execution_mode, schedule_frequency, schedule_period
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                user_id,
                name,
                strategy_type,
                description,
                params_json,
                status,
                execution_mode,
                schedule_frequency,
                schedule_period,
            )
        )
        row = DbUtil.fetch_one(
            """
            SELECT id, name, type, description, params_json, status, execution_mode,
                   schedule_frequency, schedule_period, last_executed_at, total_return,
                   sharpe_ratio, max_drawdown, win_rate, trigger_count,
                   last_triggered_at, created_at
            FROM strategies
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        )
        return cls._normalize_strategy(row)

    @classmethod
    def delete_strategy(cls, user_id: int, strategy_id: int):
        cls.ensure_schema(user_id=user_id)
        DbUtil.execute_sql("DELETE FROM strategy_alerts WHERE strategy_id = %s AND user_id = %s", (strategy_id, user_id))
        DbUtil.execute_sql("DELETE FROM strategies WHERE id = %s AND user_id = %s", (strategy_id, user_id))

    @classmethod
    def list_backtests(cls, user_id: int = 1) -> List[Dict[str, Any]]:
        cls.ensure_schema(user_id=user_id)
        rows = DbUtil.fetch_all(
            """
            SELECT id, strategy_id, name, strategy_name, symbol, start_date, end_date,
                   final_pnl, total_return, annual_return, sharpe_ratio, max_drawdown,
                   win_rate, trade_count, status, performance_json, equity_curve_json,
                   trades_json, created_at
            FROM backtest_results
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT 50
            """,
            (user_id,)
        ) or []
        return [cls._normalize_backtest(row) for row in rows]

    @classmethod
    def run_backtest(cls, user_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        cls.ensure_schema(user_id=user_id)

        strategy_id = payload.get('strategy_id')
        strategy = None
        if strategy_id:
            strategy = DbUtil.fetch_one(
                """
                SELECT id, name, type, description, params_json, status, execution_mode,
                       schedule_frequency, schedule_period, last_executed_at, total_return,
                       sharpe_ratio, max_drawdown, win_rate, trigger_count,
                       last_triggered_at, created_at
                FROM strategies
                WHERE id = %s AND user_id = %s
                """,
                (strategy_id, user_id)
            )

        strategy_name = (strategy or {}).get('name') or '策略回测'
        strategy_type = (strategy or {}).get('type') or 'custom'
        symbol = str(payload.get('symbol') or '').strip().upper()
        if not symbol:
            raise ValueError('symbol 不能为空')

        end_date = cls._parse_date(payload.get('end_date')) or datetime.now().date()
        start_date = cls._parse_date(payload.get('start_date')) or (end_date - timedelta(days=90))
        if start_date >= end_date:
            raise ValueError('开始日期必须早于结束日期')

        initial_capital = float(payload.get('initial_capital') or 100000)
        params = cls._json_load((strategy or {}).get('params_json')) or {}
        history_series = cls._load_backtest_series(
            symbol=symbol,
            user_id=user_id,
            start_date=start_date,
            end_date=end_date
        )
        if len(history_series) < 10:
            raise ValueError(f'{symbol} 历史行情不足，无法运行真实回测')

        simulation = cls._simulate_strategy(
            symbol=symbol,
            strategy_type=strategy_type,
            params=params,
            series=history_series,
            initial_capital=initial_capital
        )
        curve_dates = simulation['equityCurve']['dates']
        curve_values = simulation['equityCurve']['values']
        trades = simulation['trades']
        performance = simulation['performance']
        final_equity = float(curve_values[-1] if curve_values else initial_capital)
        final_pnl = round(final_equity - initial_capital, 2)
        total_return = float(performance.get('totalReturn') or 0)
        annual_return = float(performance.get('annualReturn') or 0)
        sharpe_ratio = float(performance.get('sharpeRatio') or 0)
        max_drawdown = float(performance.get('maxDrawdown') or 0)
        win_rate = float(performance.get('winRate') or 0)
        equity_curve = simulation['equityCurve']
        record_name = f"{strategy_name} · {symbol}"

        DbUtil.execute_sql(
            """
            INSERT INTO backtest_results (
                user_id, strategy_id, name, strategy_name, symbol, start_date, end_date,
                final_pnl, total_return, annual_return, sharpe_ratio, max_drawdown,
                win_rate, trade_count, status, performance_json, equity_curve_json, trades_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'completed', %s, %s, %s)
            """,
            (
                user_id,
                strategy_id,
                record_name,
                strategy_name,
                symbol,
                start_date,
                end_date,
                final_pnl,
                total_return,
                annual_return,
                sharpe_ratio,
                max_drawdown,
                win_rate,
                len(trades),
                json.dumps(performance, ensure_ascii=False),
                json.dumps(equity_curve, ensure_ascii=False),
                json.dumps(trades, ensure_ascii=False)
            )
        )

        row = DbUtil.fetch_one(
            """
            SELECT id, strategy_id, name, strategy_name, symbol, start_date, end_date,
                   final_pnl, total_return, annual_return, sharpe_ratio, max_drawdown,
                   win_rate, trade_count, status, performance_json, equity_curve_json,
                   trades_json, created_at
            FROM backtest_results
            WHERE user_id = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,)
        )
        return cls._normalize_backtest(row)

    @classmethod
    def get_monitor_summary(cls, user_id: int = 1, account_id: Optional[int] = None) -> Dict[str, Any]:
        cls.ensure_schema(user_id=user_id)
        strategies = cls.list_strategies(user_id=user_id)
        alerts = cls.get_alerts(user_id=user_id, limit=12)
        active_rules = [item for item in strategies if item.get('status') == 'active']
        auto_rules = [item for item in strategies if item.get('executionMode') == cls.EXECUTION_MODE_AUTO]
        manual_rules = [item for item in strategies if item.get('executionMode') == cls.EXECUTION_MODE_MANUAL]
        auto_active_rules = [item for item in active_rules if item.get('executionMode') == cls.EXECUTION_MODE_AUTO]
        manual_active_rules = [item for item in active_rules if item.get('executionMode') == cls.EXECUTION_MODE_MANUAL]

        position_count = 0
        try:
            manager = get_broker_manager()
            broker = manager.get_broker(account_id, user_id=user_id)
            if broker and (broker.is_connected or broker.connect()):
                position_count = len(broker.get_positions() or [])
        except Exception:
            position_count = 0

        job = DbUtil.fetch_one(
            """
            SELECT last_run_at, status, message
            FROM scheduled_jobs
            WHERE job_name = %s
            """,
            (f'position_monitor:user:{int(user_id)}',)
        )

        return {
            "overview": {
                "ruleCount": len(strategies),
                "activeRuleCount": len(active_rules),
                "autoRuleCount": len(auto_rules),
                "manualRuleCount": len(manual_rules),
                "autoActiveRuleCount": len(auto_active_rules),
                "manualActiveRuleCount": len(manual_active_rules),
                "alertCount": len(alerts),
                "highRiskCount": len([item for item in alerts if item.get('severity') == 'high']),
                "positionCount": position_count,
                "lastRunAt": job.get('last_run_at').strftime('%Y-%m-%d %H:%M:%S') if job and job.get('last_run_at') else None,
                "status": job.get('status') if job else 'idle',
                "message": job.get('message') if job else ''
            },
            "rules": strategies,
            "alerts": alerts
        }

    @classmethod
    def get_alerts(cls, user_id: int = 1, limit: int = 20) -> List[Dict[str, Any]]:
        cls.ensure_schema(user_id=user_id)
        rows = DbUtil.fetch_all(
            """
            SELECT sa.id, sa.strategy_id, s.name AS strategy_name, sa.account_id, sa.symbol, sa.market,
                   sa.severity, sa.action_suggested, sa.message, sa.pnl_percent,
                   sa.weight, sa.current_price, sa.created_at
            FROM strategy_alerts sa
            LEFT JOIN strategies s ON s.id = sa.strategy_id
            WHERE sa.user_id = %s
            ORDER BY sa.id DESC
            LIMIT %s
            """,
            (user_id, limit)
        ) or []

        alerts = []
        for row in rows:
            alerts.append({
                "id": row.get('id'),
                "strategyId": row.get('strategy_id'),
                "strategyName": row.get('strategy_name') or '监控规则',
                "accountId": row.get('account_id'),
                "symbol": row.get('symbol'),
                "market": row.get('market'),
                "severity": row.get('severity') or 'medium',
                "actionSuggested": row.get('action_suggested') or 'ALERT',
                "message": row.get('message') or '',
                "pnlPercent": float(row.get('pnl_percent') or 0),
                "weight": float(row.get('weight') or 0),
                "currentPrice": float(row.get('current_price') or 0),
                "createdAt": row.get('created_at').strftime('%Y-%m-%d %H:%M:%S') if row.get('created_at') else None
            })
        return alerts

    @classmethod
    def run_monitor(
        cls,
        user_id: int = 1,
        account_id: Optional[int] = None,
        source: str = 'manual',
        strategy_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        cls.ensure_schema(user_id=user_id)
        strategies = cls._select_monitor_strategies(
            cls.list_strategies(user_id=user_id),
            source=source,
        )
        if strategy_id is not None:
            strategy_id = int(strategy_id)
            strategies = [item for item in strategies if int(item.get('id') or 0) == strategy_id]
            if not strategies:
                raise ValueError('目标策略不存在、未启用，或当前不满足执行条件')
        if not strategies:
            return {
                "source": source,
                "accountId": account_id,
                "positionCount": 0,
                "alertCount": 0,
                "alerts": [],
                "strategyIds": []
            }

        manager = get_broker_manager()
        broker = manager.get_broker(account_id, user_id=user_id)
        if not broker:
            raise ValueError('未找到当前用户可用的券商账户')

        if not broker.is_connected and not broker.connect():
            raise ConnectionError('券商连接失败')

        bound_account_id = int(getattr(broker, 'account_id', account_id or 0) or account_id or 0) or None
        positions = broker.get_positions() or []
        evaluated_strategy_ids = [int(item['id']) for item in strategies if item.get('id') is not None]
        total_market_value = sum(float(getattr(item, 'market_value', 0) or 0) for item in positions)
        market_insights = {
            item.get('market'): item
            for item in MarketInsightService.get_latest_snapshots(user_id=user_id)
        }

        alerts = []
        should_auto_execute = source == 'scheduler'
        realtime_orders_cache: Optional[List[Any]] = None
        realtime_orders_error = ""
        for position in positions:
            symbol = getattr(position, 'symbol', '')
            current_price = float(getattr(position, 'market_price', 0) or 0)
            avg_price = float(getattr(position, 'average_cost', 0) or 0)
            market_value = float(getattr(position, 'market_value', current_price * float(getattr(position, 'quantity', 0) or 0)) or 0)
            pnl_percent = ((current_price - avg_price) / avg_price * 100) if avg_price > 0 else 0.0
            weight = (market_value / total_market_value * 100) if total_market_value > 0 else 0.0
            market = cls.detect_market(symbol)
            insight = market_insights.get(market, {})

            context = {
                "symbol": symbol,
                "market": market,
                "current_price": current_price,
                "pnl_percent": pnl_percent,
                "weight": weight,
                "market_regime": insight.get('regime') or 'balanced',
                "market_headline": insight.get('headline') or ''
            }

            for strategy in strategies:
                alert = cls._evaluate_strategy(strategy, context)
                if not alert:
                    continue

                duplicate = DbUtil.query_one(
                    """
                    SELECT id
                    FROM strategy_alerts
                    WHERE user_id = %s
                      AND strategy_id = %s
                      AND symbol = %s
                      AND created_at >= DATE_SUB(NOW(), INTERVAL 15 MINUTE)
                    LIMIT 1
                    """,
                    (user_id, strategy['id'], symbol)
                )
                if duplicate:
                    continue

                DbUtil.execute_sql(
                    """
                    INSERT INTO strategy_alerts (
                        user_id, strategy_id, account_id, symbol, market, severity,
                        action_suggested, message, pnl_percent, weight, current_price
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        strategy['id'],
                        bound_account_id,
                        symbol,
                        market,
                        alert['severity'],
                        alert['actionSuggested'],
                        alert['message'],
                        pnl_percent,
                        weight,
                        current_price
                    )
                )
                DbUtil.execute_sql(
                    """
                    UPDATE strategies
                    SET trigger_count = trigger_count + 1,
                        last_triggered_at = NOW(),
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s AND user_id = %s
                    """,
                    (strategy['id'], user_id)
                )
                execution = cls._build_execution_result(status="alert_only")
                if should_auto_execute and strategy.get("executionMode") == cls.EXECUTION_MODE_AUTO:
                    if realtime_orders_cache is None:
                        realtime_orders_cache, realtime_orders_error = cls._load_trade_service_orders(
                            account_id=bound_account_id,
                            user_id=user_id,
                        )
                    execution = cls._execute_strategy_alert(
                        strategy=strategy,
                        alert=alert,
                        context=context,
                        position=position,
                        account_id=bound_account_id,
                        user_id=user_id,
                        source=source,
                        realtime_orders=realtime_orders_cache,
                        realtime_orders_error=realtime_orders_error,
                    )
                    if execution.get("standardStatus") not in cls.TERMINAL_STANDARD_ORDER_STATUSES:
                        submitted_order = execution.get("order")
                        if submitted_order:
                            realtime_orders_cache = list(realtime_orders_cache or [])
                            realtime_orders_cache.append(submitted_order)

                alerts.append({
                    "strategyId": strategy['id'],
                    "strategyName": strategy['name'],
                    "symbol": symbol,
                    "market": market,
                    "severity": alert['severity'],
                    "actionSuggested": alert['actionSuggested'],
                    "message": alert['message'],
                    "pnlPercent": round(pnl_percent, 2),
                    "weight": round(weight, 2),
                    "currentPrice": round(current_price, 2),
                    "execution": execution,
                })

        cls._mark_strategies_executed(user_id=user_id, strategy_ids=evaluated_strategy_ids)

        return {
            "source": source,
            "accountId": bound_account_id,
            "positionCount": len(positions),
            "alertCount": len(alerts),
            "alerts": alerts,
            "strategyIds": evaluated_strategy_ids
        }

    @classmethod
    def _evaluate_strategy(cls, strategy: Dict[str, Any], context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        strategy_type = strategy.get('type')
        params = strategy.get('params') or {}
        threshold = abs(float(params.get('threshold', 0) or 0))
        action = str(params.get('action') or 'ALERT').upper()
        pnl_percent = float(context.get('pnl_percent') or 0)
        weight = float(context.get('weight') or 0)
        symbol = context.get('symbol')
        market_regime = context.get('market_regime') or 'balanced'

        if strategy_type == 'stop_loss' and pnl_percent <= -threshold:
            return {
                "severity": "high",
                "actionSuggested": action,
                "message": f"{symbol} 浮亏 {pnl_percent:.2f}% ，已达到止损阈值 {-threshold:.2f}%"
            }

        if strategy_type == 'take_profit' and pnl_percent >= threshold:
            return {
                "severity": "medium",
                "actionSuggested": action,
                "message": f"{symbol} 浮盈 {pnl_percent:.2f}% ，建议分批锁定利润"
            }

        if strategy_type == 'overweight_trim' and weight >= threshold:
            return {
                "severity": "medium",
                "actionSuggested": action,
                "message": f"{symbol} 仓位占比 {weight:.2f}% ，已超过阈值 {threshold:.2f}%"
            }

        if strategy_type == 'market_guard' and market_regime == 'risk_off' and pnl_percent <= 0:
            return {
                "severity": "high",
                "actionSuggested": action,
                "message": f"{symbol} 所属市场进入防守状态，且持仓表现偏弱，建议降低暴露"
            }

        return None

    @classmethod
    def _execute_strategy_alert(
        cls,
        *,
        strategy: Dict[str, Any],
        alert: Dict[str, Any],
        context: Dict[str, Any],
        position: Any,
        account_id: Optional[int],
        user_id: int,
        source: str,
        realtime_orders: Optional[List[Any]],
        realtime_orders_error: str = "",
    ) -> Dict[str, Any]:
        action = str((strategy.get("params") or {}).get("action") or "ALERT").strip().upper()
        if action == "ALERT":
            return cls._build_execution_result(status="alert_only")

        order_intent = cls._build_order_intent(
            strategy=strategy,
            alert=alert,
            context=context,
            position=position,
            account_id=account_id,
            source=source,
        )
        if not order_intent:
            return cls._build_execution_result(
                status="skipped",
                reason="当前持仓不足以生成自动委托",
                action=action,
            )

        if realtime_orders_error:
            return cls._build_execution_result(
                status="failed",
                reason=f"读取 trade-service 实时订单失败: {realtime_orders_error}",
                action=action,
            )

        active_order = cls._find_active_trade_service_order(
            realtime_orders or [],
            symbol=order_intent.get("symbol"),
            side=order_intent.get("action"),
        )
        if active_order:
            return cls._build_execution_result(
                status="skipped",
                reason="存在同标的同方向未完成委托，跳过自动执行",
                action=action,
                duplicateOrderId=active_order.get("orderId"),
                duplicateStatus=active_order.get("status"),
            )

        try:
            cls._assert_paper_trading_account(account_id=account_id, user_id=user_id)
            response = cls._submit_order_intent_via_trade_service(
                account_id=int(account_id or 0),
                user_id=user_id,
                order_intent=order_intent,
            )
        except Exception as exc:
            return cls._build_execution_result(
                status="failed",
                reason=str(exc),
                action=action,
                quantity=order_intent.get("quantity"),
            )

        return cls._build_execution_result(
            status=response.get("status") or "submitted",
            action=action,
            orderAction=order_intent.get("action"),
            quantity=order_intent.get("quantity"),
            orderId=response.get("order_id"),
            standardStatus=response.get("standardStatus"),
            boundary=response.get("boundary"),
            payload=order_intent,
            order={
                "symbol": order_intent.get("symbol"),
                "side": order_intent.get("action"),
                "status": response.get("standardStatus") or response.get("status"),
                "order_id": response.get("order_id"),
            },
        )

    @classmethod
    def _build_order_intent(
        cls,
        *,
        strategy: Dict[str, Any],
        alert: Dict[str, Any],
        context: Dict[str, Any],
        position: Any,
        account_id: Optional[int],
        source: str,
    ) -> Optional[Dict[str, Any]]:
        params = strategy.get("params") or {}
        action = str(params.get("action") or "ALERT").strip().upper()
        symbol = HistoricalMarketDataService.normalize_symbol(context.get("symbol"))
        price = float(context.get("current_price") or 0)
        if not symbol or price <= 0:
            return None

        quantity = cls._resolve_strategy_order_quantity(action=action, position=position)
        if quantity <= 0:
            return None
        order_action = "SELL" if action == "REDUCE" else action

        return {
            "account_id": int(account_id or 0),
            "symbol": symbol,
            "action": order_action,
            "quantity": quantity,
            "price": price,
            "order_type": "LIMIT",
            "time_in_force": "DAY",
            "source": f"strategy-monitor:{source}",
            "strategy_context": {
                "strategyId": strategy.get("id"),
                "strategyName": strategy.get("name"),
                "strategyType": strategy.get("type"),
                "market": context.get("market"),
                "pnlPercent": float(context.get("pnl_percent") or 0),
                "weight": float(context.get("weight") or 0),
                "message": alert.get("message") or "",
                "executionMode": strategy.get("executionMode"),
                "requestedAction": action,
            },
        }

    @classmethod
    def _resolve_strategy_order_quantity(cls, *, action: str, position: Any) -> int:
        position_qty = cls._position_quantity(position)
        if action == "SELL":
            return position_qty
        if action == "REDUCE":
            return max(1, int(math.ceil(position_qty / 2.0))) if position_qty > 0 else 0
        if action == "BUY":
            return 1
        return 0

    @staticmethod
    def _position_quantity(position: Any) -> int:
        candidates = (
            getattr(position, "available_quantity", None),
            getattr(position, "availableQuantity", None),
            getattr(position, "quantity", None),
            getattr(position, "qty", None),
        )
        for value in candidates:
            try:
                quantity = int(math.floor(float(value or 0)))
            except (TypeError, ValueError):
                quantity = 0
            if quantity > 0:
                return quantity
        return 0

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

    @classmethod
    def _submit_order_intent_via_trade_service(
        cls,
        *,
        account_id: int,
        user_id: int,
        order_intent: Dict[str, Any],
    ) -> Dict[str, Any]:
        if account_id <= 0:
            raise ValueError("未找到可用账户，无法自动执行策略")
        response = cls._request_trade_service(
            method="POST",
            path="/api/v1/trade/orders/submit",
            user_id=user_id,
            payload=order_intent,
        )
        data = response.get("data") if isinstance(response.get("data"), dict) else response
        if response and response.get("success") is False:
            raise RuntimeError(response.get("error") or response.get("message") or "trade-service 拒绝下单")
        order_id = data.get("orderId") or data.get("order_id") or response.get("order_id")
        standard_status = cls._standard_order_status(data.get("status") or response.get("status") or "submitted")
        return {
            "status": "executed" if standard_status in {"submitted", "accepted", "partially_filled", "filled"} else standard_status,
            "order_id": order_id,
            "standardStatus": standard_status,
            "boundary": "trade-service",
        }

    @classmethod
    def _assert_paper_trading_account(cls, account_id: Optional[int], user_id: int) -> Dict[str, Any]:
        account = cls._load_trade_service_account(account_id=account_id, user_id=user_id)
        if cls._is_paper_account(account):
            return account
        raise PermissionError("策略自动交易仅允许纸账户/模拟账户执行，当前账户未通过 paper 校验")

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

    @classmethod
    def _find_active_trade_service_order(cls, orders: List[Any], symbol: str, side: str) -> Optional[Dict[str, Any]]:
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        normalized_side = cls._normalize_order_side(side)
        for order in orders or []:
            order_symbol = HistoricalMarketDataService.normalize_symbol(cls._read_order_attr(order, "symbol", ""))
            order_side = cls._normalize_order_side(
                cls._read_order_attr(order, "side", cls._read_order_attr(order, "action", ""))
            )
            if order_symbol != normalized_symbol or order_side != normalized_side:
                continue
            status = cls._read_order_attr(order, "status", "")
            standard_status = cls._standard_order_status(status)
            if standard_status in cls.TERMINAL_STANDARD_ORDER_STATUSES:
                continue
            return {
                "orderId": cls._read_order_attr(order, "order_id", cls._read_order_attr(order, "orderId")),
                "status": standard_status or cls._normalize_order_status(status).lower(),
            }
        return None

    @staticmethod
    def _read_order_attr(order: Any, name: str, default: Any = None) -> Any:
        if isinstance(order, dict):
            return order.get(name, default)
        return getattr(order, name, default)

    @staticmethod
    def _normalize_order_side(value: Any) -> str:
        text = str(value or "").strip().lower()
        if "." in text:
            text = text.split(".")[-1]
        if text in {"buy", "b", "long"} or "买" in text:
            return "BUY"
        if text in {"sell", "s", "short"} or "卖" in text:
            return "SELL"
        return text.upper()

    @staticmethod
    def _normalize_order_status(value: Any) -> str:
        text = str(value or "").strip()
        if "." in text:
            text = text.split(".")[-1]
        return text.replace("-", "_").replace(" ", "_").upper()

    @classmethod
    def _standard_order_status(cls, value: Any) -> str:
        normalized = cls._normalize_order_status(value)
        return cls.STANDARD_ORDER_STATUS.get(normalized, normalized.lower() if normalized else "unknown")

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

            token = generate_token(int(user_id), "strategy-monitor-service", "user")
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

    @staticmethod
    def _build_execution_result(status: str, **kwargs: Any) -> Dict[str, Any]:
        return {"status": status, **kwargs}

    @classmethod
    def _normalize_strategy(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        params = row.get('params_json')
        try:
            params = json.loads(params) if params else {}
        except (TypeError, ValueError, json.JSONDecodeError):
            params = {}

        return {
            "id": row.get('id'),
            "name": row.get('name') or '策略',
            "type": row.get('type') or 'custom',
            "description": row.get('description') or '',
            "params": params,
            "status": row.get('status') or 'stopped',
            "executionMode": cls._normalize_execution_mode(row.get('execution_mode')),
            "scheduleFrequency": cls._normalize_schedule_frequency(row.get('schedule_frequency')),
            "schedulePeriod": cls._normalize_schedule_period(row.get('schedule_period')),
            "totalReturn": float(row.get('total_return') or 0),
            "sharpeRatio": float(row.get('sharpe_ratio') or 0),
            "maxDrawdown": float(row.get('max_drawdown') or 0),
            "winRate": float(row.get('win_rate') or 0),
            "triggerCount": int(row.get('trigger_count') or 0),
            "lastExecutedAt": row.get('last_executed_at').strftime('%Y-%m-%d %H:%M:%S') if row.get('last_executed_at') else None,
            "lastTriggeredAt": row.get('last_triggered_at').strftime('%Y-%m-%d %H:%M:%S') if row.get('last_triggered_at') else None,
            "createdAt": row.get('created_at').strftime('%Y-%m-%d %H:%M:%S') if row.get('created_at') else None
        }

    @classmethod
    def get_strategy_templates(cls) -> Dict[str, Any]:
        categories = {
            "risk": "风险控制",
            "profit": "止盈退出",
            "position": "仓位管理",
            "market": "市场联动",
            "review": "人工复核",
        }
        templates = []
        for item in cls.STRATEGY_TEMPLATES:
            templates.append(
                {
                    **item,
                    "categoryLabel": categories.get(item.get("category"), item.get("category") or "其他"),
                }
            )
        return {
            "templates": templates,
            "categories": [{"value": key, "label": label} for key, label in categories.items()],
            "featured": [item for item in templates if item.get("featured")],
        }

    @classmethod
    def _ensure_strategy_schema_extensions(cls) -> None:
        required_columns = {
            "execution_mode": """
                ALTER TABLE strategies
                ADD COLUMN execution_mode VARCHAR(16) DEFAULT 'auto' AFTER status
            """,
            "schedule_frequency": """
                ALTER TABLE strategies
                ADD COLUMN schedule_frequency INT DEFAULT 1 AFTER execution_mode
            """,
            "schedule_period": """
                ALTER TABLE strategies
                ADD COLUMN schedule_period VARCHAR(16) DEFAULT 'day' AFTER schedule_frequency
            """,
            "last_executed_at": """
                ALTER TABLE strategies
                ADD COLUMN last_executed_at DATETIME DEFAULT NULL AFTER schedule_period
            """,
        }
        for column_name, sql in required_columns.items():
            if cls._column_exists("strategies", column_name):
                continue
            DbUtil.execute_sql(sql)

    @staticmethod
    def _column_exists(table_name: str, column_name: str) -> bool:
        row = DbUtil.query_one(
            """
            SELECT COUNT(1)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            """,
            (table_name, column_name),
        )
        return bool(row and int(row[0] or 0) > 0)

    @classmethod
    def _normalize_execution_mode(cls, value: Any) -> str:
        normalized = str(value or cls.EXECUTION_MODE_AUTO).strip().lower()
        if normalized not in {cls.EXECUTION_MODE_MANUAL, cls.EXECUTION_MODE_AUTO}:
            return cls.EXECUTION_MODE_AUTO
        return normalized

    @classmethod
    def _normalize_schedule_frequency(cls, value: Any) -> int:
        try:
            return max(1, int(value or 1))
        except (TypeError, ValueError):
            return 1

    @classmethod
    def _normalize_schedule_period(cls, value: Any) -> str:
        normalized = str(value or cls.SCHEDULE_PERIOD_DAY).strip().lower()
        if normalized not in cls.SCHEDULE_PERIOD_SECONDS:
            return cls.SCHEDULE_PERIOD_DAY
        return normalized

    @classmethod
    def _select_monitor_strategies(cls, strategies: List[Dict[str, Any]], source: str) -> List[Dict[str, Any]]:
        selected = []
        for strategy in strategies:
            if strategy.get("status") != "active":
                continue
            if source == "scheduler":
                if strategy.get("executionMode") != cls.EXECUTION_MODE_AUTO:
                    continue
                if not cls._is_strategy_due(strategy):
                    continue
            selected.append(strategy)
        return selected

    @classmethod
    def _is_strategy_due(cls, strategy: Dict[str, Any]) -> bool:
        last_executed_at = strategy.get("lastExecutedAt")
        if not last_executed_at:
            return True
        try:
            last_run = datetime.strptime(str(last_executed_at), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return True
        frequency = cls._normalize_schedule_frequency(strategy.get("scheduleFrequency"))
        period = cls._normalize_schedule_period(strategy.get("schedulePeriod"))
        required_seconds = frequency * cls.SCHEDULE_PERIOD_SECONDS.get(period, 86400)
        return (datetime.now() - last_run).total_seconds() >= required_seconds

    @classmethod
    def _mark_strategies_executed(cls, user_id: int, strategy_ids: List[int]) -> None:
        unique_ids = sorted({int(item) for item in strategy_ids if item})
        if not unique_ids:
            return
        placeholders = ", ".join(["%s"] * len(unique_ids))
        DbUtil.execute_sql(
            f"""
            UPDATE strategies
            SET last_executed_at = NOW(),
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s
              AND id IN ({placeholders})
            """,
            tuple([user_id, *unique_ids]),
        )

    @classmethod
    def _normalize_backtest(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        performance = cls._json_load(row.get('performance_json')) or {}
        equity_curve = cls._json_load(row.get('equity_curve_json')) or {"dates": [], "values": []}
        trades = cls._json_load(row.get('trades_json')) or []

        return {
            "id": row.get('id'),
            "name": row.get('name') or row.get('strategy_name') or '回测',
            "strategyId": row.get('strategy_id'),
            "strategyName": row.get('strategy_name') or '策略',
            "symbol": row.get('symbol') or '',
            "startDate": row.get('start_date').strftime('%Y-%m-%d') if row.get('start_date') else None,
            "endDate": row.get('end_date').strftime('%Y-%m-%d') if row.get('end_date') else None,
            "finalPnl": float(row.get('final_pnl') or 0),
            "totalReturn": float(row.get('total_return') or 0),
            "status": row.get('status') or 'completed',
            "performance": {
                "totalReturn": float(performance.get('totalReturn') or row.get('total_return') or 0),
                "annualReturn": float(performance.get('annualReturn') or row.get('annual_return') or 0),
                "sharpeRatio": float(performance.get('sharpeRatio') or row.get('sharpe_ratio') or 0),
                "maxDrawdown": float(performance.get('maxDrawdown') or row.get('max_drawdown') or 0),
                "winRate": float(performance.get('winRate') or row.get('win_rate') or 0),
                "tradeCount": int(performance.get('tradeCount') or row.get('trade_count') or 0)
            },
            "equityCurve": {
                "dates": equity_curve.get('dates') or [],
                "values": equity_curve.get('values') or []
            },
            "trades": trades,
            "createdAt": row.get('created_at').strftime('%Y-%m-%d %H:%M:%S') if row.get('created_at') else None
        }

    @staticmethod
    def _json_load(value: Any) -> Any:
        if not value:
            return None
        if isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None

    @staticmethod
    def _parse_date(value: Any):
        if not value:
            return None
        if hasattr(value, 'date'):
            return value.date() if hasattr(value, 'hour') else value
        try:
            return datetime.strptime(str(value), '%Y-%m-%d').date()
        except ValueError:
            return None

    @staticmethod
    def detect_market(symbol: str) -> str:
        symbol = str(symbol or '').upper()
        if symbol.endswith('.HK'):
            return 'HK'
        if symbol.endswith('.SH') or symbol.endswith('.SZ'):
            return 'CN'
        return 'US'

    @classmethod
    def _load_backtest_series(cls, symbol: str, user_id: int, start_date, end_date) -> List[Dict[str, Any]]:
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        lookback_days = max((end_date - start_date).days + 90, 180)
        HistoricalMarketDataService.ensure_symbol_history(
            normalized_symbol,
            user_id=user_id,
            min_points=min(max(lookback_days, 180), 520),
            refresh=False
        )
        series = HistoricalMarketDataService._query_daily_series(normalized_symbol, min(max(lookback_days * 2, 240), 1500))
        filtered = []
        for item in series:
            trade_date = cls._parse_date(item.get('date'))
            if not trade_date:
                continue
            if start_date <= trade_date <= end_date:
                filtered.append(item)
        return filtered

    @staticmethod
    def _simulate_strategy(
        symbol: str,
        strategy_type: str,
        params: Dict[str, Any],
        series: List[Dict[str, Any]],
        initial_capital: float
    ) -> Dict[str, Any]:
        fee_rate = 0.001
        threshold = abs(float(params.get('threshold', 6) or 6))
        cash = float(initial_capital)
        shares = 0
        entry_price = 0.0
        partial_taken = False
        dates: List[str] = []
        values: List[float] = []
        trades: List[Dict[str, Any]] = []
        closes: List[float] = []

        def moving_average(window: int) -> float:
            if not closes:
                return 0.0
            points = closes[-window:]
            return sum(points) / len(points)

        for index, item in enumerate(series):
            price = float(item.get('close') or 0)
            if price <= 0:
                continue

            closes.append(price)
            sma5 = moving_average(5)
            sma20 = moving_average(20)
            should_buy = shares == 0 and index >= 4 and price >= sma5 and (len(closes) < 20 or price >= sma20)

            if should_buy:
                risk_budget = 0.95 if strategy_type != 'market_guard' else 0.72
                quantity = int((cash * risk_budget) / price)
                if quantity > 0:
                    cash -= quantity * price * (1 + fee_rate)
                    shares += quantity
                    entry_price = price
                    partial_taken = False
                    trades.append({
                        "date": item.get('date'),
                        "symbol": symbol,
                        "action": "buy",
                        "price": round(price, 2),
                        "quantity": quantity,
                        "pnl": 0.0
                    })

            pnl_percent = ((price - entry_price) / entry_price * 100) if entry_price > 0 else 0.0
            momentum_10 = ((price - closes[-10]) / closes[-10] * 100) if len(closes) >= 10 and closes[-10] else 0.0
            sell_quantity = 0
            if shares > 0:
                if strategy_type == 'stop_loss' and pnl_percent <= -threshold:
                    sell_quantity = shares
                elif strategy_type == 'take_profit' and pnl_percent >= threshold and not partial_taken:
                    sell_quantity = max(1, shares // 2)
                    partial_taken = True
                elif strategy_type == 'overweight_trim' and pnl_percent >= max(3.0, threshold / 2) and price < sma5:
                    sell_quantity = max(1, shares // 2)
                elif strategy_type == 'market_guard' and (price < sma20 and momentum_10 <= -4):
                    sell_quantity = shares if pnl_percent <= 0 else max(1, shares // 2)
                elif price < sma20 * 0.96:
                    sell_quantity = max(1, shares // 2)

            if sell_quantity > 0 and shares > 0:
                sell_quantity = min(sell_quantity, shares)
                cash += sell_quantity * price * (1 - fee_rate)
                realized_pnl = (price - entry_price) * sell_quantity
                shares -= sell_quantity
                trades.append({
                    "date": item.get('date'),
                    "symbol": symbol,
                    "action": "sell",
                    "price": round(price, 2),
                    "quantity": int(sell_quantity),
                    "pnl": round(realized_pnl, 2)
                })
                if shares == 0:
                    entry_price = 0.0
                    partial_taken = False

            equity = cash + shares * price
            dates.append(item.get('date'))
            values.append(round(equity, 2))

        if not values:
            values = [round(initial_capital, 2)]
            dates = [series[-1].get('date') if series else datetime.now().strftime('%Y-%m-%d')]

        total_return = ((values[-1] / initial_capital) - 1) * 100 if initial_capital else 0.0
        total_days = max(len(values), 2)
        annual_return = ((values[-1] / initial_capital) ** (252 / total_days) - 1) * 100 if initial_capital > 0 and values[-1] > 0 else 0.0

        returns = []
        for index in range(1, len(values)):
            prev = values[index - 1]
            current = values[index]
            returns.append((current - prev) / prev if prev else 0.0)

        avg_return = sum(returns) / len(returns) if returns else 0.0
        volatility = math.sqrt(sum((value - avg_return) ** 2 for value in returns) / len(returns)) if returns else 0.0
        sharpe_ratio = (avg_return / volatility) * math.sqrt(252) if volatility else avg_return * 18

        peak = values[0]
        max_drawdown = 0.0
        for value in values:
            peak = max(peak, value)
            if peak > 0:
                max_drawdown = min(max_drawdown, (value - peak) / peak)

        sell_trades = [item for item in trades if item.get('action') == 'sell']
        winning_trades = len([item for item in sell_trades if float(item.get('pnl') or 0) >= 0])
        win_rate = (winning_trades / len(sell_trades) * 100) if sell_trades else 0.0

        return {
            "performance": {
                "totalReturn": round(total_return, 2),
                "annualReturn": round(annual_return, 2),
                "sharpeRatio": round(sharpe_ratio, 2),
                "maxDrawdown": round(abs(max_drawdown) * 100, 2),
                "winRate": round(win_rate, 2),
                "tradeCount": len(trades)
            },
            "equityCurve": {
                "dates": dates,
                "values": values
            },
            "trades": trades
        }
