import logging
import threading
from datetime import date, datetime

from core.analysis.IndicatorSnapshotService import IndicatorSnapshotService
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil

logger = logging.getLogger(__name__)


class IndicatorRefreshScheduler:
    JOB_NAME = 'symbol_indicator_daily_refresh'

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

    def _loop(self):
        self._stop_event.wait(28)
        while not self._stop_event.is_set():
            try:
                SystemTaskService.ensure_schema()
                self._ensure_job_table()
                if SystemTaskService.is_enabled(self.JOB_NAME, default=True) and self._should_run(datetime.now()):
                    self._run_job()
            except Exception:
                logger.exception('技术指标调度器轮询失败')
            self._stop_event.wait(self._poll_interval_seconds)

    def _should_run(self, now: datetime) -> bool:
        hour, minute = SystemTaskService.get_daily_time(self.JOB_NAME, 7, 40)
        if (now.hour, now.minute) < (hour, minute):
            return False
        row = DbUtil.query_one("SELECT last_run_date FROM scheduled_jobs WHERE job_name = %s", (self.JOB_NAME,))
        last_run_date = self._coerce_date(row[0] if row else None)
        return last_run_date != now.date()

    def _run_job(self):
        policy = SystemTaskService.get_policy(self.JOB_NAME)
        settings = policy.get('settings') or {}
        cursor = int(settings.get('cursor') or 0)
        batch_size = max(500, SystemTaskService.get_batch_size(self.JOB_NAME, 1500))

        self._update_job('running', f'技术指标刷新中，cursor={cursor} batch={batch_size}')
        result = IndicatorSnapshotService.refresh_universe(batch_size=batch_size, cursor=cursor)

        next_cursor = 0 if not result.get('hasMore') else int(result.get('nextCursor') or 0)
        SystemTaskService.update_policy(
            self.JOB_NAME,
            {
                'settings': {
                    'cursor': next_cursor,
                    'lastProcessed': int(result.get('processed') or 0),
                    'lastFailed': len(result.get('failed') or [])
                }
            }
        )
        self._update_job(
            'success',
            f"已生成 {result.get('processed', 0)} 个标的指标，nextCursor={next_cursor}",
            last_run_date=datetime.now().date(),
            last_run_at=datetime.now()
        )

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

    def _update_job(self, status: str, message: str, last_run_date=None, last_run_at=None):
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

    @staticmethod
    def _coerce_date(value):
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


indicator_refresh_scheduler = IndicatorRefreshScheduler()
