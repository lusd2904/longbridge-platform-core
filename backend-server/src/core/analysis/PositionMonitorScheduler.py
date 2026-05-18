import threading
from datetime import datetime

from config.Config import AppConfig
from core.analysis.StrategyMonitorService import StrategyMonitorService
from core.broker.BrokerInterface import get_broker_manager
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil


class PositionMonitorScheduler:
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
        self._stop_event.wait(12)
        while not self._stop_event.is_set():
            SystemTaskService.ensure_schema()
            user_ids = get_broker_manager().list_user_ids_with_accounts()
            if not user_ids:
                self._stop_event.wait(60)
                continue

            for user_id in user_ids:
                try:
                    if not SystemTaskService.is_enabled('position_monitor', default=True):
                        self._update_job(user_id, 'disabled', '系统任务中心已关闭持仓监控')
                        continue

                    interval = max(120, min(
                        int(AppConfig.get('POSITION_MONITOR_INTERVAL', user_id=user_id, default=300) or 300),
                        SystemTaskService.get_interval('position_monitor', 300)
                    ))
                    if not self._should_run(user_id, interval):
                        continue

                    result = StrategyMonitorService.run_monitor(user_id=user_id, source='scheduler')
                    self._update_job(
                        user_id,
                        'success',
                        f"持仓监控已完成，触发 {len(result.get('alerts') or [])} 条告警"
                    )
                except Exception as exc:
                    self._update_job(user_id, 'failed', str(exc)[:220])

            self._stop_event.wait(60)

    def _job_name(self, user_id: int) -> str:
        return f'position_monitor:user:{int(user_id)}'

    def _should_run(self, user_id: int, interval: int) -> bool:
        row = DbUtil.fetch_one(
            """
            SELECT last_run_at
            FROM scheduled_jobs
            WHERE job_name = %s
            """,
            (self._job_name(user_id),)
        )
        last_run_at = row.get('last_run_at') if row else None
        if not last_run_at:
            return True
        return (datetime.now() - last_run_at).total_seconds() >= interval

    def _update_job(self, user_id: int, status: str, message: str):
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
            (self._job_name(user_id), status, message)
        )


position_monitor_scheduler = PositionMonitorScheduler()
