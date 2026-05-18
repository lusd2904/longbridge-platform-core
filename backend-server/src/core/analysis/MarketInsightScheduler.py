import threading

from config.Config import AppConfig
from core.analysis.MarketInsightService import MarketInsightService
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil


class MarketInsightScheduler:
    JOB_NAME = 'market_insight_refresh'

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
        self._stop_event.wait(8)
        while not self._stop_event.is_set():
            try:
                SystemTaskService.ensure_schema()
                enabled = SystemTaskService.is_enabled(self.JOB_NAME, default=AppConfig.get('MARKET_INSIGHT_ENABLED', default=True))
                if isinstance(enabled, str):
                    enabled = enabled.strip().lower() not in {'0', 'false', 'no', 'off'}

                if enabled:
                    MarketInsightService.refresh_all_markets(user_id=1, source='scheduler')
                    self._update_job('success')
                else:
                    self._update_job('disabled', '市场动态调度器已关闭')
            except Exception as exc:
                self._update_job('failed', str(exc)[:220])

            interval = max(300, SystemTaskService.get_interval(self.JOB_NAME, int(AppConfig.get('MARKET_INSIGHT_REFRESH_INTERVAL', default=900) or 900)))
            self._stop_event.wait(interval)

    def _update_job(self, status: str, message: str = None):
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
            VALUES (%s, CURDATE(), NOW(), %s, %s)
            ON DUPLICATE KEY UPDATE
                last_run_date = CURDATE(),
                last_run_at = NOW(),
                status = VALUES(status),
                message = VALUES(message),
                updated_at = CURRENT_TIMESTAMP
            """,
            (self.JOB_NAME, status, message or '市场动态已刷新')
        )


market_insight_scheduler = MarketInsightScheduler()
