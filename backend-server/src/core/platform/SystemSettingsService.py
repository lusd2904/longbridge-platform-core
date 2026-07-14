from __future__ import annotations

import threading
from collections.abc import Iterable

from utils.DbUtil import DbUtil


class SystemSettingsService:
    _schema_ready = False
    _lock = threading.Lock()

    DEFAULTS = {
        "system_name": {"value": "LongbridgeTrade", "type": "string", "description": "平台名称"},
        "default_market": {"value": "US", "type": "string", "description": "默认市场"},
        "default_currency": {"value": "USD", "type": "string", "description": "默认货币"},
        "language": {"value": "zh-CN", "type": "string", "description": "默认语言"},
        "timezone": {"value": "Asia/Shanghai", "type": "string", "description": "默认时区"},
        "dashboard_refresh_seconds": {"value": "15", "type": "int", "description": "首页数据刷新间隔"},
        "finance_news_refresh_seconds": {"value": "900", "type": "int", "description": "财经资讯刷新间隔"},
    }

    @classmethod
    def ensure_schema(cls) -> None:
        if cls._schema_ready:
            return

        with cls._lock:
            if cls._schema_ready:
                return

            DbUtil.execute_sql(
                """
                CREATE TABLE IF NOT EXISTS platform_system_settings (
                    setting_key VARCHAR(80) NOT NULL PRIMARY KEY,
                    setting_value TEXT DEFAULT NULL,
                    value_type VARCHAR(16) DEFAULT 'string',
                    description VARCHAR(255) DEFAULT NULL,
                    updated_by INT DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            for key, meta in cls.DEFAULTS.items():
                DbUtil.execute_sql(
                    """
                    INSERT INTO platform_system_settings (setting_key, setting_value, value_type, description)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        value_type = VALUES(value_type),
                        description = VALUES(description),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (key, str(meta.get("value", "")), meta.get("type", "string"), meta.get("description")),
                )

            cls._schema_ready = True

    @classmethod
    def get_all(cls) -> dict[str, object]:
        cls.ensure_schema()
        rows = (
            DbUtil.fetch_all(
                """
            SELECT setting_key, setting_value, value_type, description, updated_at
            FROM platform_system_settings
            ORDER BY setting_key ASC
            """
            )
            or []
        )
        payload: dict[str, object] = {}
        for row in rows:
            payload[row.get("setting_key")] = cls._coerce_value(row.get("setting_value"), row.get("value_type"))
        return payload

    @classmethod
    def update_many(
        cls, updates: dict[str, object], user_id: int | None = None, allowed_keys: Iterable[str] | None = None
    ) -> dict[str, object]:
        cls.ensure_schema()
        allowed = set(allowed_keys or cls.DEFAULTS.keys())
        for key, value in (updates or {}).items():
            if key not in allowed:
                continue
            default_meta = cls.DEFAULTS.get(key, {})
            DbUtil.execute_sql(
                """
                INSERT INTO platform_system_settings (setting_key, setting_value, value_type, description, updated_by)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    setting_value = VALUES(setting_value),
                    value_type = VALUES(value_type),
                    description = VALUES(description),
                    updated_by = VALUES(updated_by),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    key,
                    cls._serialize_value(value),
                    default_meta.get("type", "string"),
                    default_meta.get("description"),
                    user_id,
                ),
            )
        return cls.get_all()

    @staticmethod
    def _serialize_value(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    @staticmethod
    def _coerce_value(raw_value: object, value_type: object) -> object:
        raw = "" if raw_value is None else str(raw_value)
        safe_type = str(value_type or "string").lower()
        if safe_type == "int":
            try:
                return int(raw)
            except (TypeError, ValueError):
                return 0
        if safe_type == "float":
            try:
                return float(raw)
            except (TypeError, ValueError):
                return 0.0
        if safe_type == "bool":
            return raw.strip().lower() in {"1", "true", "yes", "on"}
        return raw
