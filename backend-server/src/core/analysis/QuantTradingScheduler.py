import threading
from datetime import datetime

from config.Config import AppConfig
from core.analysis.QuantTradingService import QuantTradingService
from core.broker.BrokerInterface import get_broker_manager
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil


class QuantTradingScheduler:
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
            SystemTaskService.ensure_schema()
            user_ids = get_broker_manager().list_user_ids_with_accounts()
            if not user_ids:
                self._stop_event.wait(60)
                continue

            for user_id in user_ids:
                try:
                    if not SystemTaskService.is_enabled('quant_trading', default=True):
                        self._update_job(user_id, 'disabled', '系统任务中心已关闭 AI 量化交易')
                        continue

                    enabled = AppConfig.get('AI_QUANT_TRADING_ENABLED', user_id=user_id, default=False)
                    if isinstance(enabled, str):
                        enabled = enabled.strip().lower() in {'1', 'true', 'yes', 'on'}

                    interval = max(300, min(
                        int(AppConfig.get('AI_QUANT_INTERVAL', user_id=user_id, default=900) or 900),
                        SystemTaskService.get_interval('quant_trading', 900)
                    ))
                    if not enabled:
                        self._update_job(user_id, 'disabled', 'AI 量化交易已关闭')
                        continue

                    if not self._should_run(user_id, interval):
                        continue

                    result = QuantTradingService.run_watchlist_strategy_cycle(user_id=user_id, source='scheduler', execute=None)
                    self._update_job(
                        user_id,
                        'success',
                        f"自选池量化策略已完成，发现 {int(result.get('opportunityCount') or 0)} 个机会"
                    )
                except Exception as exc:
                    self._update_job(user_id, 'failed', str(exc)[:220])

            self._stop_event.wait(60)

    def _job_name(self, user_id: int) -> str:
        return QuantTradingService.job_name(user_id)

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


quant_trading_scheduler = QuantTradingScheduler()
