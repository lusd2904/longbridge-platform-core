import threading

from config.Config import AppConfig
from core.analysis.RecommendationService import RecommendationService
from core.platform.SchedulerExecutionUser import resolve_task_execution_user
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil


class RecommendationScheduler:
    JOB_NAME = 'recommendation_refresh'

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
        initial_delay = 10
        self._stop_event.wait(initial_delay)
        while not self._stop_event.is_set():
            try:
                SystemTaskService.ensure_schema()
                self._ensure_job_table()
                if SystemTaskService.is_enabled(self.JOB_NAME, default=True):
                    execution_user = resolve_task_execution_user(self.JOB_NAME)
                    if not execution_user:
                        self._update_job('skipped', '推荐结果刷新已跳过：没有可用的执行用户')
                    else:
                        RecommendationService.refresh_all_profiles(user_id=int(execution_user['userId']))
                        self._update_job('success', f"推荐结果已刷新，执行用户 {execution_user.get('username') or execution_user.get('userId')}")
                else:
                    self._update_job('disabled', '推荐调度器已关闭')
            except Exception as exc:
                self._update_job('failed', str(exc)[:220])

            interval = max(900, SystemTaskService.get_interval(self.JOB_NAME, int(AppConfig.get('RECOMMENDATION_REFRESH_INTERVAL', default=1800) or 1800)))
            self._stop_event.wait(interval)

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

    def _update_job(self, status: str, message: str):
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
            (self.JOB_NAME, status, (message or '')[:255] or None)
        )


recommendation_scheduler = RecommendationScheduler()
