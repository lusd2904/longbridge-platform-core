from __future__ import annotations

import json

from utils.DbUtil import DbUtil


class TradeAuditService:
    TABLE_NAME = "trade_execution_audits"

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                username VARCHAR(80) DEFAULT NULL,
                account_id INT NOT NULL,
                broker_type VARCHAR(32) DEFAULT NULL,
                symbol VARCHAR(32) DEFAULT NULL,
                action VARCHAR(16) DEFAULT NULL,
                order_type VARCHAR(24) DEFAULT NULL,
                quantity DECIMAL(18, 4) DEFAULT 0,
                request_price DECIMAL(18, 4) DEFAULT NULL,
                reference_price DECIMAL(18, 4) DEFAULT NULL,
                risk_level VARCHAR(16) DEFAULT NULL,
                risk_passed TINYINT(1) DEFAULT 0,
                status VARCHAR(24) DEFAULT 'received',
                message VARCHAR(255) DEFAULT NULL,
                order_id VARCHAR(64) DEFAULT NULL,
                request_id VARCHAR(64) DEFAULT NULL,
                client_ip VARCHAR(64) DEFAULT NULL,
                extra_json JSON DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_created (user_id, created_at),
                INDEX idx_account_created (account_id, created_at),
                INDEX idx_status_created (status, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def log(
        cls,
        *,
        user_id: int,
        username: str | None,
        account_id: int,
        broker_type: str,
        symbol: str,
        action: str,
        order_type: str,
        quantity: float,
        request_price: float | None,
        reference_price: float | None,
        risk_level: str,
        risk_passed: bool,
        status: str,
        message: str,
        order_id: str | None = None,
        request_id: str | None = None,
        client_ip: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> None:
        try:
            cls.ensure_schema()
            DbUtil.execute_sql(
                f"""
                INSERT INTO {cls.TABLE_NAME} (
                    user_id, username, account_id, broker_type, symbol, action, order_type,
                    quantity, request_price, reference_price, risk_level, risk_passed,
                    status, message, order_id, request_id, client_ip, extra_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    int(user_id),
                    (username or "")[:80] or None,
                    int(account_id),
                    (broker_type or "")[:32] or None,
                    (symbol or "")[:32] or None,
                    (action or "")[:16] or None,
                    (order_type or "")[:24] or None,
                    float(quantity or 0),
                    float(request_price) if request_price is not None else None,
                    float(reference_price) if reference_price is not None else None,
                    (risk_level or "")[:16] or None,
                    1 if risk_passed else 0,
                    (status or "received")[:24],
                    (message or "")[:255] or None,
                    (order_id or "")[:64] or None,
                    (request_id or "")[:64] or None,
                    (client_ip or "")[:64] or None,
                    cls._to_json(extra),
                ),
            )
        except Exception:
            return

    @classmethod
    def list_recent(cls, limit: int = 120, user_id: int | None = None) -> list[dict[str, object]]:
        cls.ensure_schema()
        where_clause = ""
        params: list[object] = []
        if user_id is not None:
            where_clause = "WHERE user_id = %s"
            params.append(int(user_id))
        params.append(max(10, min(int(limit or 120), 300)))
        rows = (
            DbUtil.fetch_all(
                f"""
            SELECT id, user_id, username, account_id, broker_type, symbol, action, order_type,
                   quantity, request_price, reference_price, risk_level, risk_passed,
                   status, message, order_id, request_id, client_ip, created_at
            FROM {cls.TABLE_NAME}
            {where_clause}
            ORDER BY id DESC
            LIMIT %s
            """,
                tuple(params),
            )
            or []
        )
        return [
            {
                "id": int(row.get("id") or 0),
                "userId": int(row.get("user_id") or 0),
                "username": row.get("username") or "",
                "accountId": int(row.get("account_id") or 0),
                "brokerType": row.get("broker_type") or "",
                "symbol": row.get("symbol") or "",
                "action": row.get("action") or "",
                "orderType": row.get("order_type") or "",
                "quantity": float(row.get("quantity") or 0),
                "requestPrice": float(row.get("request_price") or 0) if row.get("request_price") is not None else None,
                "referencePrice": float(row.get("reference_price") or 0)
                if row.get("reference_price") is not None
                else None,
                "riskLevel": row.get("risk_level") or "",
                "riskPassed": bool(row.get("risk_passed")),
                "status": row.get("status") or "received",
                "message": row.get("message") or "",
                "orderId": row.get("order_id") or None,
                "requestId": row.get("request_id") or None,
                "clientIp": row.get("client_ip") or None,
                "createdAt": row.get("created_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("created_at") else None,
            }
            for row in rows
        ]

    @staticmethod
    def _to_json(payload: dict[str, object] | None) -> str | None:
        if not payload:
            return None
        return json.dumps(payload, ensure_ascii=False)
