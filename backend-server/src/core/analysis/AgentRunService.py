from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from typing import Any

from utils.DbUtil import DbUtil


class AgentRunService:
    """
    Multi-agent 治理存储服务。

    该服务只负责运行/步骤/人工覆盖的审计落库，不接任何交易执行接口。
    """

    RUNS_TABLE = "agent_runs"
    STEPS_TABLE = "agent_steps"
    OVERRIDES_TABLE = "agent_human_overrides"

    RUN_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}
    OVERRIDE_ACTIONS = {"acknowledged", "needs_review", "dismissed"}
    OVERRIDE_ALLOWED_NEW_STATUSES = {
        "acknowledged": {"succeeded"},
        "needs_review": {"failed"},
        "dismissed": {"cancelled"},
    }

    MAX_SCENE_LENGTH = 64
    MAX_TRIGGER_SOURCE_LENGTH = 64
    MAX_STATUS_LENGTH = 16
    MAX_STEP_NAME_LENGTH = 128
    MAX_MODEL_TIER_LENGTH = 64
    MAX_HANDOFF_LENGTH = 128
    MAX_TRACE_REF_LENGTH = 255
    MAX_ACTOR_LENGTH = 64
    MAX_ACTION_LENGTH = 64

    MAX_SUMMARY_LENGTH = 4000
    MAX_ERROR_LENGTH = 2000
    MAX_REASON_LENGTH = 1000
    MAX_REVIEW_NOTE_LENGTH = 2000

    SENSITIVE_KEYWORDS = (
        "api_key",
        "apikey",
        "secret",
        "token",
        "password",
        "passwd",
        "authorization",
        "cookie",
        "credential",
        "private_key",
        "access_key",
        "refresh_token",
        "session_key",
        "prompt",
        "messages",
        "instruction",
    )

    SENSITIVE_VALUE_PATTERNS = (
        re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/=]+"),
        re.compile(r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b\s*[:=]\s*([^\s,;\"']+)"),
        re.compile(r"(?i)\b(sk-[A-Za-z0-9]{12,}|AIza[0-9A-Za-z\-_]{16,}|ya29\.[0-9A-Za-z\-_]+)\b"),
    )

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.RUNS_TABLE} (
                run_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                scene VARCHAR({cls.MAX_SCENE_LENGTH}) NOT NULL,
                trigger_source VARCHAR({cls.MAX_TRIGGER_SOURCE_LENGTH}) NOT NULL,
                user_id INT NOT NULL,
                status VARCHAR({cls.MAX_STATUS_LENGTH}) NOT NULL DEFAULT 'queued',
                input_summary TEXT,
                result_summary TEXT,
                error_summary TEXT,
                trace_ref VARCHAR({cls.MAX_TRACE_REF_LENGTH}) DEFAULT NULL,
                started_at DATETIME DEFAULT NULL,
                finished_at DATETIME DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_agent_runs_scene_created (scene, created_at),
                INDEX idx_agent_runs_user_created (user_id, created_at),
                INDEX idx_agent_runs_status_created (status, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.STEPS_TABLE} (
                step_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                run_id BIGINT NOT NULL,
                step_name VARCHAR({cls.MAX_STEP_NAME_LENGTH}) NOT NULL,
                status VARCHAR({cls.MAX_STATUS_LENGTH}) NOT NULL DEFAULT 'queued',
                input_summary TEXT,
                output_summary TEXT,
                model_tier VARCHAR({cls.MAX_MODEL_TIER_LENGTH}) DEFAULT NULL,
                handoff VARCHAR({cls.MAX_HANDOFF_LENGTH}) DEFAULT NULL,
                latency_ms INT DEFAULT NULL,
                token_count INT DEFAULT NULL,
                cost_estimate DECIMAL(16, 6) DEFAULT NULL,
                prompt_trace_ref VARCHAR({cls.MAX_TRACE_REF_LENGTH}) DEFAULT NULL,
                error_summary TEXT,
                started_at DATETIME DEFAULT NULL,
                finished_at DATETIME DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_agent_steps_run_created (run_id, created_at),
                INDEX idx_agent_steps_run_status (run_id, status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.OVERRIDES_TABLE} (
                override_id BIGINT AUTO_INCREMENT PRIMARY KEY,
                run_id BIGINT NOT NULL,
                user_id INT NOT NULL,
                actor VARCHAR({cls.MAX_ACTOR_LENGTH}) NOT NULL,
                action VARCHAR({cls.MAX_ACTION_LENGTH}) NOT NULL,
                reason VARCHAR({cls.MAX_REASON_LENGTH}) DEFAULT NULL,
                old_status VARCHAR({cls.MAX_STATUS_LENGTH}) DEFAULT NULL,
                new_status VARCHAR({cls.MAX_STATUS_LENGTH}) DEFAULT NULL,
                review_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_agent_overrides_run_created (run_id, created_at),
                INDEX idx_agent_overrides_user_created (user_id, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def create_run(
        cls,
        *,
        scene: str,
        trigger_source: str,
        user_id: int,
        status: str = "queued",
        input_summary: Any | None = None,
        result_summary: Any | None = None,
        error_summary: Any | None = None,
        trace_ref: str | None = None,
        started_at: Any | None = None,
        finished_at: Any | None = None,
    ) -> int:
        cls.ensure_schema()
        safe_status = cls._validate_status(status)
        safe_started_at = cls._coerce_datetime(started_at)
        safe_finished_at = cls._coerce_datetime(finished_at)

        if safe_status == "running" and safe_started_at is None:
            safe_started_at = datetime.now()
        if safe_status in {"succeeded", "failed", "cancelled"}:
            if safe_started_at is None:
                safe_started_at = datetime.now()
            if safe_finished_at is None:
                safe_finished_at = datetime.now()

        return DbUtil.execute_insert(
            f"""
            INSERT INTO {cls.RUNS_TABLE} (
                scene, trigger_source, user_id, status, input_summary,
                result_summary, error_summary, trace_ref, started_at, finished_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                cls._clean_text(scene, cls.MAX_SCENE_LENGTH),
                cls._clean_text(trigger_source, cls.MAX_TRIGGER_SOURCE_LENGTH),
                int(user_id),
                safe_status,
                cls._serialize_summary(input_summary, cls.MAX_SUMMARY_LENGTH),
                cls._serialize_summary(result_summary, cls.MAX_SUMMARY_LENGTH),
                cls._serialize_summary(error_summary, cls.MAX_ERROR_LENGTH),
                cls._clean_text(trace_ref, cls.MAX_TRACE_REF_LENGTH),
                safe_started_at,
                safe_finished_at,
            ),
        )

    @classmethod
    def mark_run_running(
        cls,
        run_id: int,
        *,
        input_summary: Any | None = None,
        trace_ref: str | None = None,
        started_at: Any | None = None,
    ) -> dict[str, Any] | None:
        cls.ensure_schema()
        safe_started_at = cls._coerce_datetime(started_at) or datetime.now()
        DbUtil.execute_sql(
            f"""
            UPDATE {cls.RUNS_TABLE}
            SET status = %s,
                input_summary = COALESCE(%s, input_summary),
                trace_ref = COALESCE(%s, trace_ref),
                started_at = COALESCE(started_at, %s),
                updated_at = CURRENT_TIMESTAMP
            WHERE run_id = %s
            """,
            (
                "running",
                cls._serialize_summary(input_summary, cls.MAX_SUMMARY_LENGTH),
                cls._clean_text(trace_ref, cls.MAX_TRACE_REF_LENGTH),
                safe_started_at,
                int(run_id),
            ),
        )
        return cls.get_run(int(run_id), use_primary=True)

    @classmethod
    def claim_run(
        cls,
        run_id: int,
        *,
        input_summary: Any | None = None,
        trace_ref: str | None = None,
        started_at: Any | None = None,
    ) -> bool:
        cls.ensure_schema()
        safe_started_at = cls._coerce_datetime(started_at) or datetime.now()
        affected = DbUtil.execute_sql(
            f"""
            UPDATE {cls.RUNS_TABLE}
            SET status = %s,
                input_summary = COALESCE(%s, input_summary),
                trace_ref = COALESCE(%s, trace_ref),
                started_at = COALESCE(started_at, %s),
                updated_at = CURRENT_TIMESTAMP
            WHERE run_id = %s AND status = %s
            """,
            (
                "running",
                cls._serialize_summary(input_summary, cls.MAX_SUMMARY_LENGTH),
                cls._clean_text(trace_ref, cls.MAX_TRACE_REF_LENGTH),
                safe_started_at,
                int(run_id),
                "queued",
            ),
        )
        return int(affected or 0) > 0

    @classmethod
    def complete_run(
        cls,
        run_id: int,
        *,
        result_summary: Any | None = None,
        trace_ref: str | None = None,
        finished_at: Any | None = None,
    ) -> dict[str, Any] | None:
        cls.ensure_schema()
        safe_finished_at = cls._coerce_datetime(finished_at) or datetime.now()
        DbUtil.execute_sql(
            f"""
            UPDATE {cls.RUNS_TABLE}
            SET status = %s,
                result_summary = COALESCE(%s, result_summary),
                error_summary = NULL,
                trace_ref = COALESCE(%s, trace_ref),
                started_at = COALESCE(started_at, created_at),
                finished_at = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE run_id = %s
            """,
            (
                "succeeded",
                cls._serialize_summary(result_summary, cls.MAX_SUMMARY_LENGTH),
                cls._clean_text(trace_ref, cls.MAX_TRACE_REF_LENGTH),
                safe_finished_at,
                int(run_id),
            ),
        )
        return cls.get_run(int(run_id), use_primary=True)

    @classmethod
    def fail_run(
        cls,
        run_id: int,
        *,
        error_summary: Any | None = None,
        trace_ref: str | None = None,
        finished_at: Any | None = None,
        status: str = "failed",
    ) -> dict[str, Any] | None:
        cls.ensure_schema()
        safe_status = cls._validate_status(status)
        if safe_status not in {"failed", "cancelled"}:
            raise ValueError("run failure status must be failed or cancelled")
        safe_finished_at = cls._coerce_datetime(finished_at) or datetime.now()
        DbUtil.execute_sql(
            f"""
            UPDATE {cls.RUNS_TABLE}
            SET status = %s,
                error_summary = COALESCE(%s, error_summary),
                trace_ref = COALESCE(%s, trace_ref),
                started_at = COALESCE(started_at, created_at),
                finished_at = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE run_id = %s
            """,
            (
                safe_status,
                cls._serialize_summary(error_summary, cls.MAX_ERROR_LENGTH),
                cls._clean_text(trace_ref, cls.MAX_TRACE_REF_LENGTH),
                safe_finished_at,
                int(run_id),
            ),
        )
        return cls.get_run(int(run_id), use_primary=True)

    @classmethod
    def cancel_stale_runs(
        cls,
        *,
        max_age_minutes: int = 60,
        scene_prefix: str | None = "watchlist_",
        reason: Any | None = None,
    ) -> int:
        cls.ensure_schema()
        safe_minutes = max(5, min(int(max_age_minutes or 60), 24 * 60))
        reason_payload = reason or {
            "code": "agent_run_stranded",
            "message": f"analysis-service startup cleanup cancelled queued/running runs older than {safe_minutes} minutes",
        }
        conditions = ["status IN (%s, %s)", "updated_at < DATE_SUB(NOW(), INTERVAL %s MINUTE)"]
        params: list[Any] = ["queued", "running", safe_minutes]
        if scene_prefix:
            conditions.append("scene LIKE %s")
            params.append(f"{str(scene_prefix)}%")
        affected = DbUtil.execute_sql(
            f"""
            UPDATE {cls.RUNS_TABLE}
            SET status = %s,
                error_summary = COALESCE(error_summary, %s),
                finished_at = COALESCE(finished_at, NOW()),
                updated_at = CURRENT_TIMESTAMP
            WHERE {' AND '.join(conditions)}
            """,
            tuple(
                [
                    "cancelled",
                    cls._serialize_summary(reason_payload, cls.MAX_ERROR_LENGTH),
                    *params,
                ]
            ),
        )
        return int(affected or 0)

    @classmethod
    def record_step(
        cls,
        *,
        run_id: int,
        step_name: str,
        status: str,
        input_summary: Any | None = None,
        output_summary: Any | None = None,
        model_tier: str | None = None,
        handoff: str | None = None,
        latency_ms: Any | None = None,
        token_count: Any | None = None,
        cost_estimate: Any | None = None,
        prompt_trace_ref: str | None = None,
        error_summary: Any | None = None,
        started_at: Any | None = None,
        finished_at: Any | None = None,
    ) -> int:
        cls.ensure_schema()
        safe_status = cls._validate_status(status)
        safe_started_at = cls._coerce_datetime(started_at)
        safe_finished_at = cls._coerce_datetime(finished_at)

        if safe_status == "running" and safe_started_at is None:
            safe_started_at = datetime.now()
        if safe_status in {"succeeded", "failed", "cancelled"}:
            if safe_started_at is None:
                safe_started_at = datetime.now()
            if safe_finished_at is None:
                safe_finished_at = datetime.now()

        return DbUtil.execute_insert(
            f"""
            INSERT INTO {cls.STEPS_TABLE} (
                run_id, step_name, status, input_summary, output_summary,
                model_tier, handoff, latency_ms, token_count, cost_estimate,
                prompt_trace_ref, error_summary, started_at, finished_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(run_id),
                cls._clean_text(step_name, cls.MAX_STEP_NAME_LENGTH),
                safe_status,
                cls._serialize_summary(input_summary, cls.MAX_SUMMARY_LENGTH),
                cls._serialize_summary(output_summary, cls.MAX_SUMMARY_LENGTH),
                cls._clean_text(model_tier, cls.MAX_MODEL_TIER_LENGTH),
                cls._clean_text(handoff, cls.MAX_HANDOFF_LENGTH),
                cls._coerce_int(latency_ms),
                cls._coerce_int(token_count),
                cls._coerce_decimal(cost_estimate),
                cls._clean_text(prompt_trace_ref, cls.MAX_TRACE_REF_LENGTH),
                cls._serialize_summary(error_summary, cls.MAX_ERROR_LENGTH),
                safe_started_at,
                safe_finished_at,
            ),
        )

    @classmethod
    def record_override(
        cls,
        *,
        run_id: int,
        user_id: int,
        actor: str,
        action: str,
        reason: Any | None = None,
        old_status: str | None = None,
        new_status: str | None = None,
        review_note: Any | None = None,
    ) -> int:
        cls.ensure_schema()
        safe_action = cls._validate_override_action(action)
        safe_old_status = cls._validate_optional_status(old_status)
        safe_new_status = cls._validate_override_new_status(safe_action, new_status)
        override_id = DbUtil.execute_insert(
            f"""
            INSERT INTO {cls.OVERRIDES_TABLE} (
                run_id, user_id, actor, action, reason,
                old_status, new_status, review_note
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                int(run_id),
                int(user_id),
                cls._clean_text(actor, cls.MAX_ACTOR_LENGTH),
                safe_action,
                cls._serialize_summary(reason, cls.MAX_REASON_LENGTH),
                safe_old_status,
                safe_new_status,
                cls._serialize_summary(review_note, cls.MAX_REVIEW_NOTE_LENGTH),
            ),
        )
        if safe_new_status:
            DbUtil.execute_sql(
                f"""
                UPDATE {cls.RUNS_TABLE}
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE run_id = %s
                """,
                (safe_new_status, int(run_id)),
            )
        return override_id

    @classmethod
    def get_run(cls, run_id: int, use_primary: bool = False) -> dict[str, Any] | None:
        cls.ensure_schema()
        fetch_one = DbUtil.fetch_one_primary if use_primary else DbUtil.fetch_one
        fetch_all = DbUtil.fetch_all_primary if use_primary else DbUtil.fetch_all

        run_row = fetch_one(
            f"""
            SELECT *
            FROM {cls.RUNS_TABLE}
            WHERE run_id = %s
            LIMIT 1
            """,
            (int(run_id),),
        )
        if not run_row:
            return None

        step_rows = (
            fetch_all(
                f"""
            SELECT *
            FROM {cls.STEPS_TABLE}
            WHERE run_id = %s
            ORDER BY created_at ASC, step_id ASC
            """,
                (int(run_id),),
            )
            or []
        )
        override_rows = (
            fetch_all(
                f"""
            SELECT *
            FROM {cls.OVERRIDES_TABLE}
            WHERE run_id = %s
            ORDER BY created_at ASC, override_id ASC
            """,
                (int(run_id),),
            )
            or []
        )

        data = cls._normalize_run_row(run_row)
        data["steps"] = [cls._normalize_step_row(row) for row in step_rows]
        data["overrides"] = [cls._normalize_override_row(row) for row in override_rows]
        cls._attach_review_state(data)
        return data

    @classmethod
    def list_recent_runs(
        cls,
        *,
        limit: int = 20,
        scene: str | None = None,
        user_id: int | None = None,
        status: str | None = None,
        use_primary: bool = False,
    ) -> list[dict[str, Any]]:
        cls.ensure_schema()
        fetch_all = DbUtil.fetch_all_primary if use_primary else DbUtil.fetch_all

        conditions: list[str] = []
        params: list[Any] = []

        if scene:
            conditions.append("scene = %s")
            params.append(cls._clean_text(scene, cls.MAX_SCENE_LENGTH))
        if user_id is not None:
            conditions.append("user_id = %s")
            params.append(int(user_id))
        if status:
            conditions.append("status = %s")
            params.append(cls._validate_status(status))

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        params.append(max(1, min(int(limit or 20), 200)))

        rows = (
            fetch_all(
                f"""
            SELECT *
            FROM {cls.RUNS_TABLE}
            {where_clause}
            ORDER BY created_at DESC, run_id DESC
            LIMIT %s
            """,
                tuple(params),
            )
            or []
        )
        if not rows:
            return []

        data = [cls._normalize_run_row(row) for row in rows]
        run_ids = [
            int(item.get("runId") or item.get("run_id") or 0)
            for item in data
            if int(item.get("runId") or item.get("run_id") or 0) > 0
        ]
        overrides_by_run_id = cls._list_overrides_by_run_ids(run_ids, use_primary=use_primary)
        for item in data:
            run_id = int(item.get("runId") or item.get("run_id") or 0)
            item["overrides"] = overrides_by_run_id.get(run_id, [])
            cls._attach_review_state(item)
        return data

    @classmethod
    def _validate_status(cls, status: Any) -> str:
        safe_status = str(status or "").strip().lower()
        if safe_status not in cls.RUN_STATUSES:
            raise ValueError(f"unsupported status: {status}")
        return safe_status

    @classmethod
    def _validate_optional_status(cls, status: str | None) -> str | None:
        if status is None or str(status).strip() == "":
            return None
        return cls._validate_status(status)

    @classmethod
    def _validate_override_action(cls, action: Any) -> str:
        normalized = str(action or "").strip().lower().replace("-", "_").replace(" ", "_")
        if normalized not in cls.OVERRIDE_ACTIONS:
            raise ValueError(f"unsupported override action: {action}")
        return normalized

    @classmethod
    def _validate_override_new_status(cls, action: str, status: str | None) -> str | None:
        safe_status = cls._validate_optional_status(status)
        if safe_status is None:
            return None
        allowed_statuses = cls.OVERRIDE_ALLOWED_NEW_STATUSES.get(action) or set()
        if safe_status not in allowed_statuses:
            raise ValueError(f"unsupported override status transition: action={action} status={status}")
        return safe_status

    @classmethod
    def _serialize_summary(cls, value: Any | None, max_length: int) -> str | None:
        if value is None:
            return None

        if isinstance(value, str):
            return cls._clean_text(cls._sanitize_string(value), max_length)

        sanitized = cls._redact_sensitive_data(value)
        dumped = json.dumps(sanitized, ensure_ascii=False, default=str)
        return cls._clean_text(dumped, max_length)

    @classmethod
    def _redact_sensitive_data(cls, value: Any) -> Any:
        if isinstance(value, dict):
            cleaned: dict[str, Any] = {}
            for key, item in value.items():
                key_text = str(key)
                if cls._is_sensitive_key(key_text):
                    cleaned[key_text] = "[REDACTED]"
                    continue
                cleaned[key_text] = cls._redact_sensitive_data(item)
            return cleaned

        if isinstance(value, (list, tuple, set)):
            return [cls._redact_sensitive_data(item) for item in value]

        if isinstance(value, str):
            return cls._sanitize_string(value)

        if isinstance(value, (datetime, Decimal)):
            return str(value)

        return value

    @classmethod
    def _is_sensitive_key(cls, key: str) -> bool:
        safe_key = str(key or "").strip().lower()
        return any(keyword in safe_key for keyword in cls.SENSITIVE_KEYWORDS)

    @classmethod
    def _sanitize_string(cls, text: str) -> str:
        sanitized = str(text)
        for pattern in cls.SENSITIVE_VALUE_PATTERNS:
            sanitized = pattern.sub(cls._redact_match, sanitized)
        return sanitized

    @staticmethod
    def _redact_match(match: re.Match[str]) -> str:
        groups = match.groups()
        if len(groups) >= 2:
            return f"{groups[0]}=[REDACTED]"
        if len(groups) == 1:
            return f"{groups[0]}[REDACTED]"
        return "[REDACTED]"

    @staticmethod
    def _clean_text(value: Any | None, max_length: int) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        if len(text) <= max_length:
            return text
        suffix = f"...[truncated:{len(text)}]"
        allowed = max(0, max_length - len(suffix))
        return f"{text[:allowed]}{suffix}"

    @staticmethod
    def _coerce_datetime(value: Any | None) -> datetime | None:
        if value is None or value == "":
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    return datetime.strptime(text, fmt)
                except ValueError:
                    continue
        raise ValueError(f"unsupported datetime value: {value}")

    @staticmethod
    def _coerce_int(value: Any | None) -> int | None:
        if value is None or value == "":
            return None
        return int(value)

    @staticmethod
    def _coerce_decimal(value: Any | None) -> float | None:
        if value is None or value == "":
            return None
        return float(value)

    @classmethod
    def _normalize_run_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        run_id = int(row.get("run_id") or 0)
        scene = row.get("scene") or ""
        trigger_source = row.get("trigger_source") or ""
        user_id = int(row.get("user_id") or 0)
        status = row.get("status") or "queued"
        input_summary = row.get("input_summary") or None
        result_summary = row.get("result_summary") or None
        error_summary = row.get("error_summary") or None
        trace_ref = row.get("trace_ref") or None
        started_at = cls._format_datetime(row.get("started_at"))
        finished_at = cls._format_datetime(row.get("finished_at"))
        created_at = cls._format_datetime(row.get("created_at"))
        updated_at = cls._format_datetime(row.get("updated_at"))
        return {
            "run_id": run_id,
            "scene": scene,
            "trigger_source": trigger_source,
            "user_id": user_id,
            "status": status,
            "input_summary": input_summary,
            "result_summary": result_summary,
            "error_summary": error_summary,
            "trace_ref": trace_ref,
            "started_at": started_at,
            "finished_at": finished_at,
            "created_at": created_at,
            "updated_at": updated_at,
            "runId": run_id,
            "triggerSource": trigger_source,
            "userId": user_id,
            "inputSummary": cls._deserialize_summary(input_summary),
            "resultSummary": cls._deserialize_summary(result_summary),
            "errorSummary": cls._deserialize_summary(error_summary),
            "traceRef": trace_ref,
            "startedAt": started_at,
            "finishedAt": finished_at,
            "createdAt": created_at,
            "updatedAt": updated_at,
        }

    @classmethod
    def _normalize_step_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        step_id = int(row.get("step_id") or 0)
        run_id = int(row.get("run_id") or 0)
        step_name = row.get("step_name") or ""
        status = row.get("status") or "queued"
        input_summary = row.get("input_summary") or None
        output_summary = row.get("output_summary") or None
        model_tier = row.get("model_tier") or None
        handoff = row.get("handoff") or None
        latency_ms = int(row.get("latency_ms")) if row.get("latency_ms") is not None else None
        token_count = int(row.get("token_count")) if row.get("token_count") is not None else None
        cost_estimate = float(row.get("cost_estimate")) if row.get("cost_estimate") is not None else None
        prompt_trace_ref = row.get("prompt_trace_ref") or None
        error_summary = row.get("error_summary") or None
        started_at = cls._format_datetime(row.get("started_at"))
        finished_at = cls._format_datetime(row.get("finished_at"))
        created_at = cls._format_datetime(row.get("created_at"))
        updated_at = cls._format_datetime(row.get("updated_at"))
        return {
            "step_id": step_id,
            "run_id": run_id,
            "step_name": step_name,
            "status": status,
            "input_summary": input_summary,
            "output_summary": output_summary,
            "model_tier": model_tier,
            "handoff": handoff,
            "latency_ms": latency_ms,
            "token_count": token_count,
            "cost_estimate": cost_estimate,
            "prompt_trace_ref": prompt_trace_ref,
            "error_summary": error_summary,
            "started_at": started_at,
            "finished_at": finished_at,
            "created_at": created_at,
            "updated_at": updated_at,
            "stepId": step_id,
            "runId": run_id,
            "stepName": step_name,
            "inputSummary": cls._deserialize_summary(input_summary),
            "outputSummary": cls._deserialize_summary(output_summary),
            "modelTier": model_tier,
            "latencyMs": latency_ms,
            "tokenCount": token_count,
            "costEstimate": cost_estimate,
            "promptTraceRef": prompt_trace_ref,
            "errorSummary": cls._deserialize_summary(error_summary),
            "startedAt": started_at,
            "finishedAt": finished_at,
            "createdAt": created_at,
            "updatedAt": updated_at,
        }

    @classmethod
    def _normalize_override_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        override_id = int(row.get("override_id") or 0)
        run_id = int(row.get("run_id") or 0)
        user_id = int(row.get("user_id") or 0)
        actor = row.get("actor") or ""
        action = row.get("action") or ""
        reason = row.get("reason") or None
        old_status = row.get("old_status") or None
        new_status = row.get("new_status") or None
        review_note = row.get("review_note") or None
        created_at = cls._format_datetime(row.get("created_at"))
        return {
            "override_id": override_id,
            "run_id": run_id,
            "user_id": user_id,
            "actor": actor,
            "action": action,
            "reason": reason,
            "old_status": old_status,
            "new_status": new_status,
            "review_note": review_note,
            "created_at": created_at,
            "overrideId": override_id,
            "runId": run_id,
            "userId": user_id,
            "oldStatus": old_status,
            "newStatus": new_status,
            "reviewNote": cls._deserialize_summary(review_note),
            "reasonDetail": cls._deserialize_summary(reason),
            "createdAt": created_at,
        }

    @classmethod
    def _list_overrides_by_run_ids(
        cls,
        run_ids: list[int],
        *,
        use_primary: bool = False,
    ) -> dict[int, list[dict[str, Any]]]:
        filtered_run_ids = [int(run_id) for run_id in run_ids if int(run_id) > 0]
        if not filtered_run_ids:
            return {}

        fetch_all = DbUtil.fetch_all_primary if use_primary else DbUtil.fetch_all
        placeholders = ", ".join(["%s"] * len(filtered_run_ids))
        rows = (
            fetch_all(
                f"""
            SELECT *
            FROM {cls.OVERRIDES_TABLE}
            WHERE run_id IN ({placeholders})
            ORDER BY created_at ASC, override_id ASC
            """,
                tuple(filtered_run_ids),
            )
            or []
        )

        grouped: dict[int, list[dict[str, Any]]] = {}
        for row in rows:
            override = cls._normalize_override_row(row)
            run_id = int(override.get("runId") or override.get("run_id") or 0)
            grouped.setdefault(run_id, []).append(override)
        return grouped

    @classmethod
    def _attach_review_state(cls, data: dict[str, Any]) -> dict[str, Any]:
        overrides = data.get("overrides") if isinstance(data.get("overrides"), list) else []
        latest_override = overrides[-1] if overrides else None
        review_action = (
            str(latest_override.get("action") or "").strip().lower() if isinstance(latest_override, dict) else ""
        )
        data["latestOverride"] = latest_override
        data["reviewAction"] = review_action or None
        data["reviewedAt"] = latest_override.get("createdAt") if isinstance(latest_override, dict) else None
        data["reviewedBy"] = latest_override.get("actor") if isinstance(latest_override, dict) else None
        return data

    @staticmethod
    def _deserialize_summary(value: Any | None) -> Any | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        text = value.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except Exception:
            return text

    @staticmethod
    def _format_datetime(value: Any | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d %H:%M:%S")
        return str(value)
