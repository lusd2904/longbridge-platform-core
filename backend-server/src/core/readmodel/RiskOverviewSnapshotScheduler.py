import threading
from datetime import datetime

from api import data_routes as legacy_data_routes
from core.broker.BrokerInterface import get_broker_manager
from core.platform.SystemTaskService import SystemTaskService
from core.readmodel.RiskOverviewSnapshotService import RiskOverviewSnapshotService
from utils.DbUtil import DbUtil


class RiskOverviewSnapshotScheduler:
    JOB_NAME = "risk_overview_snapshot_refresh"

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
        self._stop_event.wait(15)
        while not self._stop_event.is_set():
            try:
                SystemTaskService.ensure_schema()
                if not SystemTaskService.is_enabled(self.JOB_NAME, default=True):
                    self._update_job("disabled", "风控快照任务已关闭")
                    self._stop_event.wait(30)
                    continue

                saved = 0
                for user_id in get_broker_manager().list_user_ids_with_accounts():
                    overall = legacy_data_routes._build_risk_overview(user_id=user_id, account_id=None)  # noqa: SLF001
                    RiskOverviewSnapshotService.save_snapshot(
                        user_id=user_id,
                        account_id=None,
                        payload=overall,
                        source="scheduler",
                    )
                    saved += 1
                    for account in get_broker_manager().list_accounts(user_id=user_id) or []:
                        account_id = int(account.get("id") or 0)
                        if account_id <= 0:
                            continue
                        try:
                            payload = legacy_data_routes._build_risk_overview(user_id=user_id, account_id=account_id)  # noqa: SLF001
                            RiskOverviewSnapshotService.save_snapshot(
                                user_id=user_id,
                                account_id=account_id,
                                payload=payload,
                                source="scheduler",
                            )
                            saved += 1
                        except Exception:
                            continue
                self._update_job("success", f"风控总览快照已刷新，共 {saved} 份")
            except Exception as exc:
                self._update_job("failed", str(exc)[:220])

            interval = max(60, SystemTaskService.get_interval(self.JOB_NAME, 180))
            self._stop_event.wait(interval)

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


risk_overview_snapshot_scheduler = RiskOverviewSnapshotScheduler()

