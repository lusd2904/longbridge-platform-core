from __future__ import annotations

import json
import os
import socket
import sys
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib import error as urlerror
from urllib import request as urlrequest

from fastapi import Body, Depends, HTTPException, Query


REFACTOR_ROOT = Path(__file__).resolve().parents[4]
if str(REFACTOR_ROOT) not in sys.path:
    sys.path.insert(0, str(REFACTOR_ROOT))

from apps.operations.module_shared import (
    AccountAssetSnapshotService,
    DbUtil,
    MarketHistoryBootstrapService,
    MarketUniverseSync,
    PositionSnapshotService,
    QuantTradingService,
    QuoteSnapshotService,
    RiskOverviewSnapshotService,
    StrategyMonitorService,
    SymbolContentCacheService,
    SystemTaskService,
    account_asset_snapshot_scheduler,
    bootstrap_runtime,
    build_alert,
    build_content_context,
    build_dependency_status,
    build_health_payload,
    build_quote_context,
    create_service_app,
    daily_market_scan_scheduler,
    daily_symbol_trend_scan_scheduler,
    finance_briefing_scheduler,
    get_current_session,
    historical_market_data_scheduler,
    indicator_refresh_scheduler,
    market_history_backfill_scheduler,
    market_insight_scheduler,
    market_universe_scheduler,
    position_monitor_scheduler,
    position_snapshot_scheduler,
    quant_trading_scheduler,
    quote_snapshot_scheduler,
    recommendation_scheduler,
    resolve_region,
    risk_overview_snapshot_scheduler,
    service_port,
    summarize_status,
    symbol_content_cache_scheduler,
    to_plain,
)
from apps.runtime_shared.auth import generate_token

bootstrap_runtime()


app = create_service_app(
    title="Refactor V2 Scheduler Service",
    version="0.2.0",
    description="Phase 1 live service for scheduler orchestration, policies, job status and manual triggers.",
)
PORT = service_port("REF_SCHEDULER_SERVICE_PORT", 8107)
SCHEDULER_LEASE_SECONDS = max(15, int(os.getenv("REF_SCHEDULER_LEASE_SECONDS", "20")))
SCHEDULER_RENEW_INTERVAL_SECONDS = max(5, int(os.getenv("REF_SCHEDULER_RENEW_INTERVAL_SECONDS", "5")))


def _config_port(env_var: str, default: int) -> int:
    return int(os.getenv(env_var, str(default)))


def _service_url(url_env_var: str, port_env_var: str, default_port: int) -> str:
    explicit_url = str(os.getenv(url_env_var, "")).strip().rstrip("/")
    if explicit_url:
        return explicit_url
    return f"http://127.0.0.1:{_config_port(port_env_var, default_port)}"


ANALYSIS_SERVICE_URL = _service_url("REF_ANALYSIS_SERVICE_URL", "REF_ANALYSIS_SERVICE_PORT", 8103)


def _format_datetime(value: Any) -> Optional[str]:
    if not value:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _is_admin(session: dict) -> bool:
    return str(session.get("role") or "").strip().lower() == "admin"


def _user_scoped_job_name(task_key: str, user_id: int) -> str:
    if task_key == "position_monitor":
        return position_monitor_scheduler._job_name(user_id)  # noqa: SLF001
    if task_key == "quant_trading":
        return quant_trading_scheduler._job_name(user_id)  # noqa: SLF001
    return task_key


def _coerce_positive_int(value: Any) -> Optional[int]:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _load_active_user(user_id: Any) -> Optional[Dict[str, Any]]:
    normalized_user_id = _coerce_positive_int(user_id)
    if normalized_user_id is None:
        return None
    try:
        row = DbUtil.fetch_one(
            """
            SELECT id, username, role, status
            FROM users
            WHERE id = %s
              AND COALESCE(status, 'active') NOT IN ('disabled', 'locked')
            LIMIT 1
            """,
            (normalized_user_id,),
        )
    except Exception:
        return None
    if not row:
        return None
    return {
        "userId": int(row.get("id") or normalized_user_id),
        "username": row.get("username") or f"user-{normalized_user_id}",
        "role": row.get("role") or "user",
    }


def _resolve_task_execution_user(task_key: str, requested_user_id: Any = None) -> Optional[Dict[str, Any]]:
    policy_settings: Dict[str, Any] = {}
    try:
        policy_settings = (SystemTaskService.get_policy(task_key) or {}).get("settings") or {}
    except Exception:
        policy_settings = {}

    env_key = f"REF_{task_key.upper()}_EXECUTION_USER_ID"
    candidates = [
        ("request-user", requested_user_id),
        ("task-policy", policy_settings.get("executionUserId")),
        ("task-policy", policy_settings.get("schedulerUserId")),
        ("task-policy", policy_settings.get("userId")),
        ("env", os.getenv(env_key)),
        ("env", os.getenv("REF_SYSTEM_TASK_EXECUTION_USER_ID")),
    ]
    for reason, candidate in candidates:
        user = _load_active_user(candidate)
        if user:
            user["reason"] = reason
            return user

    try:
        row = DbUtil.fetch_one(
            """
            SELECT id, username, role
            FROM users
            WHERE COALESCE(status, 'active') NOT IN ('disabled', 'locked')
            ORDER BY CASE WHEN role = 'admin' THEN 0 ELSE 1 END, id ASC
            LIMIT 1
            """
        )
    except Exception:
        row = None
    if not row:
        return None
    return {
        "userId": int(row.get("id") or 0),
        "username": row.get("username") or f"user-{row.get('id')}",
        "role": row.get("role") or "user",
        "reason": "active-user-fallback",
    }


