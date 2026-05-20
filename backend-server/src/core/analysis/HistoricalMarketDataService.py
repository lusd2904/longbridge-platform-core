from __future__ import annotations

from collections import OrderedDict
from contextlib import contextmanager
from datetime import date, datetime, timedelta
import logging
import os
import requests
import time
from typing import Any, Dict, Iterable, List, Optional

from config.Config import AppConfig
from core.analysis.MarketInsightService import MarketInsightService
from core.broker.BrokerInterface import get_broker_manager
from shared.longbridge import (
    AdjustType,
    Period,
    QuoteContext,
    build_quote_context,
)
from utils.DbUtil import DbUtil

logger = logging.getLogger(__name__)
LONGBRIDGE_AVAILABLE = QuoteContext is not None

try:
    import akshare as ak
    AKSHARE_AVAILABLE = True
except Exception:
    ak = None
    AKSHARE_AVAILABLE = False

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except Exception:
    yf = None
    YFINANCE_AVAILABLE = False


class HistoricalMarketDataService:
    TABLE_NAME = 'market_price_history_daily'
    SUPPORTED_TIMEFRAMES = {'daily', 'weekly', 'monthly', 'quarterly', 'yearly'}
    _BACKFILL_STATUS_CACHE: Dict[str, Any] = {"expires_at": 0.0, "payload": None}
    _BACKFILL_STATUS_TTL_SECONDS = 30
    _BACKFILL_STATUS_SCHEMA_READY = False

    @classmethod
    def _empty_history_payload(cls, symbol: str, timeframe: str = 'daily') -> Dict[str, object]:
        normalized_symbol = cls.normalize_symbol(symbol)
        safe_timeframe = str(timeframe or 'daily').strip().lower()
        return {
            "symbol": normalized_symbol,
            "market": cls.detect_market(normalized_symbol),
            "timeframe": safe_timeframe,
            "items": [],
            "summary": {
                "count": 0,
                "latestDate": None,
                "firstDate": None,
                "latestClose": 0,
                "periodReturn": 0
            }
        }

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(32) NOT NULL,
                market VARCHAR(10) NOT NULL,
                trade_date DATE NOT NULL,
                open_price DECIMAL(18, 4) DEFAULT 0,
                high_price DECIMAL(18, 4) DEFAULT 0,
                low_price DECIMAL(18, 4) DEFAULT 0,
                close_price DECIMAL(18, 4) DEFAULT 0,
                volume BIGINT DEFAULT 0,
                turnover DECIMAL(20, 4) DEFAULT 0,
                source VARCHAR(32) DEFAULT 'skshare',
                synced_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_symbol_trade_date (symbol, trade_date),
                INDEX idx_symbol_date (symbol, trade_date),
                INDEX idx_market_date (market, trade_date)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def get_history(
        cls,
        symbol: str,
        timeframe: str = 'daily',
        limit: int = 180,
        user_id: int = 1,
        refresh: bool = False
    ) -> Dict[str, object]:
        cls.ensure_schema()
        normalized_symbol = cls.normalize_symbol(symbol)
        safe_limit = min(max(int(limit or 180), 20), 500)
        safe_timeframe = str(timeframe or 'daily').strip().lower()
        if safe_timeframe not in cls.SUPPORTED_TIMEFRAMES:
            raise ValueError('timeframe 仅支持 daily / weekly / monthly / quarterly / yearly')

        try:
            cls.ensure_symbol_history(normalized_symbol, user_id=user_id, min_points=safe_limit, refresh=refresh)
        except Exception:
            pass
        series = cls._query_daily_series(normalized_symbol, safe_limit * 6)
        if not series:
            payload = cls._empty_history_payload(normalized_symbol, safe_timeframe)
            payload["warning"] = f'{normalized_symbol} 暂无历史行情数据'
            return payload

        if safe_timeframe == 'daily':
            items = cls._attach_change_metrics(series)
        else:
            items = cls._attach_change_metrics(cls._aggregate_series(series, safe_timeframe))

        sliced_items = items[-safe_limit:]
        closes = [item['close'] for item in sliced_items if item.get('close') is not None]

        return {
            "symbol": normalized_symbol,
            "market": cls.detect_market(normalized_symbol),
            "timeframe": safe_timeframe,
            "items": sliced_items,
            "summary": {
                "count": len(sliced_items),
                "latestDate": sliced_items[-1]['date'] if sliced_items else None,
                "firstDate": sliced_items[0]['date'] if sliced_items else None,
                "latestClose": closes[-1] if closes else 0,
                "periodReturn": round(((closes[-1] - closes[0]) / closes[0] * 100), 2) if len(closes) >= 2 and closes[0] else 0
            }
        }

    @classmethod
    def get_compare_history(
        cls,
        symbols: Iterable[str],
        timeframe: str = 'daily',
        limit: int = 180,
        user_id: int = 1,
        refresh: bool = False
    ) -> Dict[str, object]:
        from core.analysis.IndicatorSnapshotService import IndicatorSnapshotService

        safe_timeframe = str(timeframe or 'daily').strip().lower()
        if safe_timeframe not in cls.SUPPORTED_TIMEFRAMES:
            raise ValueError('timeframe 仅支持 daily / weekly / monthly / quarterly / yearly')

        normalized_symbols: List[str] = []
        for raw_symbol in symbols or []:
            normalized_symbol = cls.normalize_symbol(raw_symbol)
            if not normalized_symbol or normalized_symbol in normalized_symbols:
                continue
            normalized_symbols.append(normalized_symbol)
            if len(normalized_symbols) >= 6:
                break

        if not normalized_symbols:
            raise ValueError('至少需要一个有效标的')

        series_payload = []
        comparison_payload = []
        snapshots = []

        for symbol in normalized_symbols:
            history = cls.get_history(
                symbol=symbol,
                timeframe=safe_timeframe,
                limit=limit,
                user_id=user_id,
                refresh=refresh
            )
            snapshot = IndicatorSnapshotService.get_snapshot(symbol, timeframe=safe_timeframe, user_id=user_id)
            fundamentals = snapshot.get('fundamentals') or IndicatorSnapshotService._load_fundamentals(symbol)
            display_name = fundamentals.get('name') or symbol
            items = history.get('items') or []
            first_close = float(items[0].get('close') or 0) if items else 0

            series_payload.append({
                **history,
                "name": display_name,
                "snapshot": snapshot,
                "fundamentals": fundamentals
            })
            comparison_payload.append({
                "symbol": symbol,
                "name": display_name,
                "market": history.get('market'),
                "periodReturn": history.get('summary', {}).get('periodReturn', 0),
                "latestClose": history.get('summary', {}).get('latestClose', 0),
                "series": [
                    {
                        "date": item.get('date'),
                        "value": round(((float(item.get('close') or 0) - first_close) / first_close * 100), 2) if first_close else 0
                    }
                    for item in items
                ]
            })
            snapshots.append({
                "symbol": symbol,
                "name": display_name,
                "market": history.get('market'),
                "snapshot": snapshot,
                "fundamentals": fundamentals
            })

        return {
            "timeframe": safe_timeframe,
            "limit": min(max(int(limit or 180), 20), 500),
            "primarySymbol": normalized_symbols[0],
            "symbols": normalized_symbols,
            "series": series_payload,
            "comparison": comparison_payload,
            "snapshots": snapshots
        }

    @classmethod
    def get_backfill_status(cls) -> Dict[str, object]:
        now = time.time()
        cached_payload = cls._BACKFILL_STATUS_CACHE.get("payload")
        if cached_payload and now < float(cls._BACKFILL_STATUS_CACHE.get("expires_at") or 0):
            return dict(cached_payload)

        cls._ensure_backfill_status_schema()
        from core.platform.SystemTaskService import SystemTaskService

        universe_row = DbUtil.fetch_one(
            """
            SELECT
              (
                COALESCE((SELECT COUNT(1) FROM large_cap_stocks WHERE is_active = 1), 0) +
                COALESCE((SELECT COUNT(1) FROM us_etf WHERE is_active = 1), 0) +
                COALESCE((SELECT COUNT(1) FROM cn_stocks WHERE is_active = 1), 0) +
                COALESCE((SELECT COUNT(1) FROM cn_etf WHERE is_active = 1), 0) +
                COALESCE((SELECT COUNT(1) FROM hk_stocks WHERE is_active = 1), 0) +
                COALESCE((SELECT COUNT(1) FROM hk_etf WHERE is_active = 1), 0)
              ) AS total_universe_symbols
            """
        ) or {}
        total_rows = cls._estimate_history_total_rows()
        history_row = DbUtil.fetch_one(
            f"""
            SELECT COUNT(DISTINCT symbol) AS synced_symbols,
                   MAX(trade_date) AS latest_trade_date
            FROM {cls.TABLE_NAME}
            FORCE INDEX (uniq_symbol_trade_date)
            """
        ) or {}
        market_rows = DbUtil.fetch_all(
            f"""
            SELECT market, COUNT(1) AS row_count
            FROM {cls.TABLE_NAME}
            FORCE INDEX (idx_market_date)
            GROUP BY market
            """
        ) or []
        task_status = DbUtil.fetch_one(
            """
            SELECT job_name, last_run_date, last_run_at, status, message
            FROM scheduled_jobs
            WHERE job_name = %s
            LIMIT 1
            """,
            ('market_history_universe_backfill',)
        ) or {}
        policy = SystemTaskService.get_policy('market_history_universe_backfill')

        total_universe_symbols = int(universe_row.get('total_universe_symbols') or 0)
        synced_symbols = int(history_row.get('synced_symbols') or 0)
        coverage_rate = round((synced_symbols / total_universe_symbols * 100), 2) if total_universe_symbols else 0.0
        market_coverage = {
            str(row.get('market') or 'ALL'): int(row.get('row_count') or 0)
            for row in market_rows
        }

        latest_trade_date = history_row.get('latest_trade_date')
        last_run_date = task_status.get('last_run_date')
        last_run_at = task_status.get('last_run_at')
        settings = policy.get('settings') or {}
        task_state = str(task_status.get('status') or 'idle').strip().lower() or 'idle'
        progress = cls._build_backfill_progress_payload(
            settings=settings,
            task_state=task_state,
            interval_seconds=int(policy.get('intervalSeconds') or 0),
            batch_size=int(policy.get('batchSize') or 0),
            last_run_at=last_run_at.strftime('%Y-%m-%d %H:%M:%S') if last_run_at else None,
        )

        payload = {
            "totalUniverseSymbols": total_universe_symbols,
            "syncedSymbols": synced_symbols,
            "coverageRate": coverage_rate,
            "totalRows": total_rows,
            "latestTradeDate": latest_trade_date.strftime('%Y-%m-%d') if latest_trade_date else None,
            "marketCoverage": market_coverage,
            "marketCoverageMode": "history_rows",
            "task": {
                "taskKey": 'market_history_universe_backfill',
                "enabled": bool(policy.get('enabled')),
                "intervalSeconds": int(policy.get('intervalSeconds') or 0),
                "batchSize": int(policy.get('batchSize') or 0),
                "maxRequestsPerMinute": int(policy.get('maxRequestsPerMinute') or 0),
                "backfillStartDate": str(
                    settings.get('startDate')
                    or AppConfig.get('HISTORICAL_BACKFILL_START_DATE', default='2020-01-01')
                    or '2020-01-01'
                ),
                "settings": settings,
                "progress": progress,
                "status": task_state,
                "message": task_status.get('message') or '',
                "lastRunDate": last_run_date.strftime('%Y-%m-%d') if last_run_date else None,
                "lastRunAt": last_run_at.strftime('%Y-%m-%d %H:%M:%S') if last_run_at else None
            }
        }
        cls._BACKFILL_STATUS_CACHE = {
            "expires_at": now + cls._BACKFILL_STATUS_TTL_SECONDS,
            "payload": dict(payload),
        }
        return payload

    @classmethod
    def clear_backfill_status_cache(cls) -> None:
        cls._BACKFILL_STATUS_CACHE = {"expires_at": 0.0, "payload": None}

    @classmethod
    def _build_backfill_progress_payload(
        cls,
        *,
        settings: Dict[str, Any],
        task_state: str,
        interval_seconds: int,
        batch_size: int,
        last_run_at: Optional[str],
    ) -> Dict[str, object]:
        def safe_int(value, fallback=0):
            try:
                return int(value)
            except (TypeError, ValueError):
                return fallback

        def string_list(value, limit=12):
            if not isinstance(value, list):
                return []
            items = []
            for item in value:
                text = str(item or '').strip().upper()
                if text:
                    items.append(text)
                if len(items) >= limit:
                    break
            return items

        def failure_list(value, limit=12):
            if not isinstance(value, list):
                return []
            failures = []
            for item in value:
                if isinstance(item, dict):
                    symbol = str(item.get('symbol') or '').strip().upper()
                    error = str(item.get('error') or item.get('message') or '').strip()
                else:
                    symbol = str(item or '').strip().upper()
                    error = ''
                if symbol or error:
                    failures.append({"symbol": symbol, "error": error[:180]})
                if len(failures) >= limit:
                    break
            return failures

        current_batch = string_list(settings.get('currentBatchSymbols'), limit=max(1, batch_size or 12))
        processed_in_run = string_list(settings.get('processedInRun'), limit=12)
        failed_in_run = failure_list(settings.get('failedInRun'), limit=12)
        last_processed = string_list(settings.get('lastProcessedSymbols'), limit=12)
        last_failures = failure_list(settings.get('lastFailures'), limit=12)
        current_symbol = str(settings.get('currentSymbol') or '').strip().upper()
        cursor = safe_int(settings.get('cursor'), 0)
        last_next_cursor = safe_int(settings.get('lastNextCursor'), cursor)

        return {
            "isRunning": task_state == 'running',
            "cursor": cursor,
            "nextCursor": last_next_cursor,
            "batchSize": batch_size,
            "intervalSeconds": interval_seconds,
            "currentSymbol": current_symbol,
            "currentBatchSymbols": current_batch,
            "processedInRun": processed_in_run,
            "failedInRun": failed_in_run,
            "lastProcessedSymbols": last_processed,
            "lastFailures": last_failures,
            "lastFailedCount": safe_int(settings.get('lastFailedCount'), len(last_failures)),
            "lastRunProcessedCount": safe_int(settings.get('lastRunProcessedCount'), len(last_processed)),
            "runningStartedAt": settings.get('runningStartedAt') or None,
            "lastRunAt": settings.get('lastRunAt') or last_run_at,
        }

    @classmethod
    def _ensure_backfill_status_schema(cls) -> None:
        if cls._BACKFILL_STATUS_SCHEMA_READY:
            return

        from core.platform.SystemTaskService import SystemTaskService

        cls.ensure_schema()
        SystemTaskService.ensure_schema()
        DbUtil.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                job_name VARCHAR(80) NOT NULL PRIMARY KEY,
                last_run_date DATE DEFAULT NULL,
                last_run_at DATETIME DEFAULT NULL,
                status VARCHAR(32) DEFAULT 'idle',
                message VARCHAR(255) DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cls._BACKFILL_STATUS_SCHEMA_READY = True

    @classmethod
    def _estimate_history_total_rows(cls) -> int:
        table_stats = DbUtil.fetch_one(
            """
            SELECT table_rows
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = %s
            LIMIT 1
            """,
            (cls.TABLE_NAME,)
        ) or {}
        estimated_rows = int(table_stats.get('table_rows') or 0)
        if estimated_rows > 0:
            return estimated_rows

        row = DbUtil.fetch_one(
            f"""
            SELECT COUNT(1) AS total_rows
            FROM {cls.TABLE_NAME}
            """
        ) or {}
        return int(row.get('total_rows') or 0)

    @classmethod
    def ensure_symbol_history(
        cls,
        symbol: str,
        user_id: int = 1,
        min_points: int = 120,
        refresh: bool = False
    ) -> int:
        cls.ensure_schema()
        normalized_symbol = cls.normalize_symbol(symbol)
        row = DbUtil.fetch_one(
            f"""
            SELECT COUNT(1) AS total_count, MAX(trade_date) AS latest_date
            FROM {cls.TABLE_NAME}
            WHERE symbol = %s
            """,
            (normalized_symbol,)
        ) or {}

        total_count = int(row.get('total_count') or 0)
        latest_date = row.get('latest_date')
        is_stale = not latest_date or latest_date < (date.today() - timedelta(days=3))
        if refresh or total_count < min_points or is_stale:
            count = max(min_points, int(AppConfig.get('HISTORICAL_DATA_LOOKBACK_DAYS', default=420) or 420))
            return cls.sync_symbol(normalized_symbol, user_id=user_id, count=count)
        return total_count

    @classmethod
    def sync_tracked_universe(
        cls,
        user_ids: Optional[Iterable[int]] = None,
        lookback_days: Optional[int] = None,
        max_symbols: Optional[int] = None
    ) -> Dict[str, object]:
        cls.ensure_schema()
        safe_lookback = int(lookback_days or AppConfig.get('HISTORICAL_DATA_LOOKBACK_DAYS', default=420) or 420)
        safe_max_symbols = int(max_symbols or AppConfig.get('HISTORICAL_DATA_MAX_SYMBOLS', default=240) or 240)
        symbols = cls.collect_tracked_symbols(user_ids=user_ids, limit=safe_max_symbols)

        saved_count = 0
        failed: List[Dict[str, str]] = []
        for symbol in symbols:
            sync_user_id = cls._resolve_symbol_sync_user_id(symbol, user_ids)
            try:
                saved_count += cls.sync_symbol(symbol, user_id=sync_user_id, count=safe_lookback)
            except Exception as exc:
                failed.append({"symbol": symbol, "error": str(exc)[:180]})

        return {
            "symbols": symbols,
            "symbol_count": len(symbols),
            "saved_count": saved_count,
            "failed_count": len(failed),
            "failed": failed[:20],
            "lookback_days": safe_lookback
        }

    @classmethod
    def _resolve_symbol_sync_user_id(cls, symbol: str, user_ids: Optional[Iterable[int]] = None) -> int:
        candidates = [int(item) for item in (user_ids or []) if str(item or '').isdigit() and int(item) > 0]
        if candidates:
            return candidates[0]

        normalized_symbol = cls.normalize_symbol(symbol)
        try:
            manager = get_broker_manager()
            for current_user_id in manager.list_user_ids_with_accounts():
                for account in manager.list_accounts(user_id=current_user_id):
                    broker = manager.get_broker(account.get('id'), user_id=current_user_id)
                    if broker:
                        return int(current_user_id)
        except Exception:
            pass

        try:
            row = DbUtil.fetch_one(
                """
                SELECT user_id
                FROM user_watchlist_stocks
                WHERE symbol = %s
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (normalized_symbol,)
            ) or {}
            return int(row.get('user_id') or 1)
        except Exception:
            return 1

    @classmethod
    def collect_tracked_symbols(
        cls,
        user_ids: Optional[Iterable[int]] = None,
        limit: int = 240
    ) -> List[str]:
        target_limit = max(20, int(limit or 240))
        unique_symbols: OrderedDict[str, bool] = OrderedDict()

        def add_symbols(symbols: Iterable[str]) -> None:
            for raw_symbol in symbols:
                symbol = cls.normalize_symbol(raw_symbol)
                if not symbol or symbol in unique_symbols:
                    continue
                unique_symbols[symbol] = True
                if len(unique_symbols) >= target_limit:
                    return

        for configs in MarketInsightService.BENCHMARKS.values():
            add_symbols(item.get('symbol') for item in configs)
            if len(unique_symbols) >= target_limit:
                return list(unique_symbols.keys())

        manager = get_broker_manager()
        candidate_user_ids = list(user_ids or manager.list_user_ids_with_accounts())
        for current_user_id in candidate_user_ids:
            for account in manager.list_accounts(user_id=current_user_id):
                broker = manager.get_broker(account.get('id'), user_id=current_user_id)
                if not broker:
                    continue
                try:
                    if not broker.is_connected and not broker.connect():
                        continue
                    add_symbols(getattr(position, 'symbol', '') for position in (broker.get_positions() or []))
                except Exception:
                    continue
                if len(unique_symbols) >= target_limit:
                    return list(unique_symbols.keys())

        recommendation_rows = DbUtil.query_all(
            """
            SELECT symbol
            FROM recommendation_items
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 14 DAY)
            GROUP BY symbol
            ORDER BY MAX(created_at) DESC
            LIMIT 80
            """
        )
        add_symbols(row[0] for row in (recommendation_rows or []) if row and row[0])

        decision_rows = DbUtil.query_all(
            """
            SELECT symbol
            FROM quant_trade_decisions
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 21 DAY)
            GROUP BY symbol
            ORDER BY MAX(created_at) DESC
            LIMIT 80
            """
        )
        add_symbols(row[0] for row in (decision_rows or []) if row and row[0])

        return list(unique_symbols.keys())

    @classmethod
    def sync_symbol(cls, symbol: str, user_id: int = 1, count: int = 420) -> int:
        cls.ensure_schema()
        normalized_symbol = cls.normalize_symbol(symbol)
        candles = cls._fetch_candles(normalized_symbol, user_id=user_id, count=max(30, min(int(count or 420), 1500)))
        return cls._save_candles(normalized_symbol, candles, source='skshare')

    @classmethod
    def get_symbol_history_coverage(
        cls,
        symbol: str,
        start_date=None,
        end_date=None
    ) -> Dict[str, object]:
        cls.ensure_schema()
        normalized_symbol = cls.normalize_symbol(symbol)
        range_start = cls._coerce_date(start_date) or date(2020, 1, 1)
        range_end = cls._coerce_date(end_date) or date.today()
        if range_end < range_start:
            range_end = range_start

        row = DbUtil.fetch_one(
            f"""
            SELECT
                COUNT(1) AS total_count,
                COUNT(CASE WHEN trade_date BETWEEN %s AND %s THEN 1 END) AS range_count,
                MIN(trade_date) AS earliest_date,
                MAX(trade_date) AS latest_date,
                MIN(CASE WHEN trade_date BETWEEN %s AND %s THEN trade_date END) AS range_start_date,
                MAX(CASE WHEN trade_date BETWEEN %s AND %s THEN trade_date END) AS range_end_date
            FROM {cls.TABLE_NAME}
            WHERE symbol = %s
            """,
            (
                range_start,
                range_end,
                range_start,
                range_end,
                range_start,
                range_end,
                normalized_symbol
            )
        ) or {}

        range_count = int(row.get('range_count') or 0)
        range_start_date = row.get('range_start_date')
        range_end_date = row.get('range_end_date')
        missing_ranges: List[Dict[str, str]] = []

        if range_count <= 0 or not range_start_date or not range_end_date:
            missing_ranges.append({
                "startDate": range_start.strftime('%Y-%m-%d'),
                "endDate": range_end.strftime('%Y-%m-%d')
            })
        else:
            if range_start_date > range_start:
                missing_ranges.append({
                    "startDate": range_start.strftime('%Y-%m-%d'),
                    "endDate": (range_start_date - timedelta(days=1)).strftime('%Y-%m-%d')
                })
            if range_end_date < range_end:
                missing_ranges.append({
                    "startDate": (range_end_date + timedelta(days=1)).strftime('%Y-%m-%d'),
                    "endDate": range_end.strftime('%Y-%m-%d')
                })

        return {
            "symbol": normalized_symbol,
            "market": cls.detect_market(normalized_symbol),
            "startDate": range_start.strftime('%Y-%m-%d'),
            "endDate": range_end.strftime('%Y-%m-%d'),
            "totalCount": int(row.get('total_count') or 0),
            "rangeCount": range_count,
            "earliestDate": row.get('earliest_date').strftime('%Y-%m-%d') if row.get('earliest_date') else None,
            "latestDate": row.get('latest_date').strftime('%Y-%m-%d') if row.get('latest_date') else None,
            "rangeStartDate": range_start_date.strftime('%Y-%m-%d') if range_start_date else None,
            "rangeEndDate": range_end_date.strftime('%Y-%m-%d') if range_end_date else None,
            "complete": not missing_ranges,
            "missingRanges": missing_ranges
        }

    @classmethod
    def get_daily_series_until(
        cls,
        symbol: str,
        end_date=None,
        limit: int = 260
    ) -> List[Dict[str, object]]:
        cls.ensure_schema()
        normalized_symbol = cls.normalize_symbol(symbol)
        safe_end_date = cls._coerce_date(end_date) or date.today()
        safe_limit = max(20, min(int(limit or 260), 2000))

        rows = DbUtil.fetch_all(
            f"""
            SELECT trade_date, open_price, high_price, low_price, close_price, volume, turnover
            FROM {cls.TABLE_NAME}
            WHERE symbol = %s AND trade_date <= %s
            ORDER BY trade_date DESC
            LIMIT %s
            """,
            (normalized_symbol, safe_end_date, safe_limit)
        ) or []

        if not rows and cls.detect_market(normalized_symbol) == 'US':
            short_symbol = normalized_symbol.split('.')[0]
            rows = DbUtil.fetch_all(
                """
                SELECT trade_date, open_price, high_price, low_price, close_price, volume, 0 AS turnover
                FROM us_stock_historical_data
                WHERE symbol = %s AND trade_date <= %s
                ORDER BY trade_date DESC
                LIMIT %s
                """,
                (short_symbol, safe_end_date, safe_limit)
            ) or []

        series = []
        for row in reversed(rows):
            trade_date = row.get('trade_date')
            series.append({
                'date': trade_date.strftime('%Y-%m-%d') if trade_date else '',
                'open': float(row.get('open_price') or 0),
                'high': float(row.get('high_price') or 0),
                'low': float(row.get('low_price') or 0),
                'close': float(row.get('close_price') or 0),
                'volume': int(row.get('volume') or 0),
                'turnover': float(row.get('turnover') or 0)
            })
        return series

    @classmethod
    def backfill_symbol_history(
        cls,
        symbol: str,
        start_date=None,
        end_date=None,
        user_id: int = 1
    ) -> Dict[str, object]:
        cls.ensure_schema()
        normalized_symbol = cls.normalize_symbol(symbol)
        safe_start_date = cls._coerce_date(start_date) or date(2020, 1, 1)
        safe_end_date = min(cls._coerce_date(end_date) or date.today(), date.today())
        if safe_end_date < safe_start_date:
            safe_end_date = safe_start_date

        coverage = cls.get_symbol_history_coverage(
            normalized_symbol,
            start_date=safe_start_date,
            end_date=safe_end_date
        )
        if coverage.get('complete'):
            return {
                **coverage,
                "savedCount": 0,
                "fetchedRanges": [],
                "skipped": True
            }

        saved_count = 0
        fetched_ranges = []
        for item in coverage.get('missingRanges') or []:
            range_start = cls._coerce_date(item.get('startDate'))
            range_end = cls._coerce_date(item.get('endDate'))
            if not range_start or not range_end or range_end < range_start:
                continue
            candles = cls._fetch_candles_by_date_range_with_fallback(
                normalized_symbol,
                start_date=range_start,
                end_date=range_end,
                user_id=user_id
            )
            if candles:
                saved = cls._save_candles(normalized_symbol, candles, source='skshare-backfill')
                saved_count += saved
                fetched_ranges.append({
                    "startDate": range_start.strftime('%Y-%m-%d'),
                    "endDate": range_end.strftime('%Y-%m-%d'),
                    "savedCount": saved
                })

        refreshed_coverage = cls.get_symbol_history_coverage(
            normalized_symbol,
            start_date=safe_start_date,
            end_date=safe_end_date
        )
        return {
            **refreshed_coverage,
            "savedCount": saved_count,
            "fetchedRanges": fetched_ranges,
            "skipped": False
        }

    @classmethod
    def _save_candles(cls, symbol: str, candles: List[Dict[str, object]], source: str = 'skshare') -> int:
        saved = 0
        for candle in candles:
            DbUtil.execute_sql(
                f"""
                INSERT INTO {cls.TABLE_NAME} (
                    symbol, market, trade_date, open_price, high_price, low_price,
                    close_price, volume, turnover, source, synced_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE
                    market = VALUES(market),
                    open_price = VALUES(open_price),
                    high_price = VALUES(high_price),
                    low_price = VALUES(low_price),
                    close_price = VALUES(close_price),
                    volume = VALUES(volume),
                    turnover = VALUES(turnover),
                    source = VALUES(source),
                    synced_at = NOW(),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    symbol,
                    cls.detect_market(symbol),
                    candle['trade_date'],
                    candle['open'],
                    candle['high'],
                    candle['low'],
                    candle['close'],
                    candle['volume'],
                    candle['turnover'],
                    source
                )
            )
            saved += 1
        return saved

    @classmethod
    def _fetch_candles(cls, symbol: str, user_id: int = 1, count: int = 420) -> List[Dict[str, object]]:
        safe_count = max(30, min(int(count or 420), 1500))
        end_date = date.today()
        start_date = end_date - timedelta(days=max(safe_count * 2, safe_count + 60))
        candles = cls._fetch_candles_by_date_range_with_fallback(
            symbol,
            start_date=start_date,
            end_date=end_date,
            user_id=user_id,
        )
        return candles[-safe_count:]

    @classmethod
    def _fetch_candles_by_date_range(
        cls,
        symbol: str,
        start_date: date,
        end_date: date,
        user_id: int = 1,
        chunk_days: int = 360
    ) -> List[Dict[str, object]]:
        return cls._fetch_candles_from_skshare(symbol, start_date, end_date)

    @classmethod
    def _fetch_candles_by_date_range_with_fallback(
        cls,
        symbol: str,
        start_date: date,
        end_date: date,
        user_id: int = 1
    ) -> List[Dict[str, object]]:
        market = cls.detect_market(symbol)

        skshare_error = None
        try:
            skshare_history = cls._fetch_candles_by_date_range(
                symbol,
                start_date=start_date,
                end_date=end_date,
                user_id=user_id
            )
            if skshare_history:
                return skshare_history
        except Exception as exc:
            skshare_error = exc
            logger.warning("skshare 历史行情获取失败: %s %s", symbol, exc)

        if market == 'CN':
            try:
                cn_history = cls._fetch_candles_from_akshare(symbol, start_date, end_date)
                if cn_history:
                    return cn_history
            except Exception as exc:
                logger.warning("本地 akshare 历史行情 fallback 失败: %s %s", symbol, exc)

        if market == 'US':
            try:
                local_history = cls._fetch_candles_from_us_history_table(symbol, start_date, end_date)
                if local_history:
                    return local_history
            except Exception as exc:
                logger.warning("本地美股历史表 fallback 失败: %s %s", symbol, exc)

        if market in {'US', 'HK', 'CN'}:
            try:
                yf_history = cls._fetch_candles_from_yfinance(symbol, start_date, end_date)
                if yf_history:
                    return yf_history
            except Exception as exc:
                logger.warning("yfinance 历史行情 fallback 失败: %s %s", symbol, exc)

        if skshare_error:
            logger.warning("历史行情无可用 fallback: %s %s", symbol, skshare_error)
        return []

    @classmethod
    def _fetch_candles_from_skshare(
        cls,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, object]]:
        base_urls = cls._skshare_base_urls()
        if not base_urls:
            return []

        market = cls.detect_market(symbol)
        if market not in {'CN', 'HK', 'US'}:
            return []

        start_text = start_date.strftime('%Y%m%d')
        end_text = end_date.strftime('%Y%m%d')
        session = requests.Session()
        session.trust_env = False

        last_error: Optional[Exception] = None
        for request_def in cls._skshare_history_requests(symbol):
            interface = request_def['interface']
            params = dict(request_def['params'])
            if request_def.get('date_filter'):
                params.setdefault('start_date', start_text)
                params.setdefault('end_date', end_text)
            for base_url in base_urls:
                url = f"{base_url.rstrip('/')}/api/public/{interface}"
                try:
                    response = session.get(url, params=params, timeout=cls._skshare_timeout())
                    if response.status_code == 404:
                        continue
                    if response.status_code >= 400:
                        last_error = RuntimeError(f"{response.status_code} {response.text[:180]}")
                        continue
                    rows = response.json() or []
                    candles = cls._format_skshare_rows(rows)
                    if request_def.get('client_date_filter'):
                        candles = [
                            item for item in candles
                            if start_date.strftime('%Y-%m-%d') <= str(item.get('trade_date') or '') <= end_date.strftime('%Y-%m-%d')
                        ]
                    if candles:
                        return candles
                except Exception as exc:
                    last_error = exc
                    continue

        if last_error:
            raise RuntimeError(f"skshare 历史行情请求失败: {last_error}") from last_error
        return []

    @classmethod
    def _skshare_base_urls(cls) -> List[str]:
        configured = (
            os.getenv('SKSHARE_BASE_URL')
            or os.getenv('REF_SKSHARE_BASE_URL')
            or str(AppConfig.get('SKSHARE_BASE_URL', default='') or '').strip()
            or 'http://127.0.0.1:18081'
        )
        candidates = []
        for item in str(configured or '').split(','):
            base_url = item.strip().rstrip('/')
            if base_url and base_url not in candidates:
                candidates.append(base_url)
        return candidates

    @staticmethod
    def _skshare_timeout() -> int:
        raw = (
            os.getenv('SKSHARE_TIMEOUT')
            or os.getenv('REF_SKSHARE_TIMEOUT')
            or AppConfig.get('SKSHARE_TIMEOUT', default=30)
            or 30
        )
        try:
            return max(3, min(int(raw), 120))
        except (TypeError, ValueError):
            return 30

    @classmethod
    def _skshare_history_requests(cls, symbol: str) -> List[Dict[str, object]]:
        normalized_symbol = cls.normalize_symbol(symbol)
        code = normalized_symbol.split('.')[0]
        market = cls.detect_market(normalized_symbol)

        if market == 'CN':
            if cls._is_cn_etf_symbol(normalized_symbol):
                return [
                    cls._skshare_request('fund_etf_hist_em', code, period=True, date_filter=True, adjust=True)
                ]

            prefixed_code = cls._skshare_cn_prefixed_symbol(normalized_symbol)
            return [
                cls._skshare_request('stock_zh_a_daily', prefixed_code, date_filter=True, adjust=True),
                cls._skshare_request('stock_zh_a_hist_tx', prefixed_code, date_filter=True, adjust=True),
                cls._skshare_request('stock_zh_a_hist', code, period=True, date_filter=True, adjust=True),
            ]
        if market == 'HK':
            digits = ''.join(ch for ch in code if ch.isdigit())
            hk_code = (digits or code).zfill(5)
            return [
                cls._skshare_request('stock_hk_daily', hk_code, adjust=True, client_date_filter=True),
                cls._skshare_request('stock_hk_hist', hk_code, period=True, date_filter=True, adjust=True),
            ]
        if market == 'US':
            upper_code = code.upper()
            return [
                cls._skshare_request('stock_us_daily', upper_code, adjust=False, client_date_filter=True),
                cls._skshare_request('stock_us_hist', f'105.{upper_code}', period=True, date_filter=True, adjust=True),
                cls._skshare_request('stock_us_hist', f'106.{upper_code}', period=True, date_filter=True, adjust=True),
                cls._skshare_request('stock_us_hist', f'107.{upper_code}', period=True, date_filter=True, adjust=True),
                cls._skshare_request('stock_us_hist', upper_code, period=True, date_filter=True, adjust=True),
            ]
        return []

    @staticmethod
    def _skshare_request(
        interface: str,
        symbol: str,
        *,
        period: bool = False,
        date_filter: bool = False,
        adjust: object = False,
        client_date_filter: bool = False
    ) -> Dict[str, object]:
        params: Dict[str, str] = {'symbol': symbol}
        if period:
            params['period'] = 'daily'
        if adjust is not False:
            params['adjust'] = 'qfq' if adjust is True else str(adjust)
        return {
            'interface': interface,
            'params': params,
            'date_filter': date_filter,
            'client_date_filter': client_date_filter,
        }

    @staticmethod
    def _skshare_cn_prefixed_symbol(symbol: str) -> str:
        normalized_symbol = str(symbol or '').strip().upper()
        code, _, suffix = normalized_symbol.partition('.')
        if suffix in {'SH', 'SS'}:
            return f"sh{code}"
        if suffix in {'SZ', 'BJ'}:
            return f"sz{code}"
        return code

    @classmethod
    def _format_skshare_rows(cls, rows) -> List[Dict[str, object]]:
        payload: List[Dict[str, object]] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            trade_date = (
                cls._coerce_date(row.get('日期'))
                or cls._coerce_date(row.get('date'))
                or cls._coerce_date(row.get('Date'))
            )
            if not trade_date:
                continue
            volume = row.get('成交量') or row.get('volume') or row.get('Volume')
            amount = row.get('amount')
            turnover = row.get('成交额') or row.get('Turnover')
            if volume is None and amount is not None:
                volume = row.get('amount')
            elif turnover is None and amount is not None:
                turnover = amount
            if turnover is None:
                turnover = row.get('turnover')
            payload.append({
                'trade_date': trade_date.strftime('%Y-%m-%d'),
                'open': cls._to_float(row.get('开盘') or row.get('open') or row.get('Open')),
                'high': cls._to_float(row.get('最高') or row.get('high') or row.get('High')),
                'low': cls._to_float(row.get('最低') or row.get('low') or row.get('Low')),
                'close': cls._to_float(row.get('收盘') or row.get('close') or row.get('Close')),
                'volume': cls._to_int(volume),
                'turnover': cls._to_float(turnover)
            })

        deduped = {item['trade_date']: item for item in payload}
        result = list(deduped.values())
        result.sort(key=lambda item: item['trade_date'])
        return result

    @classmethod
    def _fetch_candles_from_us_history_table(
        cls,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, object]]:
        short_symbol = cls.normalize_symbol(symbol).split('.')[0]
        rows = DbUtil.fetch_all(
            """
            SELECT trade_date, open_price, high_price, low_price, close_price, volume, 0 AS turnover
            FROM us_stock_historical_data
            WHERE symbol = %s AND trade_date BETWEEN %s AND %s
            ORDER BY trade_date ASC
            """,
            (short_symbol, start_date, end_date)
        ) or []
        return [
            {
                'trade_date': row.get('trade_date').strftime('%Y-%m-%d') if row.get('trade_date') else '',
                'open': cls._to_float(row.get('open_price')),
                'high': cls._to_float(row.get('high_price')),
                'low': cls._to_float(row.get('low_price')),
                'close': cls._to_float(row.get('close_price')),
                'volume': cls._to_int(row.get('volume')),
                'turnover': cls._to_float(row.get('turnover'))
            }
            for row in rows
            if row.get('trade_date')
        ]

    @classmethod
    def _fetch_candles_from_yfinance(
        cls,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, object]]:
        if not YFINANCE_AVAILABLE:
            return []

        ticker = cls._to_yfinance_symbol(symbol)
        if not ticker:
            return []

        with cls._temporary_proxy_clear():
            history = yf.Ticker(ticker).history(
                start=start_date.strftime('%Y-%m-%d'),
                end=(end_date + timedelta(days=1)).strftime('%Y-%m-%d'),
                auto_adjust=False,
                actions=False
            )

        if history is None or getattr(history, 'empty', True):
            return []

        payload = []
        for row in history.reset_index().to_dict('records'):
            trade_date = row.get('Date')
            trade_day = getattr(trade_date, 'date', lambda: trade_date)()
            if not trade_day:
                continue
            payload.append({
                'trade_date': trade_day.strftime('%Y-%m-%d'),
                'open': cls._to_float(row.get('Open')),
                'high': cls._to_float(row.get('High')),
                'low': cls._to_float(row.get('Low')),
                'close': cls._to_float(row.get('Close')),
                'volume': cls._to_int(row.get('Volume')),
                'turnover': 0.0
            })

        payload.sort(key=lambda item: item['trade_date'])
        return payload

    @classmethod
    def _fetch_candles_from_akshare(
        cls,
        symbol: str,
        start_date: date,
        end_date: date
    ) -> List[Dict[str, object]]:
        if not AKSHARE_AVAILABLE:
            return []

        normalized_symbol = cls.normalize_symbol(symbol)
        if cls.detect_market(normalized_symbol) != 'CN':
            return []

        short_symbol = normalized_symbol.split('.')[0]
        start_text = start_date.strftime('%Y%m%d')
        end_text = end_date.strftime('%Y%m%d')

        with cls._temporary_proxy_clear():
            if cls._is_cn_etf_symbol(normalized_symbol):
                frame = ak.fund_etf_hist_em(
                    symbol=short_symbol,
                    period='daily',
                    start_date=start_text,
                    end_date=end_text,
                    adjust='qfq'
                )
            else:
                frame = ak.stock_zh_a_hist(
                    symbol=short_symbol,
                    period='daily',
                    start_date=start_text,
                    end_date=end_text,
                    adjust='qfq'
                )

        if frame is None or getattr(frame, 'empty', True):
            return []

        payload = []
        for row in frame.to_dict('records'):
            trade_date = cls._coerce_date(row.get('日期'))
            if not trade_date:
                continue
            payload.append({
                'trade_date': trade_date.strftime('%Y-%m-%d'),
                'open': cls._to_float(row.get('开盘')),
                'high': cls._to_float(row.get('最高')),
                'low': cls._to_float(row.get('最低')),
                'close': cls._to_float(row.get('收盘')),
                'volume': cls._to_int(row.get('成交量')),
                'turnover': cls._to_float(row.get('成交额'))
            })

        payload.sort(key=lambda item: item['trade_date'])
        return payload

    @staticmethod
    def _to_yfinance_symbol(symbol: str) -> str:
        normalized = str(symbol or '').strip().upper()
        if not normalized or '.' not in normalized:
            return normalized

        code, suffix = normalized.split('.', 1)
        if suffix == 'US':
            return code
        if suffix == 'HK':
            digits = ''.join(ch for ch in code if ch.isdigit())
            return f"{(digits.lstrip('0') or '0').zfill(4)}.HK"
        if suffix == 'SH':
            return f"{code}.SS"
        if suffix in {'SZ', 'BJ'}:
            return f"{code}.{suffix}"
        return normalized

    @staticmethod
    def _to_float(value) -> float:
        try:
            if value is None or value != value:
                return 0.0
            return float(value)
        except Exception:
            return 0.0

    @staticmethod
    def _to_int(value) -> int:
        try:
            if value is None or value != value:
                return 0
            return int(float(value))
        except Exception:
            return 0

    @staticmethod
    def _is_cn_etf_symbol(symbol: str) -> bool:
        normalized_symbol = str(symbol or '').strip().upper()
        row = DbUtil.fetch_one(
            "SELECT 1 AS hit FROM cn_etf WHERE symbol = %s LIMIT 1",
            (normalized_symbol,)
        ) or {}
        return bool(row.get('hit'))

    @staticmethod
    @contextmanager
    def _temporary_proxy_clear():
        proxy_keys = ['all_proxy', 'ALL_PROXY', 'http_proxy', 'HTTP_PROXY', 'https_proxy', 'HTTPS_PROXY']
        original = {key: os.environ.get(key) for key in proxy_keys}
        try:
            for key in proxy_keys:
                os.environ.pop(key, None)
            yield
        finally:
            for key, value in original.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    @classmethod
    def _format_candles(cls, candles) -> List[Dict[str, object]]:
        payload = []
        for candle in candles or []:
            payload.append({
                'trade_date': candle.timestamp.strftime('%Y-%m-%d'),
                'open': float(getattr(candle, 'open', 0) or 0),
                'high': float(getattr(candle, 'high', 0) or 0),
                'low': float(getattr(candle, 'low', 0) or 0),
                'close': float(getattr(candle, 'close', 0) or 0),
                'volume': int(getattr(candle, 'volume', 0) or 0),
                'turnover': float(getattr(candle, 'turnover', 0) or 0)
            })
        payload.sort(key=lambda item: item['trade_date'])
        return payload

    @classmethod
    def _build_quote_context(cls, user_id: int = 1):
        return build_quote_context(user_id=user_id)

    @classmethod
    def _load_longbridge_credentials(cls, user_id: int = 1) -> Optional[Dict[str, str]]:
        return {}

    @classmethod
    def _query_daily_series(cls, symbol: str, limit: int) -> List[Dict[str, object]]:
        rows = DbUtil.fetch_all(
            f"""
            SELECT trade_date, open_price, high_price, low_price, close_price, volume, turnover
            FROM {cls.TABLE_NAME}
            WHERE symbol = %s
            ORDER BY trade_date DESC
            LIMIT %s
            """,
            (symbol, int(limit))
        ) or []

        if not rows and cls.detect_market(symbol) == 'US':
            short_symbol = symbol.split('.')[0]
            rows = DbUtil.fetch_all(
                """
                SELECT trade_date, open_price, high_price, low_price, close_price, volume, 0 AS turnover
                FROM us_stock_historical_data
                WHERE symbol = %s
                ORDER BY trade_date DESC
                LIMIT %s
                """,
                (short_symbol, int(limit))
            ) or []

        series = []
        for row in reversed(rows):
            trade_date = row.get('trade_date')
            series.append({
                'date': trade_date.strftime('%Y-%m-%d') if trade_date else '',
                'open': float(row.get('open_price') or 0),
                'high': float(row.get('high_price') or 0),
                'low': float(row.get('low_price') or 0),
                'close': float(row.get('close_price') or 0),
                'volume': int(row.get('volume') or 0),
                'turnover': float(row.get('turnover') or 0)
            })
        return series

    @classmethod
    def _aggregate_series(cls, series: List[Dict[str, object]], timeframe: str) -> List[Dict[str, object]]:
        buckets: OrderedDict[str, List[Dict[str, object]]] = OrderedDict()
        for item in series:
            target_date = datetime.strptime(item['date'], '%Y-%m-%d').date()
            if timeframe == 'weekly':
                bucket_date = target_date - timedelta(days=target_date.weekday())
            elif timeframe == 'monthly':
                bucket_date = target_date.replace(day=1)
            elif timeframe == 'quarterly':
                bucket_start_month = ((target_date.month - 1) // 3) * 3 + 1
                bucket_date = target_date.replace(month=bucket_start_month, day=1)
            elif timeframe == 'yearly':
                bucket_date = target_date.replace(month=1, day=1)
            else:
                raise ValueError(f'不支持的聚合周期: {timeframe}')
            bucket_key = bucket_date.strftime('%Y-%m-%d')
            buckets.setdefault(bucket_key, []).append(item)

        aggregated = []
        for bucket_key, items in buckets.items():
            aggregated.append({
                'date': bucket_key,
                'open': float(items[0]['open']),
                'high': max(float(entry['high']) for entry in items),
                'low': min(float(entry['low']) for entry in items),
                'close': float(items[-1]['close']),
                'volume': int(sum(int(entry['volume']) for entry in items)),
                'turnover': round(sum(float(entry['turnover']) for entry in items), 2)
            })
        return aggregated

    @classmethod
    def _attach_change_metrics(cls, series: List[Dict[str, object]]) -> List[Dict[str, object]]:
        previous_close = None
        enriched = []
        for item in series:
            close_price = float(item.get('close') or 0)
            change_percent = 0.0
            if previous_close:
                change_percent = ((close_price - previous_close) / previous_close) * 100
            enriched.append({
                **item,
                'changePercent': round(change_percent, 2)
            })
            previous_close = close_price or previous_close
        return enriched

    @staticmethod
    def detect_market(symbol: str) -> str:
        normalized = str(symbol or '').upper()
        if normalized.endswith('.HK'):
            return 'HK'
        if normalized.endswith('.SH') or normalized.endswith('.SZ') or normalized.endswith('.BJ'):
            return 'CN'
        return 'US'

    @classmethod
    def normalize_symbol(cls, symbol: str) -> str:
        normalized = str(symbol or '').strip().upper()
        if not normalized:
            return ''
        if '.' in normalized:
            return normalized
        return f"{normalized}.{cls.detect_market(normalized)}"

    @staticmethod
    def _coerce_date(value) -> Optional[date]:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value[:10], '%Y-%m-%d').date()
            except ValueError:
                return None
        return None
