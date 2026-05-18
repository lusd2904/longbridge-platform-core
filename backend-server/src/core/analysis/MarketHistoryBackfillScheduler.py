import logging
import threading
import time
from datetime import date, datetime

from config.Config import AppConfig
from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.analysis.IndicatorSnapshotService import IndicatorSnapshotService
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil

logger = logging.getLogger(__name__)


class MarketHistoryBackfillScheduler:
    JOB_NAME = 'market_history_universe_backfill'

    def __init__(self):
        self._thread = None
        self._stop_event = threading.Event()
        self._poll_interval_seconds = 60

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

    def run_once(self):
        self._ensure_job_table()
        return self._run_job()

    def _loop(self):
        self._stop_event.wait(36)
        while not self._stop_event.is_set():
            try:
                self._ensure_job_table()
                if self._is_enabled() and self._should_run(datetime.now()):
                    self._run_job()
            except Exception:
                logger.exception('全市场历史慢补数轮询失败')
            self._stop_event.wait(self._poll_interval_seconds)

    def _is_enabled(self) -> bool:
        return SystemTaskService.is_enabled(self.JOB_NAME, default=True)

    def _should_run(self, now: datetime) -> bool:
        interval_seconds = SystemTaskService.get_interval(self.JOB_NAME, 900)
        row = DbUtil.fetch_one(
            """
            SELECT last_run_at, status
            FROM scheduled_jobs
            WHERE job_name = %s
            LIMIT 1
            """,
            (self.JOB_NAME,)
        ) or {}
        if str(row.get('status') or '').lower() == 'running':
            return False

        last_run_at = row.get('last_run_at')
        if not last_run_at:
            return True
        return (now - last_run_at).total_seconds() >= interval_seconds

    def _run_job(self):
        policy = SystemTaskService.get_policy(self.JOB_NAME)
        settings = dict(policy.get('settings') or {})
        cursor = max(0, int(settings.get('cursor') or 0))
        batch_size = max(1, min(8, SystemTaskService.get_batch_size(self.JOB_NAME, 2)))
        max_requests_per_minute = max(0, SystemTaskService.get_rate_limit(self.JOB_NAME, 4))
        start_date = str(
            settings.get('startDate')
            or AppConfig.get('HISTORICAL_BACKFILL_START_DATE', default='2020-01-01')
            or '2020-01-01'
        ).strip()
        end_date = min(date.today(), HistoricalMarketDataService._coerce_date(settings.get('endDate')) or date.today())

        self._update_job_status('running', f'慢补数启动中，cursor={cursor} batch={batch_size} start={start_date}')

        universe = IndicatorSnapshotService._collect_universe_symbols(limit=batch_size, offset=cursor)
        wrapped = False
        if not universe and cursor > 0:
            cursor = 0
            wrapped = True
            universe = IndicatorSnapshotService._collect_universe_symbols(limit=batch_size, offset=0)

        processed_symbols = []
        failed = []
        for index, item in enumerate(universe):
            symbol = item.get('symbol')
            if not symbol:
                continue
            try:
                result = HistoricalMarketDataService.backfill_symbol_history(
                    symbol,
                    start_date=start_date,
                    end_date=end_date,
                    user_id=1
                )
                if int(result.get('savedCount') or 0) > 0:
                    IndicatorSnapshotService.refresh_symbol(
                        symbol,
                        user_id=1,
                        timeframes=('daily', 'weekly', 'monthly', 'quarterly', 'yearly')
                    )
                processed_symbols.append(symbol)
            except Exception as exc:
                failed.append({"symbol": symbol, "error": str(exc)[:180]})
                logger.warning('慢补数处理 %s 失败: %s', symbol, exc)

            if max_requests_per_minute > 0 and index < len(universe) - 1:
                time.sleep(max(1.0, 60 / max_requests_per_minute))

        next_cursor = 0 if wrapped or len(universe) < batch_size else cursor + len(universe)
        next_settings = {
            **settings,
            "cursor": next_cursor,
            "startDate": start_date,
            "endDate": end_date.strftime('%Y-%m-%d'),
            "lastProcessedSymbols": processed_symbols[:12],
            "lastFailedCount": len(failed),
            "lastRunAt": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        SystemTaskService.update_policy(
            self.JOB_NAME,
            {
                "settings": next_settings,
                "description": "后台慢速补全全市场股票与 ETF 历史行情及指标。"
            }
        )

        now = datetime.now()
        message = f"慢补数完成 {len(processed_symbols)} 个标的，失败 {len(failed)} 个，nextCursor={next_cursor}"
        self._update_job_status(
            'success',
            message,
            last_run_date=now.date(),
            last_run_at=now
        )
        return {
            "processed": len(processed_symbols),
            "failed": failed[:20],
            "cursor": cursor,
            "nextCursor": next_cursor,
            "symbols": processed_symbols
        }

    def _ensure_job_table(self):
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

    def _update_job_status(self, status: str, message: str, last_run_date=None, last_run_at=None):
        DbUtil.execute_sql(
            """
            INSERT INTO scheduled_jobs (job_name, last_run_date, last_run_at, status, message)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                last_run_date = COALESCE(VALUES(last_run_date), last_run_date),
                last_run_at = COALESCE(VALUES(last_run_at), last_run_at),
                status = VALUES(status),
                message = VALUES(message),
                updated_at = CURRENT_TIMESTAMP
            """,
            (self.JOB_NAME, last_run_date, last_run_at, status, (message or '')[:255] or None)
        )


market_history_backfill_scheduler = MarketHistoryBackfillScheduler()