def _ensure_job_table() -> None:
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


def _ensure_runtime_lease_table() -> None:
    DbUtil.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS scheduler_runtime_leases (
            lock_name VARCHAR(80) NOT NULL PRIMARY KEY,
            owner_id VARCHAR(120) DEFAULT NULL,
            lease_until DATETIME DEFAULT NULL,
            acquired_at DATETIME DEFAULT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def _job_status(job_name: str) -> Dict[str, Any]:
    _ensure_job_table()
    row = DbUtil.fetch_one(
        """
        SELECT job_name, last_run_date, last_run_at, status, message, updated_at
        FROM scheduled_jobs
        WHERE job_name = %s
        LIMIT 1
        """,
        (job_name,),
    ) or {}
    return {
        "jobName": row.get("job_name") or job_name,
        "lastRunDate": row.get("last_run_date").strftime("%Y-%m-%d") if row.get("last_run_date") else None,
        "lastRunAt": _format_datetime(row.get("last_run_at")),
        "state": row.get("status") or "idle",
        "message": row.get("message") or "",
        "updatedAt": _format_datetime(row.get("updated_at")),
    }


def _write_job_status(
    job_name: str,
    status: str,
    message: str,
    *,
    last_run_date: Optional[date] = None,
    last_run_at: Optional[datetime] = None,
) -> None:
    _ensure_job_table()
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
        (job_name, last_run_date, last_run_at, status, (message or "")[:255] or None),
    )


def _coerce_date(value: Any) -> Optional[date]:
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


