from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from utils.DbUtil import DbUtil


class RiskOverviewSnapshotService:
    TABLE_NAME = "risk_overview_snapshots"

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                account_id INT DEFAULT NULL,
                risk_score DECIMAL(10, 4) DEFAULT 0,
                score_label VARCHAR(32) DEFAULT NULL,
                score_description VARCHAR(255) DEFAULT NULL,
                high_risk_count INT DEFAULT 0,
                medium_risk_count INT DEFAULT 0,
                max_weight DECIMAL(10, 4) DEFAULT 0,
                position_limit DECIMAL(10, 4) DEFAULT 0,
                drawdown DECIMAL(10, 4) DEFAULT 0,
                drawdown_limit DECIMAL(10, 4) DEFAULT 0,
                protection_count INT DEFAULT 0,
                stop_loss_count INT DEFAULT 0,
                take_profit_count INT DEFAULT 0,
                position_count INT DEFAULT 0,
                snapshot_at DATETIME NOT NULL,
                overview_json JSON DEFAULT NULL,
                events_json JSON DEFAULT NULL,
                source VARCHAR(32) DEFAULT 'risk-service',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_user_account_snapshot (user_id, account_id, snapshot_at),
                INDEX idx_user_account_time (user_id, account_id, snapshot_at),
                INDEX idx_snapshot_at (snapshot_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def save_snapshot(
        cls,
        *,
        user_id: int,
        payload: dict[str, Any],
        account_id: int | None = None,
        snapshot_at: datetime | None = None,
        source: str = "risk-service",
    ) -> None:
        cls.ensure_schema()
        overview = payload.get("overview") or {}
        events = payload.get("events") or []
        high_risk_count = len([item for item in events if str(item.get("level") or "").lower() == "high"])
        medium_risk_count = len([item for item in events if str(item.get("level") or "").lower() == "medium"])
        safe_snapshot_at = snapshot_at or datetime.now()
        DbUtil.execute_sql(
            f"""
            INSERT INTO {cls.TABLE_NAME} (
                user_id, account_id, risk_score, score_label, score_description,
                high_risk_count, medium_risk_count, max_weight, position_limit,
                drawdown, drawdown_limit, protection_count, stop_loss_count,
                take_profit_count, position_count, snapshot_at, overview_json,
                events_json, source
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                risk_score = VALUES(risk_score),
                score_label = VALUES(score_label),
                score_description = VALUES(score_description),
                high_risk_count = VALUES(high_risk_count),
                medium_risk_count = VALUES(medium_risk_count),
                max_weight = VALUES(max_weight),
                position_limit = VALUES(position_limit),
                drawdown = VALUES(drawdown),
                drawdown_limit = VALUES(drawdown_limit),
                protection_count = VALUES(protection_count),
                stop_loss_count = VALUES(stop_loss_count),
                take_profit_count = VALUES(take_profit_count),
                position_count = VALUES(position_count),
                overview_json = VALUES(overview_json),
                events_json = VALUES(events_json),
                source = VALUES(source)
            """,
            (
                int(user_id),
                int(account_id) if account_id not in (None, "") else None,
                float(overview.get("score") or 0),
                str(overview.get("scoreLabel") or "")[:32] or None,
                str(overview.get("scoreDescription") or "")[:255] or None,
                high_risk_count,
                medium_risk_count,
                float(overview.get("maxWeight") or 0),
                float(overview.get("positionLimit") or 0),
                float(overview.get("drawdown") or 0),
                float(overview.get("drawdownLimit") or 0),
                int(overview.get("protectionCount") or 0),
                int(overview.get("stopLossCount") or 0),
                int(overview.get("takeProfitCount") or 0),
                int(overview.get("positionCount") or 0),
                safe_snapshot_at,
                json.dumps(overview, ensure_ascii=False),
                json.dumps(events, ensure_ascii=False),
                source,
            ),
        )

    @classmethod
    def get_latest(
        cls,
        *,
        user_id: int,
        account_id: int | None = None,
        use_primary: bool = False,
    ) -> dict[str, Any] | None:
        cls.ensure_schema()
        fetch_one = DbUtil.fetch_one_primary if use_primary else DbUtil.fetch_one
        sql = f"""
            SELECT *
            FROM {cls.TABLE_NAME}
            WHERE user_id = %s
        """
        params = [int(user_id)]
        if account_id not in (None, ""):
            sql += " AND account_id = %s"
            params.append(int(account_id))
        sql += " ORDER BY snapshot_at DESC, id DESC LIMIT 1"
        row = fetch_one(sql, tuple(params))
        return cls._normalize_row(row) if row else None

    @classmethod
    def _normalize_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        overview = row.get("overview_json")
        if isinstance(overview, str):
            try:
                overview = json.loads(overview)
            except Exception:
                overview = {}
        elif not isinstance(overview, dict):
            overview = {}

        events = row.get("events_json")
        if isinstance(events, str):
            try:
                events = json.loads(events)
            except Exception:
                events = []
        elif not isinstance(events, list):
            events = []

        snapshot_at = row.get("snapshot_at")
        return {
            "userId": int(row.get("user_id") or 0),
            "accountId": row.get("account_id"),
            "snapshotAt": snapshot_at.strftime("%Y-%m-%d %H:%M:%S") if snapshot_at else None,
            "source": row.get("source") or "risk-service",
            "overview": overview,
            "events": events,
        }
