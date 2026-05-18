import logging
import threading
from datetime import datetime

from core.analysis.FinanceBriefingService import FinanceBriefingService
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil

logger = logging.getLogger(__name__)


class FinanceBriefingScheduler:
    JOB_NAME = 'finance_briefing_refresh'

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
                SystemTaskService.ensure_schema()
                self._ensure_job_table()
                if SystemTaskService.is_enabled(self.JOB_NAME, default=True):
                    self._run_job()
                else:
                    self._update_job('disabled', '财经信息调度已关闭')
            except Exception:
                logger.exception('财经信息调度器轮询失败')
            self._stop_event.wait(SystemTaskService.get_interval(self.JOB_NAME, 900))

    def _run_job(self):
        result = FinanceBriefingService.refresh_all_markets(user_id=1)
        self._update_job(
            'success',
            f"已生成 {len(result.get('items', []))} 条财经信息",
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


finance_briefing_scheduler = FinanceBriefingScheduler()