def _analysis_summary(payload: Any, session_name: str) -> str:
    if isinstance(payload, dict):
        for key in ("summary", "message", "detail"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value[:255]
        for key in ("count", "itemCount", "reviewCount", "generatedCount"):
            value = payload.get(key)
            if value is not None:
                return f"自选股 {session_name} 复核已完成，生成 {value} 条 AI 建议"[:255]
        data = payload.get("data")
        if isinstance(data, dict):
            nested = _analysis_summary(data, session_name)
            if nested:
                return nested[:255]
    return f"自选股 {session_name} 复核已完成，仅生成 AI 建议，不执行交易"[:255]


def _list_watchlist_review_users(session_name: str) -> List[Dict[str, Any]]:
    flag_column = "scan_before_open" if session_name == "pre_open" else "scan_after_close"
    max_users = max(1, min(int(os.getenv("REF_WATCHLIST_REVIEW_MAX_USERS", "50")), 200))
    try:
        DbUtil.execute_sql(
            """
            CREATE TABLE IF NOT EXISTS user_watchlist_stocks (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                symbol VARCHAR(32) NOT NULL,
                name VARCHAR(255) NOT NULL DEFAULT '',
                market VARCHAR(16) NOT NULL DEFAULT '',
                asset_type VARCHAR(32) NOT NULL DEFAULT 'stock',
                category VARCHAR(255) NOT NULL DEFAULT '',
                scan_before_open TINYINT(1) NOT NULL DEFAULT 1,
                scan_after_close TINYINT(1) NOT NULL DEFAULT 1,
                added_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                last_scan_at TIMESTAMP NULL DEFAULT NULL,
                UNIQUE KEY uniq_user_watchlist_symbol (user_id, symbol),
                KEY idx_user_watchlist_sessions (user_id, scan_before_open, scan_after_close)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
    except Exception:
        pass

    users = DbUtil.fetch_all(
        f"""
        SELECT
            u.id,
            u.username,
            u.role,
            COUNT(w.id) AS target_count
        FROM users u
        JOIN user_watchlist_stocks w
          ON w.user_id = u.id
         AND w.{flag_column} = 1
        WHERE COALESCE(u.status, 'active') NOT IN ('disabled', 'locked')
        GROUP BY u.id, u.username, u.role
        ORDER BY target_count DESC, u.id ASC
        LIMIT %s
        """,
        (max_users,),
    ) or []
    if users:
        return [
            {
                "userId": int(row.get("id") or 0),
                "username": row.get("username") or f"user-{row.get('id')}",
                "role": row.get("role") or "user",
                "targetCount": int(row.get("target_count") or 0),
                "reason": "watchlist-targets",
            }
            for row in users
            if int(row.get("id") or 0) > 0
        ]

    return []


def _request_watchlist_review_for_user(session_name: str, user: Dict[str, Any]) -> Dict[str, Any]:
    user_id = int(user.get("userId") or user.get("id") or 0)
    if user_id <= 0:
        raise RuntimeError("watchlist review 用户无效")
    service_token = generate_token(user_id, str(user.get("username") or "scheduler-service"), str(user.get("role") or "user"))
    payload = {
        "session": session_name,
        "userId": user_id,
        "triggerSource": "scheduler",
        "dryRun": True,
    }
    request_body = json.dumps(payload).encode("utf-8")
    request = urlrequest.Request(
        f"{ANALYSIS_SERVICE_URL}/api/v1/analysis/agent/watchlist-review",
        data=request_body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {service_token}"},
        method="POST",
    )

    try:
        with urlrequest.urlopen(request, timeout=180) as response:
            response_body = response.read().decode("utf-8")
            result = json.loads(response_body) if response_body else {}
    except urlerror.HTTPError as exc:
        response_body = exc.read().decode("utf-8", errors="ignore")
        message = f"HTTP {exc.code}: {response_body[:180] or exc.reason}"
        raise RuntimeError(message) from exc
    except urlerror.URLError as exc:
        message = f"analysis-service 不可达: {exc.reason}"
        raise RuntimeError(message) from exc
    except Exception as exc:
        message = str(exc)[:220] or "watchlist review 调用失败"
        raise RuntimeError(message) from exc

    success = bool(result.get("success", True)) if isinstance(result, dict) else True
    if not success:
        failure_message = str(result.get("message") or result.get("error") or "analysis-service 返回失败")[:220]
        raise RuntimeError(failure_message)
    return result if isinstance(result, dict) else {"success": True, "data": result}


def _is_watchlist_review_failure(result_payload: Dict[str, Any]) -> bool:
    result_status = str(result_payload.get("status") or "").strip().lower()
    if bool(result_payload.get("degraded")):
        return True
    if result_status in {"failed", "degraded", "error"}:
        return True
    return False


def _is_watchlist_review_skipped(result_payload: Dict[str, Any]) -> bool:
    result_status = str(result_payload.get("status") or "").strip().lower()
    reason = str(result_payload.get("reason") or "").strip().lower()
    return bool(result_payload.get("skipped")) or result_status == "skipped" or reason in {"no_targets", "empty-watchlist"}


def _run_watchlist_review(session_name: str) -> Dict[str, Any]:
    now = datetime.now()
    job_name = f"watchlist_{session_name}_review"
    _write_job_status(job_name, "running", f"自选股 {session_name} 复核任务执行中")

    users = _list_watchlist_review_users(session_name)
    if not users:
        message = f"自选股 {session_name} 复核已跳过：没有开启本时段扫描的自选标的"
        _write_job_status(job_name, "skipped", message, last_run_date=now.date(), last_run_at=now)
        return {
            "success": True,
            "skipped": True,
            "reason": "empty-watchlist",
            "summary": message,
            "session": session_name,
            "userCount": 0,
            "results": [],
        }

    results: List[Dict[str, Any]] = []
    failures: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    for user in users:
        user_id = int(user.get("userId") or 0)
        try:
            result = _request_watchlist_review_for_user(session_name, user)
            result_payload = result.get("data") if isinstance(result.get("data"), dict) else result
            result_status = str(result_payload.get("status") or "").strip().lower() if isinstance(result_payload, dict) else ""
            if isinstance(result_payload, dict):
                if _is_watchlist_review_skipped(result_payload):
                    skipped.append({
                        "userId": user_id,
                        "message": _analysis_summary(result, session_name),
                        "status": result_status or "skipped",
                        "reason": result_payload.get("reason") or "no_targets",
                    })
                elif _is_watchlist_review_failure(result_payload):
                    failures.append({
                        "userId": user_id,
                        "message": _analysis_summary(result, session_name),
                        "status": result_status or "failed",
                    })
            results.append({
                "userId": user_id,
                "username": user.get("username"),
                "targetCount": int(user.get("targetCount") or 0),
                "reason": user.get("reason"),
                "result": result,
            })
        except Exception as exc:
            failures.append({"userId": user_id, "message": str(exc)[:220]})
            results.append({
                "userId": user_id,
                "username": user.get("username"),
                "targetCount": int(user.get("targetCount") or 0),
                "reason": user.get("reason"),
                "error": str(exc)[:500],
            })

    skipped_count = len(skipped)
    success_count = max(0, len(users) - len(failures) - skipped_count)
    if failures and success_count == 0 and skipped_count == 0:
        status = "failed"
    elif skipped_count and success_count == 0 and not failures:
        status = "skipped"
    else:
        status = "success"
    summary = (
        f"自选股 {session_name} 复核已提交，用户 {len(users)} 个，成功 {success_count} 个，跳过 {skipped_count} 个，失败 {len(failures)} 个；后台生成 AI 建议，不执行交易"
    )
    _write_job_status(
        job_name,
        status,
        summary,
        last_run_date=now.date(),
        last_run_at=now,
    )
    return {
        "success": not failures,
        "summary": summary,
        "session": session_name,
        "userCount": len(users),
        "successCount": success_count,
        "skippedCount": skipped_count,
        "failureCount": len(failures),
        "skipped": skipped,
        "failures": failures,
        "results": results,
    }


class ManagedDailyTaskRunner:
    def __init__(self, task_key: str, default_hour: int, default_minute: int, runner: Callable[[], Dict[str, Any]]) -> None:
        self.JOB_NAME = task_key
        self._default_hour = default_hour
        self._default_minute = default_minute
        self._runner = runner
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._poll_interval_seconds = 60

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name=f"{self.JOB_NAME}-scheduler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

    def run_once(self) -> Dict[str, Any]:
        return self._runner()

    def _loop(self) -> None:
        self._stop_event.wait(15)
        while not self._stop_event.is_set():
            try:
                SystemTaskService.ensure_schema()
                if SystemTaskService.is_enabled(self.JOB_NAME, default=True) and self._should_run(datetime.now()):
                    self._runner()
            except Exception:
                continue
            self._stop_event.wait(self._poll_interval_seconds)

    def _should_run(self, now: datetime) -> bool:
        hour, minute = SystemTaskService.get_daily_time(self.JOB_NAME, self._default_hour, self._default_minute)
        if (now.hour, now.minute) < (hour, minute):
            return False
        row = DbUtil.query_one("SELECT last_run_date FROM scheduled_jobs WHERE job_name = %s", (self.JOB_NAME,))
        last_run_date = _coerce_date(row[0] if row else None)
        return last_run_date != now.date()


watchlist_pre_open_review_scheduler = ManagedDailyTaskRunner(
    "watchlist_pre_open_review",
    8,
    45,
    lambda: _run_watchlist_review("pre_open"),
)
watchlist_post_close_review_scheduler = ManagedDailyTaskRunner(
    "watchlist_post_close_review",
    16,
    30,
    lambda: _run_watchlist_review("post_close"),
)


class SchedulerRuntime:
    def __init__(self) -> None:
        self._managed: Dict[str, Dict[str, Any]] = {
            "market_universe_daily_sync": {
                "title": "市场底库全量同步",
                "scope": "system",
                "scheduler": market_universe_scheduler,
            },
            "historical_market_data_daily_sync": {
                "title": "历史行情增量同步",
                "scope": "system",
                "scheduler": historical_market_data_scheduler,
            },
            "market_history_universe_backfill": {
                "title": "全市场历史慢补数",
                "scope": "system",
                "scheduler": market_history_backfill_scheduler,
            },
            "symbol_indicator_daily_refresh": {
                "title": "技术指标日刷新",
                "scope": "system",
                "scheduler": indicator_refresh_scheduler,
            },
            "daily_market_ai_scan": {
                "title": "市场 AI 技术扫描",
                "scope": "system",
                "scheduler": daily_market_scan_scheduler,
            },
            "watchlist_pre_open_review": {
                "title": "自选股盘前复核",
                "scope": "system",
                "scheduler": watchlist_pre_open_review_scheduler,
            },
            "watchlist_post_close_review": {
                "title": "自选股盘后复核",
                "scope": "system",
                "scheduler": watchlist_post_close_review_scheduler,
            },
            "daily_symbol_trend_ai_scan": {
                "title": "逐股 AI 趋势扫描",
                "scope": "system",
                "scheduler": daily_symbol_trend_scan_scheduler,
            },
            "market_insight_refresh": {
                "title": "市场动态扫描",
                "scope": "system",
                "scheduler": market_insight_scheduler,
            },
            "recommendation_refresh": {
                "title": "智能推荐刷新",
                "scope": "system",
                "scheduler": recommendation_scheduler,
            },
            "finance_briefing_refresh": {
                "title": "财经信息刷新",
                "scope": "system",
                "scheduler": finance_briefing_scheduler,
            },
            "account_asset_snapshot_refresh": {
                "title": "账户资产快照",
                "scope": "system",
                "scheduler": account_asset_snapshot_scheduler,
            },
            "position_snapshot_refresh": {
                "title": "持仓快照",
                "scope": "system",
                "scheduler": position_snapshot_scheduler,
            },
            "risk_overview_snapshot_refresh": {
                "title": "风控总览快照",
                "scope": "system",
                "scheduler": risk_overview_snapshot_scheduler,
            },
            "symbol_content_cache_refresh": {
                "title": "标的内容缓存",
                "scope": "system",
                "scheduler": symbol_content_cache_scheduler,
            },
            "quote_snapshot_refresh": {
                "title": "展示行情快照",
                "scope": "system",
                "scheduler": quote_snapshot_scheduler,
            },
            "position_monitor": {
                "title": "持仓规则监控",
                "scope": "user",
                "scheduler": position_monitor_scheduler,
            },
            "quant_trading": {
                "title": "AI 量化交易",
                "scope": "user",
                "scheduler": quant_trading_scheduler,
            },
        }

    def start_all(self) -> None:
        for meta in self._managed.values():
            meta["scheduler"].start()

    def stop_all(self) -> None:
        for meta in self._managed.values():
            meta["scheduler"].stop()

    def snapshot(self) -> Dict[str, Any]:
        services = []
        for task_key, meta in self._managed.items():
            scheduler = meta["scheduler"]
            thread = getattr(scheduler, "_thread", None)
            services.append(
                {
                    "taskKey": task_key,
                    "title": meta["title"],
                    "scope": meta["scope"],
                    "alive": bool(thread and thread.is_alive()),
                    "threadName": getattr(thread, "name", None),
                }
            )
        online = len([item for item in services if item["alive"]])
        return {
            "service": "scheduler-service",
            "managedCount": len(services),
            "aliveCount": online,
            "allAlive": online == len(services) and len(services) > 0,
            "threads": services,
        }


scheduler_runtime = SchedulerRuntime()


class SchedulerLeadership:
    LOCK_NAME = "scheduler-runtime"

    def __init__(self, runtime: SchedulerRuntime) -> None:
        self._runtime = runtime
        self._owner_id = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._lease_seconds = SCHEDULER_LEASE_SECONDS
        self._renew_interval = SCHEDULER_RENEW_INTERVAL_SECONDS
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()
        self._is_leader = False
        self._last_error: Optional[str] = None
        self._last_renew_at: Optional[str] = None

    def _fetch_lock_row(self) -> Dict[str, Any]:
        _ensure_runtime_lease_table()
        return DbUtil.fetch_one(
            """
            SELECT lock_name, owner_id, lease_until, acquired_at, updated_at
            FROM scheduler_runtime_leases
            WHERE lock_name = %s
            LIMIT 1
            """,
            (self.LOCK_NAME,),
        ) or {}

    def _set_leader_state(self, is_leader: bool) -> None:
        with self._lock:
            if self._is_leader == is_leader:
                return
            self._is_leader = is_leader
            if is_leader:
                self._runtime.start_all()
            else:
                self._runtime.stop_all()

    def _acquire_or_renew(self) -> bool:
        _ensure_runtime_lease_table()
        DbUtil.execute_sql(
            """
            INSERT INTO scheduler_runtime_leases (lock_name, owner_id, lease_until, acquired_at, updated_at)
            VALUES (%s, %s, DATE_ADD(UTC_TIMESTAMP(), INTERVAL %s SECOND), UTC_TIMESTAMP(), UTC_TIMESTAMP())
            ON DUPLICATE KEY UPDATE
                owner_id = IF(
                    owner_id = VALUES(owner_id) OR lease_until IS NULL OR lease_until < UTC_TIMESTAMP(),
                    VALUES(owner_id),
                    owner_id
                ),
                lease_until = IF(
                    owner_id = VALUES(owner_id) OR lease_until IS NULL OR lease_until < UTC_TIMESTAMP(),
                    VALUES(lease_until),
                    lease_until
                ),
                acquired_at = IF(
                    owner_id = VALUES(owner_id) OR lease_until IS NULL OR lease_until < UTC_TIMESTAMP(),
                    UTC_TIMESTAMP(),
                    acquired_at
                ),
                updated_at = CURRENT_TIMESTAMP
            """,
            (self.LOCK_NAME, self._owner_id, self._lease_seconds),
        )
        row = self._fetch_lock_row()
        is_leader = str(row.get("owner_id") or "") == self._owner_id
        if is_leader:
            lease_until = row.get("lease_until")
            self._last_renew_at = _format_datetime(lease_until)
        return is_leader

    def _release(self) -> None:
        _ensure_runtime_lease_table()
        DbUtil.execute_sql(
            """
            UPDATE scheduler_runtime_leases
            SET owner_id = NULL,
                lease_until = UTC_TIMESTAMP(),
                updated_at = CURRENT_TIMESTAMP
            WHERE lock_name = %s AND owner_id = %s
            """,
            (self.LOCK_NAME, self._owner_id),
        )

    def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._set_leader_state(self._acquire_or_renew())
                self._last_error = None
            except Exception as exc:
                self._last_error = str(exc)
                self._set_leader_state(False)
            self._stop_event.wait(self._renew_interval)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name="scheduler-leadership", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._set_leader_state(False)
        try:
            self._release()
        except Exception as exc:
            self._last_error = str(exc)

    def snapshot(self) -> Dict[str, Any]:
        row = self._fetch_lock_row()
        lease_until = row.get("lease_until")
        return {
            "lockName": self.LOCK_NAME,
            "ownerId": self._owner_id,
            "currentOwnerId": row.get("owner_id"),
            "isLeader": bool(self._is_leader),
            "leaseSeconds": self._lease_seconds,
            "renewIntervalSeconds": self._renew_interval,
            "leaseUntil": _format_datetime(lease_until),
            "acquiredAt": _format_datetime(row.get("acquired_at")),
            "updatedAt": _format_datetime(row.get("updated_at")),
            "lastRenewAt": self._last_renew_at,
            "managerRunning": bool(self._thread and self._thread.is_alive()),
            "lastError": self._last_error,
        }


scheduler_leadership = SchedulerLeadership(scheduler_runtime)


def _build_task_snapshot(task_key: str, user_id: int) -> Dict[str, Any]:
    policy = SystemTaskService.get_policy(task_key)
    if not policy:
        raise HTTPException(status_code=404, detail="未找到任务策略")
    job_name = _user_scoped_job_name(task_key, user_id)
    runtime_item = next(
        (item for item in scheduler_runtime.snapshot()["threads"] if item["taskKey"] == task_key),
        None,
    )
    return {
        **policy,
        "jobName": job_name,
        "status": _job_status(job_name),
        "runtime": runtime_item or {"taskKey": task_key, "alive": False},
    }


def _list_task_snapshots(user_id: int, session: dict) -> List[Dict[str, Any]]:
    SystemTaskService.ensure_schema()
    tasks = []
    for task_key in SystemTaskService.DEFAULT_POLICIES.keys():
        policy = SystemTaskService.get_policy(task_key)
        if not policy:
            continue
        if policy.get("userScope") == "system" and not _is_admin(session):
            continue
        tasks.append(_build_task_snapshot(task_key, user_id))
    return tasks


def _recent_jobs(user_id: int, session: dict, limit: int = 20) -> List[Dict[str, Any]]:
    _ensure_job_table()
    rows = DbUtil.fetch_all(
        """
        SELECT job_name, last_run_date, last_run_at, status, message, updated_at
        FROM scheduled_jobs
        ORDER BY COALESCE(last_run_at, updated_at) DESC
        LIMIT %s
        """,
        (max(1, min(int(limit or 20), 120)),),
    ) or []

    allowed_job_names = None
    if not _is_admin(session):
        allowed_job_names = {
            _user_scoped_job_name("position_monitor", user_id),
            _user_scoped_job_name("quant_trading", user_id),
        }

    items = []
    for row in rows:
        job_name = row.get("job_name") or ""
        if allowed_job_names is not None and job_name not in allowed_job_names:
            continue
        items.append(
            {
                "jobName": job_name,
                "lastRunDate": row.get("last_run_date").strftime("%Y-%m-%d") if row.get("last_run_date") else None,
                "lastRunAt": _format_datetime(row.get("last_run_at")),
                "state": row.get("status") or "idle",
                "message": row.get("message") or "",
                "updatedAt": _format_datetime(row.get("updated_at")),
            }
        )
    return items


def _assert_task_access(session: dict, task_key: str) -> Dict[str, Any]:
    policy = SystemTaskService.get_policy(task_key)
    if not policy:
        raise HTTPException(status_code=404, detail="未找到任务策略")
    if policy.get("userScope") == "system" and not _is_admin(session):
        raise HTTPException(status_code=403, detail="当前用户无权管理系统级调度任务")
    return policy


def _run_market_universe(user_id: int) -> Dict[str, Any]:
    market_universe_scheduler._ensure_job_table()  # noqa: SLF001
    markets = market_universe_scheduler._get_markets()  # noqa: SLF001
    from datetime import datetime

    started_at = datetime.now()
    market_universe_scheduler._update_job_status("running", f"准备同步市场: {', '.join(markets)}")  # noqa: SLF001
    result = MarketUniverseSync.sync_markets(markets=markets, user_id=user_id)
    market_universe_scheduler._update_job_status(  # noqa: SLF001
        "success",
        f"同步完成，写入 {int(result.get('total_saved', 0))} 条，耗时 {result.get('duration_seconds', 0)} 秒",
        last_run_date=started_at.date(),
        last_run_at=started_at,
    )
    return result


def _run_historical_sync() -> Dict[str, Any]:
    from datetime import datetime
    from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService

    historical_market_data_scheduler._ensure_job_table()  # noqa: SLF001
    historical_market_data_scheduler._update_job_status("running", "历史行情同步启动中")  # noqa: SLF001
    result = HistoricalMarketDataService.sync_tracked_universe()
    historical_market_data_scheduler._update_job_status(  # noqa: SLF001
        "success",
        f"同步 {result.get('symbol_count', 0)} 个标的，写入 {result.get('saved_count', 0)} 条K线",
        last_run_date=datetime.now().date(),
        last_run_at=datetime.now(),
    )
    return result


def _run_indicator_refresh() -> Dict[str, Any]:
    from datetime import datetime
    from core.analysis.IndicatorSnapshotService import IndicatorSnapshotService

    indicator_refresh_scheduler._ensure_job_table()  # noqa: SLF001
    policy = SystemTaskService.get_policy(indicator_refresh_scheduler.JOB_NAME)
    settings = policy.get("settings") or {}
    cursor = int(settings.get("cursor") or 0)
    batch_size = max(500, SystemTaskService.get_batch_size(indicator_refresh_scheduler.JOB_NAME, 1500))
    indicator_refresh_scheduler._update_job("running", f"技术指标刷新中，cursor={cursor} batch={batch_size}")  # noqa: SLF001
    result = IndicatorSnapshotService.refresh_universe(batch_size=batch_size, cursor=cursor)
    next_cursor = 0 if not result.get("hasMore") else int(result.get("nextCursor") or 0)
    SystemTaskService.update_policy(
        indicator_refresh_scheduler.JOB_NAME,
        {
            "settings": {
                "cursor": next_cursor,
                "lastProcessed": int(result.get("processed") or 0),
                "lastFailed": len(result.get("failed") or []),
            }
        },
    )
    indicator_refresh_scheduler._update_job(  # noqa: SLF001
        "success",
        f"已生成 {result.get('processed', 0)} 个标的指标，nextCursor={next_cursor}",
        last_run_date=datetime.now().date(),
        last_run_at=datetime.now(),
    )
    return result


def _run_market_scan(user_id: Optional[int] = None) -> Dict[str, Any]:
    from datetime import datetime
    from core.analysis.DailyMarketScanService import DailyMarketScanService

    daily_market_scan_scheduler._ensure_job_table()  # noqa: SLF001
    daily_market_scan_scheduler._update_job("running", "市场 AI 技术扫描启动中")  # noqa: SLF001
    execution_user = _resolve_task_execution_user(daily_market_scan_scheduler.JOB_NAME, user_id)
    if not execution_user:
        message = "市场 AI 技术扫描已跳过：没有可用的执行用户"
        daily_market_scan_scheduler._update_job(  # noqa: SLF001
            "skipped",
            message,
            last_run_date=datetime.now().date(),
            last_run_at=datetime.now(),
        )
        return {
            "success": True,
            "skipped": True,
            "reason": "no-execution-user",
            "summary": message,
            "markets": [],
        }

    execution_user_id = int(execution_user["userId"])
    result = DailyMarketScanService.refresh_all_markets(user_id=execution_user_id)
    result["executionUser"] = {
        "userId": execution_user_id,
        "username": execution_user.get("username"),
        "reason": execution_user.get("reason"),
    }
    daily_market_scan_scheduler._update_job(  # noqa: SLF001
        "success",
        f"已完成 {len(result.get('markets', []))} 个市场技术扫描，执行用户 {execution_user.get('username') or execution_user_id}",
        last_run_date=datetime.now().date(),
        last_run_at=datetime.now(),
    )
    return result


def _run_market_insight(user_id: int) -> Dict[str, Any]:
    from core.analysis.MarketInsightService import MarketInsightService

    result = MarketInsightService.refresh_all_markets(user_id=user_id, source="manual")
    market_insight_scheduler._update_job("success", "市场动态已刷新")  # noqa: SLF001
    return result


def _run_recommendation_refresh(user_id: int) -> Dict[str, Any]:
    from core.analysis.RecommendationService import RecommendationService

    RecommendationService.refresh_all_profiles(user_id=user_id)
    recommendation_scheduler._update_job("success", "推荐结果已刷新")  # noqa: SLF001
    return {"refreshed": True}


def _run_finance_briefing(user_id: int) -> Dict[str, Any]:
    from datetime import datetime
    from core.analysis.FinanceBriefingService import FinanceBriefingService

    finance_briefing_scheduler._ensure_job_table()  # noqa: SLF001
    result = FinanceBriefingService.refresh_all_markets(user_id=user_id)
    finance_briefing_scheduler._update_job(  # noqa: SLF001
        "success",
        f"已生成 {len(result.get('items', []))} 条财经信息",
        last_run_date=datetime.now().date(),
        last_run_at=datetime.now(),
    )
    return result


def _run_account_asset_snapshot_refresh(user_id: int) -> Dict[str, Any]:
    snapshots = AccountAssetSnapshotService.refresh_for_user(user_id=user_id, source="scheduler")
    _write_job_status(
        "account_asset_snapshot_refresh",
        "success",
        f"已写入 {len(snapshots)} 个账户资产快照",
        last_run_date=datetime.now().date(),
        last_run_at=datetime.now(),
    )
    return {"snapshots": snapshots, "count": len(snapshots)}


def _run_position_snapshot_refresh(user_id: int) -> Dict[str, Any]:
    snapshots = PositionSnapshotService.refresh_for_user(user_id=user_id, source="scheduler")
    position_count = sum(len(items) for items in snapshots.values())
    _write_job_status(
        "position_snapshot_refresh",
        "success",
        f"已写入 {position_count} 条持仓快照",
        last_run_date=datetime.now().date(),
        last_run_at=datetime.now(),
    )
    return {"accounts": len(snapshots), "positionCount": position_count}


def _run_risk_overview_snapshot_refresh(user_id: int) -> Dict[str, Any]:
    from core.broker.BrokerInterface import get_broker_manager

    saved = 0
    overall_payload = build_risk_overview(user_id=user_id, account_id=None)
    RiskOverviewSnapshotService.save_snapshot(
        user_id=user_id,
        account_id=None,
        payload=overall_payload,
        source="scheduler",
    )
    saved += 1

    for account in get_broker_manager().list_accounts(user_id=user_id) or []:
        account_id = int(account.get("id") or 0)
        if account_id <= 0:
            continue
        try:
            payload = build_risk_overview(user_id=user_id, account_id=account_id)
            RiskOverviewSnapshotService.save_snapshot(
                user_id=user_id,
                account_id=account_id,
                payload=payload,
                source="scheduler",
            )
            saved += 1
        except Exception:
            continue

    _write_job_status(
        "risk_overview_snapshot_refresh",
        "success",
        f"已写入 {saved} 份风控总览快照",
        last_run_date=datetime.now().date(),
        last_run_at=datetime.now(),
    )
    return {"count": saved}


def _run_symbol_content_cache_refresh(user_id: int) -> Dict[str, Any]:
    from core.analysis.MarketInsightService import MarketInsightService
    from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService

    quote_ctx = build_quote_context(user_id=user_id, region=resolve_region())
    content_ctx = build_content_context(user_id=user_id, region=resolve_region())

    symbols: List[str] = []
    for items in MarketInsightService.BENCHMARKS.values():
        for item in items[:3]:
            symbol = HistoricalMarketDataService.normalize_symbol(item.get("symbol"))
            if symbol and symbol not in symbols:
                symbols.append(symbol)

    saved = 0
    for symbol in symbols[:9]:
        market = HistoricalMarketDataService.detect_market(symbol)
        try:
            if hasattr(quote_ctx, "filings"):
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

    _write_job_status(
        "symbol_content_cache_refresh",
        "success",
        f"已写入 {saved} 条标的内容缓存",
        last_run_date=datetime.now().date(),
        last_run_at=datetime.now(),
    )
    return {"symbolCount": len(symbols[:9]), "savedCount": saved}


TASK_RUNNERS: Dict[str, Callable[[int], Dict[str, Any]]] = {
    "market_universe_daily_sync": _run_market_universe,
    "historical_market_data_daily_sync": lambda user_id: _run_historical_sync(),
    "market_history_universe_backfill": lambda user_id: market_history_backfill_scheduler.run_once(),
    "symbol_indicator_daily_refresh": lambda user_id: _run_indicator_refresh(),
    "daily_market_ai_scan": lambda user_id: _run_market_scan(user_id),
    "watchlist_pre_open_review": lambda user_id: watchlist_pre_open_review_scheduler.run_once(),
    "watchlist_post_close_review": lambda user_id: watchlist_post_close_review_scheduler.run_once(),
    "daily_symbol_trend_ai_scan": lambda user_id: daily_symbol_trend_scan_scheduler.run_once(),
    "market_insight_refresh": _run_market_insight,
    "recommendation_refresh": _run_recommendation_refresh,
    "finance_briefing_refresh": _run_finance_briefing,
    "account_asset_snapshot_refresh": _run_account_asset_snapshot_refresh,
    "position_snapshot_refresh": _run_position_snapshot_refresh,
    "risk_overview_snapshot_refresh": _run_risk_overview_snapshot_refresh,
    "symbol_content_cache_refresh": _run_symbol_content_cache_refresh,
    "position_monitor": lambda user_id: StrategyMonitorService.run_monitor(user_id=user_id, source="manual"),
    "quant_trading": lambda user_id: QuantTradingService.run_cycle(user_id=user_id, source="manual", execute=False),
    "bootstrap_market_history_2024": lambda user_id: MarketHistoryBootstrapService.run_once(
        user_id=user_id,
        batch_size=SystemTaskService.get_batch_size("bootstrap_market_history_2024", 160),
    ),
}


@asynccontextmanager
async def lifespan(_: Any):
    SystemTaskService.ensure_schema()
    _ensure_job_table()
    _ensure_runtime_lease_table()
    scheduler_leadership.start()
    try:
        yield
    finally:
        scheduler_leadership.stop()


app.router.lifespan_context = lifespan


@app.get("/health")
async def health():
    runtime = scheduler_runtime.snapshot()
    leadership = scheduler_leadership.snapshot()
    mysql_ok = bool(DbUtil.query_one("SELECT 1"))
    runtime_running = bool(runtime.get("allAlive"))
    is_leader = bool(leadership.get("isLeader"))
    deps = {
        "mysql": build_dependency_status("mysql", "healthy" if mysql_ok else "degraded", detail="调度任务、租约与执行状态存储"),
        "runtime": build_dependency_status(
            "runtime",
            "healthy" if runtime_running else "degraded",
            detail="调度线程运行状态",
            observed={"isLeader": is_leader, "jobCount": runtime.get("jobCount")},
        ),
    }
    alerts = []
    if not runtime_running:
        alerts.append(build_alert("scheduler-runtime-stopped", "warning", "调度线程未运行", action="检查调度租约和 runtime/start 接口"))
    if leadership and not is_leader:
        alerts.append(build_alert("scheduler-follower", "info", "当前实例不是调度 leader，部分任务不会在本实例执行"))
    return build_health_payload(
        service="scheduler-service",
        version=app.version,
        port=PORT,
        status=summarize_status(deps.values()),
        deps=deps,
        alerts=alerts,
        capabilities=["task-orchestration", "job-retry", "scheduler-runtime"],
        extra={
            "runtime": runtime,
            "leadership": leadership,
        },
    )


@app.get("/api/v1/scheduler/bootstrap")
async def bootstrap_scheduler(
    limit: int = Query(default=16, ge=1, le=100),
    session: dict = Depends(get_current_session),
):
    user_id = int(session["user_id"])
    return {
        "success": True,
        "data": {
            "service": "scheduler-service",
            "status": "live",
            "runtime": scheduler_runtime.snapshot(),
            "leadership": scheduler_leadership.snapshot(),
            "tasks": _list_task_snapshots(user_id, session),
            "recentJobs": _recent_jobs(user_id, session, limit=limit),
            "legacySources": [
                "refactor-v2/backend-server/src/core/platform/SystemTaskService.py",
                "refactor-v2/backend-server/src/core/analysis/*Scheduler.py",
                "refactor-v2/backend-server/src/api/platform_routes.py",
            ],
        },
    }


@app.get("/api/v1/scheduler/runtime")
async def scheduler_runtime_status(session: dict = Depends(get_current_session)):
    if not _is_admin(session):
        raise HTTPException(status_code=403, detail="当前用户无权查看系统调度运行时状态")
    return {"success": True, "data": {"runtime": scheduler_runtime.snapshot(), "leadership": scheduler_leadership.snapshot()}}


@app.post("/api/v1/scheduler/runtime/start")
async def start_scheduler_runtime(session: dict = Depends(get_current_session)):
    if not _is_admin(session):
        raise HTTPException(status_code=403, detail="当前用户无权启动系统调度运行时")
    scheduler_leadership.start()
    return {
        "success": True,
        "message": "调度领导选举已启动，当前实例获取租约后会自动拉起线程",
        "data": {"runtime": scheduler_runtime.snapshot(), "leadership": scheduler_leadership.snapshot()},
    }


@app.post("/api/v1/scheduler/runtime/stop")
async def stop_scheduler_runtime(session: dict = Depends(get_current_session)):
    if not _is_admin(session):
        raise HTTPException(status_code=403, detail="当前用户无权停止系统调度运行时")
    scheduler_leadership.stop()
    return {
        "success": True,
        "message": "调度领导租约已释放，本实例线程已停止",
        "data": {"runtime": scheduler_runtime.snapshot(), "leadership": scheduler_leadership.snapshot()},
    }


@app.get("/api/v1/scheduler/tasks")
async def list_scheduler_tasks(session: dict = Depends(get_current_session)):
    return {"success": True, "data": _list_task_snapshots(int(session["user_id"]), session)}


@app.put("/api/v1/scheduler/tasks/{task_key}")
async def update_scheduler_task(
    task_key: str,
    payload: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _assert_task_access(session, task_key)
    SystemTaskService.update_policy(task_key, payload)
    return {
        "success": True,
        "message": "任务策略已更新",
        "data": _build_task_snapshot(task_key, int(session["user_id"])),
    }


@app.post("/api/v1/scheduler/tasks/{task_key}/run")
async def run_scheduler_task(
    task_key: str,
    _: dict = Body(default={}),
    session: dict = Depends(get_current_session),
):
    _assert_task_access(session, task_key)
    runner = TASK_RUNNERS.get(task_key)
    if runner is None:
        raise HTTPException(status_code=400, detail="暂不支持的任务")
    result = runner(int(session["user_id"]))
    return {
        "success": True,
        "message": "任务已执行",
        "data": {
            "result": result,
            "task": _build_task_snapshot(task_key, int(session["user_id"])),
        },
    }


@app.get("/api/v1/scheduler/jobs")
async def list_scheduler_jobs(
    limit: int = Query(default=20, ge=1, le=120),
    session: dict = Depends(get_current_session),
):
    return {"success": True, "data": _recent_jobs(int(session["user_id"]), session, limit=limit)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
