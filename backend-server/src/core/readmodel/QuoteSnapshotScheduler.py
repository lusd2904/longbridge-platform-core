import threading
from collections import OrderedDict
from collections.abc import Iterable
from datetime import datetime

from api import data_routes as legacy_data_routes
from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.broker.BrokerInterface import get_broker_manager
from core.platform.SystemTaskService import SystemTaskService
from core.readmodel.QuoteSnapshotService import QuoteSnapshotService
from utils.DbUtil import DbUtil


class QuoteSnapshotScheduler:
    JOB_NAME = "quote_snapshot_refresh"
    UNIVERSE_TABLE_LIMIT = 12

    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def _loop(self):
        self._stop_event.wait(18)
        while not self._stop_event.is_set():
            try:
                QuoteSnapshotService.ensure_schema()
                SystemTaskService.ensure_schema()
                if not SystemTaskService.is_enabled(self.JOB_NAME, default=True):
                    self._update_job("disabled", "行情快照任务已关闭")
                    self._stop_event.wait(30)
                    continue

                user_ids = get_broker_manager().list_user_ids_with_accounts()
                if not user_ids:
                    self._update_job("disabled", "暂无可用券商账户，行情快照跳过")
                    self._stop_event.wait(60)
                    continue

                limit = max(30, SystemTaskService.get_batch_size(self.JOB_NAME, 180))
                symbols = self._collect_target_symbols(limit=limit)
                if not symbols:
                    self._update_job("disabled", "暂无可用于展示的行情标的")
                    self._stop_event.wait(60)
                    continue

                quote_map = {}
                selected_user_id = None
                for user_id in user_ids:
                    quote_map = legacy_data_routes._fetch_live_quotes(symbols, user_id=user_id)  # noqa: SLF001
                    if quote_map:
                        selected_user_id = user_id
                        break

                if not quote_map:
                    self._update_job("failed", f"行情快照拉取失败，目标标的 {len(symbols)} 个")
                    self._stop_event.wait(60)
                    continue

                snapshot_at = datetime.now()
                saved = QuoteSnapshotService.save_quotes(
                    quote_map.values(),
                    source="scheduler",
                    snapshot_at=snapshot_at,
                )
                self._update_job(
                    "success",
                    f"行情快照已刷新，用户 {selected_user_id}，目标 {len(symbols)}，写入 {saved}",
                )
            except Exception as exc:
                self._update_job("failed", str(exc)[:220])

            interval = max(60, SystemTaskService.get_interval(self.JOB_NAME, 300))
            self._stop_event.wait(interval)

    def _collect_target_symbols(self, *, limit: int) -> list[str]:
        unique_symbols: OrderedDict[str, bool] = OrderedDict()

        def add_symbols(items: Iterable[str]) -> None:
            for raw_symbol in items or []:
                symbol = HistoricalMarketDataService.normalize_symbol(raw_symbol)
                if not symbol or symbol in unique_symbols:
                    continue
                unique_symbols[symbol] = True
                if len(unique_symbols) >= limit:
                    return

        add_symbols(HistoricalMarketDataService.collect_tracked_symbols(limit=limit))
        if len(unique_symbols) >= limit:
            return list(unique_symbols.keys())

        table_limit = max(4, min(self.UNIVERSE_TABLE_LIMIT, max(1, limit // 12)))
        table_configs = list(legacy_data_routes.STOCK_TABLE_BY_MARKET.values()) + list(
            legacy_data_routes.ETF_TABLE_BY_MARKET.values()
        )
        for table_config in table_configs:
            table_name = table_config["table"]
            if not legacy_data_routes._table_exists(table_name):  # noqa: SLF001
                continue
            rows = (
                DbUtil.fetch_all(
                    f"""
                SELECT symbol
                FROM {table_name}
                WHERE is_active = 1
                ORDER BY COALESCE(market_cap, 0) DESC, COALESCE(current_price, 0) DESC, symbol ASC
                LIMIT %s
                """,
                    (table_limit,),
                )
                or []
            )
            add_symbols(row.get("symbol") for row in rows if row.get("symbol"))
            if len(unique_symbols) >= limit:
                break

        return list(unique_symbols.keys())

    def _update_job(self, status: str, message: str):
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
        DbUtil.execute_sql(
            """
            INSERT INTO scheduled_jobs (job_name, last_run_date, last_run_at, status, message)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                last_run_date = VALUES(last_run_date),
                last_run_at = VALUES(last_run_at),
                status = VALUES(status),
                message = VALUES(message),
                updated_at = CURRENT_TIMESTAMP
            """,
            (self.JOB_NAME, datetime.now().date(), datetime.now(), status, message),
        )


quote_snapshot_scheduler = QuoteSnapshotScheduler()
