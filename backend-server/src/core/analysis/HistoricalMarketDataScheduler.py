import logging
import threading
from datetime import date, datetime

from config.Config import AppConfig
from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.platform.SchedulerExecutionUser import resolve_task_execution_user
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil

logger = logging.getLogger(__name__)


class HistoricalMarketDataScheduler:
    JOB_NAME = 'historical_market_data_daily_sync'

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
        self._stop_event.wait(24)
        while not self._stop_event.is_set():
            try:
                self._ensure_job_table()
                if self._is_enabled() and self._should_run(datetime.now()):
                    self._run_job()
            except Exception:
                logger.exception('历史行情定时任务轮询失败')

            self._stop_event.wait(self._poll_interval_seconds)

    def _is_enabled(self) -> bool:
        SystemTaskService.ensure_schema()
        raw_value = SystemTaskService.is_enabled(self.JOB_NAME, default=AppConfig.get('HISTORICAL_DATA_SYNC_ENABLED', default=True))
        if isinstance(raw_value, str):
            return raw_value.strip().lower() not in {'0', 'false', 'no', 'off'}
        return bool(raw_value)

    def _schedule_time(self):
        default_hour = self._coerce_int(AppConfig.get('HISTORICAL_DATA_SYNC_HOUR', default=7), 7)
        default_minute = self._coerce_int(AppConfig.get('HISTORICAL_DATA_SYNC_MINUTE', default=10), 10)
        hour, minute = SystemTaskService.get_daily_time(self.JOB_NAME, default_hour, default_minute)
        return min(max(hour, 0), 23), min(max(minute, 0), 59)

    def _should_run(self, now: datetime) -> bool:
        hour, minute = self._schedule_time()
        if (now.hour, now.minute) < (hour, minute):
            return False

        row = DbUtil.query_one(
            "SELECT last_run_date FROM scheduled_jobs WHERE job_name = %s",
            (self.JOB_NAME,)
        )
        last_run_date = self._coerce_date(row[0] if row else None)
        return last_run_date != now.date()

    def _run_job(self):
        self._update_job_status('running', '历史行情同步启动中')
        try:
            execution_user = resolve_task_execution_user(self.JOB_NAME)
            if not execution_user:
                self._update_job_status(
                    'skipped',
                    '历史行情同步已跳过：没有可用的执行用户',
                    last_run_date=datetime.now().date(),
                    last_run_at=datetime.now()
                )
                return
            result = HistoricalMarketDataService.sync_tracked_universe(user_ids=[int(execution_user['userId'])])
            self._update_job_status(
                'success',
                f"同步 {result.get('symbol_count', 0)} 个标的，写入 {result.get('saved_count', 0)} 条K线，执行用户 {execution_user.get('username') or execution_user.get('userId')}",
                last_run_date=datetime.now().date(),
                last_run_at=datetime.now()
            )
        except Exception as exc:
            self._update_job_status('failed', f"历史行情同步失败: {str(exc)[:220]}")
            logger.exception('历史行情自动同步失败')

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

    @staticmethod
    def _coerce_int(value, fallback: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

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


historical_market_data_scheduler = HistoricalMarketDataScheduler()
