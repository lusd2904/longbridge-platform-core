import threading
from datetime import datetime

from core.broker.BrokerInterface import get_broker_manager
from core.platform.SystemTaskService import SystemTaskService
from core.readmodel.SymbolContentCacheService import SymbolContentCacheService
from shared.longbridge import build_content_context, build_quote_context, resolve_region, to_plain
from utils.DbUtil import DbUtil


class SymbolContentCacheScheduler:
    JOB_NAME = "symbol_content_cache_refresh"
    HOT_SYMBOLS = [
        "AAPL.US",
        "NVDA.US",
        "SPY.US",
        "QQQ.US",
        "510300.SH",
        "159915.SZ",
        "700.HK",
        "2800.HK",
        "3033.HK",
    ]

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
        self._stop_event.wait(20)
        while not self._stop_event.is_set():
            try:
                SystemTaskService.ensure_schema()
                if not SystemTaskService.is_enabled(self.JOB_NAME, default=True):
                    self._update_job("disabled", "标的内容缓存任务已关闭")
                    self._stop_event.wait(30)
                    continue

                user_ids = get_broker_manager().list_user_ids_with_accounts()
                if not user_ids:
                    self._update_job("disabled", "暂无可用券商账户，内容缓存跳过")
                    self._stop_event.wait(60)
                    continue

                user_id = user_ids[0]
                quote_ctx = build_quote_context(user_id=user_id, region=resolve_region())
                content_ctx = build_content_context(user_id=user_id, region=resolve_region())

                saved = 0
                for symbol in self.HOT_SYMBOLS:
                    market = self._detect_market(symbol)
                    if hasattr(quote_ctx, "filings"):
                        try:
                            saved += SymbolContentCacheService.upsert_items(
                                symbol=symbol,
                                market=market,
                                content_type="announcements",
                                items=to_plain(quote_ctx.filings(symbol)) or [],
                                source_name="longbridge-filings",
                            )
                        except Exception:
                            pass
                    try:
                        saved += SymbolContentCacheService.upsert_items(
                            symbol=symbol,
                            market=market,
                            content_type="news",
                            items=to_plain(content_ctx.news(symbol)) or [],
                            source_name="longbridge-news",
                        )
                    except Exception:
                        pass
                    try:
                        saved += SymbolContentCacheService.upsert_items(
                            symbol=symbol,
                            market=market,
                            content_type="topics",
                            items=to_plain(content_ctx.topics(symbol)) or [],
                            source_name="longbridge-topics",
                        )
                    except Exception:
                        pass
                self._update_job("success", f"标的内容缓存已刷新，写入 {saved} 条")
            except Exception as exc:
                self._update_job("failed", str(exc)[:220])

            interval = max(300, SystemTaskService.get_interval(self.JOB_NAME, 900))
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

    @staticmethod
    def _detect_market(symbol: str) -> str:
        if symbol.endswith(".HK"):
            return "HK"
        if symbol.endswith(".SH") or symbol.endswith(".SZ") or symbol.endswith(".BJ"):
            return "CN"
        return "US"


symbol_content_cache_scheduler = SymbolContentCacheScheduler()
