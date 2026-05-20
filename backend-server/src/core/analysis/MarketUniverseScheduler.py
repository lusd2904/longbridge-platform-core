import logging
import threading
from datetime import date, datetime

from config.Config import AppConfig
from core.platform.SchedulerExecutionUser import resolve_task_execution_user
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil
from utils.MarketUniverseSync import MarketUniverseSync

logger = logging.getLogger(__name__)


class MarketUniverseScheduler:
    JOB_NAME = 'market_universe_daily_sync'

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
        self._stop_event.wait(20)
        while not self._stop_event.is_set():
            try:
                self._ensure_job_table()
                if self._is_enabled() and self._should_run(datetime.now()):
                    self._run_sync_job()
            except Exception:
                logger.exception('市场底库定时任务轮询失败')

            self._stop_event.wait(self._poll_interval_seconds)

    def _is_enabled(self) -> bool:
        SystemTaskService.ensure_schema()
        raw_value = SystemTaskService.is_enabled(self.JOB_NAME, default=AppConfig.get('MARKET_UNIVERSE_SYNC_ENABLED', default=True))
        if isinstance(raw_value, str):
            return raw_value.strip().lower() not in {'0', 'false', 'no', 'off'}
        return bool(raw_value)

    def _get_schedule(self):
        hour, minute = SystemTaskService.get_daily_time(
            self.JOB_NAME,
            self._coerce_int(AppConfig.get('MARKET_UNIVERSE_SYNC_HOUR', default=6), 6),
            self._coerce_int(AppConfig.get('MARKET_UNIVERSE_SYNC_MINUTE', default=0), 0)
        )
        hour = min(max(hour, 0), 23)
        minute = min(max(minute, 0), 59)
        return hour, minute

    def _get_markets(self):
        raw_value = AppConfig.get('MARKET_UNIVERSE_SYNC_MARKETS', default='US,HK,CN')
        if isinstance(raw_value, str):
            values = [item.strip().upper() for item in raw_value.split(',') if item.strip()]
        elif isinstance(raw_value, (list, tuple, set)):
            values = [str(item).strip().upper() for item in raw_value if str(item).strip()]
        else:
            values = ['US', 'HK', 'CN']

        supported = []
        for market in values:
            if market in {'US', 'HK', 'CN'} and market not in supported:
                supported.append(market)

        return supported or ['US', 'HK', 'CN']

    def _should_run(self, now: datetime) -> bool:
        hour, minute = self._get_schedule()
        if (now.hour, now.minute) < (hour, minute):
            return False

        row = DbUtil.query_one(
            "SELECT last_run_date FROM scheduled_jobs WHERE job_name = %s",
            (self.JOB_NAME,)
        )
        last_run_date = self._coerce_date(row[0] if row else None)
        return last_run_date != now.date()

    def _run_sync_job(self):
        started_at = datetime.now()
        markets = self._get_markets()
        self._update_job_status(
            status='running',
            message=f"准备同步市场: {', '.join(markets)}"
        )

        try:
            execution_user = resolve_task_execution_user(self.JOB_NAME)
            if not execution_user:
                self._update_job_status(
                    status='skipped',
                    message='市场底库同步已跳过：没有可用的执行用户',
                    last_run_date=started_at.date(),
                    last_run_at=started_at
                )
                return
            result = MarketUniverseSync.sync_markets(markets=markets, user_id=int(execution_user['userId']))
            saved = int(result.get('total_saved', 0))
            duration = result.get('duration_seconds', 0)
            self._update_job_status(
                status='success',
                message=f"同步完成，写入 {saved} 条，耗时 {duration} 秒，执行用户 {execution_user.get('username') or execution_user.get('userId')}",
                last_run_date=started_at.date(),
                last_run_at=started_at
            )
            logger.info('市场底库自动同步完成: markets=%s saved=%s duration=%s', markets, saved, duration)
        except Exception as exc:
            self._update_job_status(
                status='failed',
                message=f"同步失败: {str(exc)[:220]}"
            )
            logger.exception('市场底库自动同步失败')

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
            (self.JOB_NAME, last_run_date, last_run_at, status, message[:255] if message else None)
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


market_universe_scheduler = MarketUniverseScheduler()
