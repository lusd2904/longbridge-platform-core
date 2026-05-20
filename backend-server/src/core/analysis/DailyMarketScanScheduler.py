import logging
import threading
from datetime import date, datetime

from core.analysis.DailyMarketScanService import DailyMarketScanService
from core.platform.SchedulerExecutionUser import resolve_task_execution_user
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil

logger = logging.getLogger(__name__)


class DailyMarketScanScheduler:
    JOB_NAME = 'daily_market_ai_scan'

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
        self._stop_event.wait(32)
        while not self._stop_event.is_set():
            try:
                SystemTaskService.ensure_schema()
                self._ensure_job_table()
                if SystemTaskService.is_enabled(self.JOB_NAME, default=True) and self._should_run(datetime.now()):
                    self._run_job()
            except Exception:
                logger.exception('市场AI扫描调度器轮询失败')
            self._stop_event.wait(self._poll_interval_seconds)

    def _should_run(self, now: datetime) -> bool:
        hour, minute = SystemTaskService.get_daily_time(self.JOB_NAME, 8, 20)
        if (now.hour, now.minute) < (hour, minute):
            return False
        row = DbUtil.query_one("SELECT last_run_date FROM scheduled_jobs WHERE job_name = %s", (self.JOB_NAME,))
        last_run_date = self._coerce_date(row[0] if row else None)
        return last_run_date != now.date()

    def _run_job(self):
        self._update_job('running', '市场 AI 技术扫描启动中')
        execution_user = resolve_task_execution_user(self.JOB_NAME)
        if not execution_user:
            self._update_job(
                'skipped',
                '市场 AI 技术扫描已跳过：没有可用的执行用户',
                last_run_date=datetime.now().date(),
                last_run_at=datetime.now()
            )
            return

        result = DailyMarketScanService.refresh_all_markets(user_id=int(execution_user["userId"]))
        self._update_job(
            'success',
            f"已完成 {len(result.get('markets', []))} 个市场技术扫描，执行用户 {execution_user.get('username') or execution_user.get('userId')}",
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


daily_market_scan_scheduler = DailyMarketScanScheduler()
