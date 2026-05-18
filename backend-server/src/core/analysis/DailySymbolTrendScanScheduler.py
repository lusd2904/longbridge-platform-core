import logging
import threading
from datetime import date, datetime, timedelta

from core.analysis.DailySymbolTrendScanService import DailySymbolTrendScanService
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil

logger = logging.getLogger(__name__)


class DailySymbolTrendScanScheduler:
    JOB_NAME = "daily_symbol_trend_ai_scan"

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

    def run_once(self):
        self._ensure_job_table()
        return self._run_job()

    def _loop(self):
        self._stop_event.wait(40)
        while not self._stop_event.is_set():
            try:
                self._ensure_job_table()
                if self._is_enabled() and self._should_run(datetime.now()):
                    self._run_job()
            except Exception:
                logger.exception("逐股 AI 趋势扫描轮询失败")
            self._stop_event.wait(self._poll_interval_seconds)

    def _is_enabled(self) -> bool:
        return SystemTaskService.is_enabled(self.JOB_NAME, default=True)

    def _should_run(self, now: datetime) -> bool:
        hour, minute = SystemTaskService.get_daily_time(self.JOB_NAME, 18, 40)
        if (now.hour, now.minute) < (hour, minute):
            return False

        policy = SystemTaskService.get_policy(self.JOB_NAME)
        settings = dict(policy.get("settings") or {})
        target_date = (now.date() - timedelta(days=1)).strftime("%Y-%m-%d")
        if str(settings.get("completedForDate") or "") == target_date:
            return False

        row = DbUtil.fetch_one(
            """
            SELECT last_run_at, status
            FROM scheduled_jobs
            WHERE job_name = %s
            LIMIT 1
            """,
            (self.JOB_NAME,)
        ) or {}
        if str(row.get("status") or "").lower() == "running":
            return False

        last_run_at = row.get("last_run_at")
        if not last_run_at:
            return True
        return (now - last_run_at).total_seconds() >= SystemTaskService.get_interval(self.JOB_NAME, 60)

    def _run_job(self):
        policy = SystemTaskService.get_policy(self.JOB_NAME)
        settings = dict(policy.get("settings") or {})
        target_date = (datetime.now().date() - timedelta(days=1)).strftime("%Y-%m-%d")

        if str(settings.get("targetDate") or "") != target_date:
            cursor = 0
        else:
            cursor = max(0, int(settings.get("cursor") or 0))

        batch_size = max(1, min(SystemTaskService.get_batch_size(self.JOB_NAME, 24), 60))
        self._update_job("running", f"逐股 AI 趋势扫描启动中，targetDate={target_date} cursor={cursor} batch={batch_size}")

        result = DailySymbolTrendScanService.run_batch(
            analysis_date=target_date,
            batch_size=batch_size,
            cursor=cursor,
            user_id=1
        )

        now = datetime.now()
        next_settings = {
            **settings,
            "targetDate": target_date,
            "cursor": int(result.get("nextCursor") or 0),
            "lastProcessedSymbols": result.get("symbols", [])[:20],
            "lastBatchProcessed": int(result.get("processed") or 0),
            "lastBatchSaved": int(result.get("saved") or 0),
            "lastFallbackCount": int(result.get("fallbackCount") or 0),
            "lastRunAt": now.strftime("%Y-%m-%d %H:%M:%S")
        }
        if result.get("completed"):
            next_settings["completedForDate"] = target_date
            next_settings["cursor"] = 0

        SystemTaskService.update_policy(
            self.JOB_NAME,
            {
                "settings": next_settings,
                "description": "每天按批次为全市场股票和 ETF 生成截止昨日的 AI 趋势扫描结果。"
            }
        )

        message = (
            f"逐股 AI 趋势扫描完成批次 {int(result.get('processed') or 0)} 个标的，"
            f"回退 {int(result.get('fallbackCount') or 0)} 个，nextCursor={int(result.get('nextCursor') or 0)}"
        )
        self._update_job(
            "success",
            message,
            last_run_date=self._coerce_date(target_date) or now.date(),
            last_run_at=now
        )
        return result

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
            (self.JOB_NAME, last_run_date, last_run_at, status, (message or "")[:255] or None)
        )

    @staticmethod
    def _coerce_date(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
        return None


daily_symbol_trend_scan_scheduler = DailySymbolTrendScanScheduler()
