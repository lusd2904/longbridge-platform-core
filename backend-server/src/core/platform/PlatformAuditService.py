from __future__ import annotations

from typing import Dict, List, Optional

from utils.DbUtil import DbUtil


class PlatformAuditService:
    TABLE_NAME = "platform_audit_logs"

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id INT DEFAULT NULL,
                username VARCHAR(80) DEFAULT NULL,
                level VARCHAR(16) DEFAULT 'info',
                module VARCHAR(64) DEFAULT 'platform',
                operation VARCHAR(64) DEFAULT NULL,
                description VARCHAR(255) DEFAULT NULL,
                extra_json JSON DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_created (user_id, created_at),
                INDEX idx_level_created (level, created_at),
                INDEX idx_module_created (module, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def log(
        cls,
        *,
        user_id: Optional[int],
        username: Optional[str],
        module: str,
        operation: str,
        description: str,
        level: str = "info",
        extra: Optional[Dict[str, object]] = None
    ) -> None:
        try:
            cls.ensure_schema()
            DbUtil.execute_sql(
                f"""
                INSERT INTO {cls.TABLE_NAME} (
                    user_id, username, level, module, operation, description, extra_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    username,
                    (level or "info")[:16],
                    (module or "platform")[:64],
                    (operation or "")[:64] or None,
                    (description or "")[:255] or None,
                    cls._to_json(extra)
                )
            )
        except Exception:
            return

    @classmethod
    def list_recent(cls, limit: int = 120, level: str = "") -> List[Dict[str, object]]:
        cls.ensure_schema()
        params: List[object] = []
        where_clause = ""
        if level and level.lower() != "all":
            where_clause = "WHERE level = %s"
            params.append(level.lower())
        params.append(max(10, min(int(limit or 120), 400)))
        rows = DbUtil.fetch_all(
            f"""
            SELECT id, user_id, username, level, module, operation, description, created_at
            FROM {cls.TABLE_NAME}
            {where_clause}
            ORDER BY id DESC
            LIMIT %s
            """,
            tuple(params)
        ) or []
        return [
            {
                "id": int(row.get("id") or 0),
                "time": row.get("created_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("created_at") else None,
                "level": row.get("level") or "info",
                "module": row.get("module") or "platform",
                "operation": row.get("operation") or "",
                "message": row.get("description") or "",
                "username": row.get("username") or ""
            }
            for row in rows
        ]

    @staticmethod
    def _to_json(payload: Optional[Dict[str, object]]) -> Optional[str]:
        if not payload:
            return None
        import json
        return json.dumps(payload, ensure_ascii=False)
