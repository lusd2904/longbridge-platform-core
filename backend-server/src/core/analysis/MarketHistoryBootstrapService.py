from __future__ import annotations

from datetime import datetime

from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.analysis.IndicatorSnapshotService import IndicatorSnapshotService
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil


class MarketHistoryBootstrapService:
    TASK_KEY = "bootstrap_market_history_2024"

    @classmethod
    def run_once(cls, user_id: int = 1, batch_size: int = 160) -> dict[str, object]:
        SystemTaskService.ensure_schema()
        HistoricalMarketDataService.ensure_schema()
        IndicatorSnapshotService.ensure_schema()

        policy = SystemTaskService.get_policy(cls.TASK_KEY)
        state = dict(policy.get("settings") or {})
        cn_hk_offset = int(state.get("cnHkOffset") or 0)
        us_synced = bool(state.get("usSynced"))
        processed_symbols: list[str] = []

        if not us_synced:
            cls._copy_us_history_from_2024()
            us_synced = True

        universe = cls._collect_cn_hk_symbols(limit=max(20, int(batch_size or 160)), offset=cn_hk_offset)
        for symbol in universe:
            try:
                HistoricalMarketDataService.sync_symbol(symbol, user_id=user_id, count=650)
                IndicatorSnapshotService.refresh_symbol(symbol, user_id=user_id)
                processed_symbols.append(symbol)
            except Exception:
                continue

        next_offset = cn_hk_offset + len(universe)
        completed = us_synced and not universe
        next_settings = {
            "usSynced": us_synced,
            "cnHkOffset": next_offset,
            "lastRunAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "lastProcessedSymbols": processed_symbols[:25],
        }

        SystemTaskService.update_policy(
            cls.TASK_KEY,
            {
                "enabled": False if completed else bool(policy.get("enabled")),
                "settings": next_settings,
                "description": "一次性历史回补已完成" if completed else "一次性历史回补执行中，继续手动触发可推进进度",
            },
        )
        if completed:
            SystemTaskService.mark_single_run_completed(cls.TASK_KEY, "2024起全量历史回补完成，任务已自动关闭")

        return {
            "taskKey": cls.TASK_KEY,
            "completed": completed,
            "usSynced": us_synced,
            "processedSymbols": processed_symbols,
            "nextOffset": next_offset,
            "remainingBatchEstimate": 0 if completed else len(universe),
        }

    @classmethod
    def _copy_us_history_from_2024(cls) -> None:
        DbUtil.execute_sql(
            """
            INSERT INTO market_price_history_daily (
                symbol, market, trade_date, open_price, high_price, low_price,
                close_price, volume, turnover, source, synced_at
            )
            SELECT CONCAT(symbol, '.US') AS symbol,
                   'US' AS market,
                   trade_date,
                   open_price,
                   high_price,
                   low_price,
                   close_price,
                   volume,
                   0 AS turnover,
                   'bootstrap-us-history',
                   NOW()
            FROM us_stock_historical_data
            WHERE trade_date >= '2024-01-01'
            ON DUPLICATE KEY UPDATE
                open_price = VALUES(open_price),
                high_price = VALUES(high_price),
                low_price = VALUES(low_price),
                close_price = VALUES(close_price),
                volume = VALUES(volume),
                source = VALUES(source),
                synced_at = NOW(),
                updated_at = CURRENT_TIMESTAMP
            """
        )

    @classmethod
    def _collect_cn_hk_symbols(cls, limit: int = 160, offset: int = 0) -> list[str]:
        rows = (
            DbUtil.fetch_all(
                """
            SELECT symbol
            FROM (
                SELECT symbol FROM cn_stocks WHERE is_active = 1
                UNION ALL
                SELECT symbol FROM cn_etf WHERE is_active = 1
                UNION ALL
                SELECT symbol FROM hk_stocks WHERE is_active = 1
                UNION ALL
                SELECT symbol FROM hk_etf WHERE is_active = 1
            ) universe
            ORDER BY symbol ASC
            LIMIT %s OFFSET %s
            """,
                (int(limit), int(offset)),
            )
            or []
        )
        return [row.get("symbol") for row in rows if row.get("symbol")]
