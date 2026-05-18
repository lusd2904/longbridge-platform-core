from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.bootstrap import bootstrap_runtime

bootstrap_runtime()

from config.settings import settings  # noqa: E402
from utils.DbUtil import DbUtil, get_db_connection  # noqa: E402
from utils.kafka_bus import kafka_bus  # noqa: E402

from legacy_trade_service.models import AuthUser

try:
    from kafka import KafkaConsumer

    KAFKA_CONSUMER_AVAILABLE = True
except Exception:
    KafkaConsumer = None
    KAFKA_CONSUMER_AVAILABLE = False


def _ensure_trade_schema() -> None:
    DbUtil.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS trade_sagas (
            saga_id VARCHAR(64) PRIMARY KEY,
            user_id INT NOT NULL,
            account_id INT NOT NULL,
            saga_type VARCHAR(32) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            symbol VARCHAR(32) DEFAULT NULL,
            action VARCHAR(16) DEFAULT NULL,
            quantity DECIMAL(18, 4) DEFAULT 0,
            request_price DECIMAL(18, 4) DEFAULT NULL,
            reference_price DECIMAL(18, 4) DEFAULT NULL,
            order_type VARCHAR(24) DEFAULT NULL,
            order_id VARCHAR(64) DEFAULT NULL,
            message VARCHAR(255) DEFAULT NULL,
            compensation_status VARCHAR(32) DEFAULT NULL,
            request_id VARCHAR(64) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_user_created (user_id, created_at),
            INDEX idx_account_created (account_id, created_at),
            INDEX idx_status_created (status, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    DbUtil.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS trade_saga_steps (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            saga_id VARCHAR(64) NOT NULL,
            step_name VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            detail VARCHAR(255) DEFAULT NULL,
            payload_json JSON DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_saga_created (saga_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    DbUtil.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS trade_outbox_events (
            event_id VARCHAR(64) PRIMARY KEY,
            saga_id VARCHAR(64) DEFAULT NULL,
            topic VARCHAR(128) NOT NULL,
            event_type VARCHAR(128) NOT NULL,
            event_key VARCHAR(128) DEFAULT NULL,
            payload_json JSON NOT NULL,
            publish_status VARCHAR(24) NOT NULL DEFAULT 'pending',
            retry_count INT NOT NULL DEFAULT 0,
            last_error VARCHAR(255) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            published_at TIMESTAMP NULL DEFAULT NULL,
            INDEX idx_status_created (publish_status, created_at),
            INDEX idx_saga_created (saga_id, created_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    DbUtil.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS trade_event_inbox (
            event_id VARCHAR(64) PRIMARY KEY,
            topic VARCHAR(128) NOT NULL,
            event_key VARCHAR(128) DEFAULT NULL,
            payload_json JSON NOT NULL,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_topic_received (topic, received_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    DbUtil.execute_sql(
        """
        CREATE TABLE IF NOT EXISTS trade_order_projections (
            account_id INT NOT NULL,
            order_id VARCHAR(64) NOT NULL,
            user_id INT NOT NULL,
            symbol VARCHAR(32) DEFAULT NULL,
            action VARCHAR(16) DEFAULT NULL,
            order_type VARCHAR(24) DEFAULT NULL,
            quantity DECIMAL(18, 4) DEFAULT 0,
            price DECIMAL(18, 4) DEFAULT NULL,
            status VARCHAR(32) DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (account_id, order_id),
            INDEX idx_user_updated (user_id, updated_at),
            INDEX idx_user_status_updated (user_id, status, updated_at)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _ensure_trade_projection_indexes()
    _ensure_trade_outbox_columns()


def _ensure_trade_outbox_columns() -> None:
    columns = {
        "next_retry_at": "DATETIME DEFAULT NULL",
        "dead_letter_at": "DATETIME DEFAULT NULL",
    }
    for column_name, column_definition in columns.items():
        exists = DbUtil.query_one(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = 'trade_outbox_events'
              AND column_name = %s
            LIMIT 1
            """,
            (column_name,),
        )
        if exists:
            continue
        DbUtil.execute_sql(
            f"ALTER TABLE trade_outbox_events ADD COLUMN {column_name} {column_definition}"
        )


def _ensure_trade_projection_indexes() -> None:
    indexes = {
        "idx_user_status_updated": "user_id, status, updated_at",
    }
    for index_name, columns in indexes.items():
        exists = DbUtil.query_one(
            """
            SELECT 1
            FROM information_schema.statistics
            WHERE table_schema = DATABASE()
              AND table_name = 'trade_order_projections'
              AND index_name = %s
            LIMIT 1
            """,
            (index_name,),
        )
        if exists:
            continue
        DbUtil.execute_sql(
            f"ALTER TABLE trade_order_projections ADD INDEX {index_name} ({columns})"
        )


def _serialize_payload(payload: Optional[Dict[str, Any]]) -> Optional[str]:
    if payload is None:
        return None
    return json.dumps(payload, ensure_ascii=False)


def _serialize_datetime(value: Any) -> Optional[str]:
    if not value:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def _insert_step(
    cursor,
    saga_id: str,
    step_name: str,
    status: str,
    detail: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO trade_saga_steps (saga_id, step_name, status, detail, payload_json)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (saga_id, step_name, status, (detail or "")[:255], _serialize_payload(payload)),
    )


def _insert_outbox(
    cursor,
    saga_id: Optional[str],
    topic: str,
    event_type: str,
    event_key: str,
    payload: Dict[str, Any],
) -> str:
    event_id = uuid.uuid4().hex
    cursor.execute(
        """
        INSERT INTO trade_outbox_events (
            event_id, saga_id, topic, event_type, event_key, payload_json, publish_status
        )
        VALUES (%s, %s, %s, %s, %s, %s, 'pending')
        """,
        (event_id, saga_id, topic, event_type, event_key, _serialize_payload(payload)),
    )
    return event_id


def _create_saga(
    *,
    user: AuthUser,
    account_id: int,
    saga_type: str,
    symbol: str,
    action: str,
    quantity: int,
    request_price: Optional[float],
    order_type: str,
    request_id: Optional[str],
    initial_event_type: str,
) -> str:
    saga_id = uuid.uuid4().hex
    topic = settings.KAFKA_TRADE_COMMAND_TOPIC if saga_type == "submit_order" else settings.KAFKA_TRADE_EVENT_TOPIC
    payload = {
        "sagaId": saga_id,
        "userId": user.user_id,
        "accountId": account_id,
        "symbol": symbol,
        "action": action,
        "quantity": quantity,
        "requestPrice": request_price,
        "orderType": order_type,
        "requestId": request_id,
        "createdAt": datetime.now().isoformat(),
    }
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO trade_sagas (
                    saga_id, user_id, account_id, saga_type, status, symbol, action, quantity,
                    request_price, order_type, message, request_id
                )
                VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    saga_id,
                    user.user_id,
                    account_id,
                    saga_type,
                    symbol,
                    action,
                    quantity,
                    request_price,
                    order_type,
                    "交易请求已接收",
                    request_id,
                ),
            )
            _insert_step(cursor, saga_id, "received", "completed", "交易请求已接收", payload)
            _insert_outbox(cursor, saga_id, topic, initial_event_type, saga_id, payload)
    return saga_id


def _update_saga_status(
    *,
    saga_id: str,
    status: str,
    message: str,
    reference_price: Optional[float] = None,
    order_id: Optional[str] = None,
    compensation_status: Optional[str] = None,
) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE trade_sagas
                SET status = %s,
                    message = %s,
                    reference_price = COALESCE(%s, reference_price),
                    order_id = COALESCE(%s, order_id),
                    compensation_status = COALESCE(%s, compensation_status)
                WHERE saga_id = %s
                """,
                (status, (message or "")[:255], reference_price, order_id, compensation_status, saga_id),
            )


def _record_saga_step(
    saga_id: str,
    step_name: str,
    status: str,
    detail: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            _insert_step(cursor, saga_id, step_name, status, detail, payload)


def _record_outbox_event(
    saga_id: str,
    event_type: str,
    payload: Dict[str, Any],
    *,
    topic: Optional[str] = None,
) -> None:
    target_topic = topic or (
        settings.KAFKA_TRADE_COMMAND_TOPIC if event_type.endswith(".requested") else settings.KAFKA_TRADE_EVENT_TOPIC
    )
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            _insert_outbox(cursor, saga_id, target_topic, event_type, saga_id, payload)


def _upsert_projection(
    *,
    user_id: int,
    account_id: int,
    order_id: str,
    symbol: str,
    action: str,
    order_type: str,
    quantity: int,
    price: Optional[float],
    status: str,
) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO trade_order_projections (
                    account_id, order_id, user_id, symbol, action, order_type, quantity, price, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    symbol = COALESCE(NULLIF(VALUES(symbol), ''), symbol),
                    action = COALESCE(NULLIF(VALUES(action), ''), action),
                    order_type = COALESCE(NULLIF(VALUES(order_type), ''), order_type),
                    quantity = CASE WHEN VALUES(quantity) > 0 THEN VALUES(quantity) ELSE quantity END,
                    price = COALESCE(VALUES(price), price),
                    status = COALESCE(NULLIF(VALUES(status), ''), status),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (account_id, order_id, user_id, symbol, action, order_type, quantity, price, status),
            )


class OutboxRelay:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._publisher_thread: Optional[threading.Thread] = None
        self._consumer_thread: Optional[threading.Thread] = None
        self._last_publish_at: Optional[str] = None
        self._last_consume_at: Optional[str] = None
        self._last_error: Optional[str] = None
        self._last_repair_at: Optional[str] = None
        self._max_retries = max(3, int(os.getenv("REF_TRADE_OUTBOX_MAX_RETRIES", "6")))
        self._base_retry_seconds = max(5, int(os.getenv("REF_TRADE_OUTBOX_RETRY_BASE_SECONDS", "10")))
        self._max_retry_seconds = max(self._base_retry_seconds, int(os.getenv("REF_TRADE_OUTBOX_RETRY_MAX_SECONDS", "600")))

    def repair_state(self) -> Dict[str, int]:
        dead_lettered = 0
        rescheduled = 0
        self._last_repair_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                dead_lettered = cursor.execute(
                    """
                    UPDATE trade_outbox_events
                    SET publish_status = 'dead_letter',
                        next_retry_at = NULL,
                        dead_letter_at = COALESCE(dead_letter_at, CURRENT_TIMESTAMP),
                        last_error = CASE
                            WHEN COALESCE(NULLIF(last_error, ''), '') = '' THEN %s
                            ELSE last_error
                        END
                    WHERE publish_status = 'failed'
                      AND retry_count >= %s
                    """,
                    ("retry count exceeded max retries", self._max_retries),
                )
                rescheduled = cursor.execute(
                    f"""
                    UPDATE trade_outbox_events
                    SET next_retry_at = DATE_ADD(UTC_TIMESTAMP(), INTERVAL {int(self._base_retry_seconds)} SECOND)
                    WHERE publish_status = 'failed'
                      AND retry_count < %s
                      AND next_retry_at IS NULL
                    """,
                    (self._max_retries,),
                )
            conn.commit()

        return {
            "deadLettered": int(dead_lettered or 0),
            "rescheduled": int(rescheduled or 0),
        }

    def list_events(
        self,
        *,
        statuses: Optional[List[str]] = None,
        saga_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
        include_payload: bool = False,
    ) -> List[Dict[str, Any]]:
        normalized_statuses = [
            str(status or "").strip().lower()
            for status in (statuses or [])
            if str(status or "").strip()
        ]
        normalized_statuses = [
            status for status in normalized_statuses
            if status in {"pending", "failed", "published", "dead_letter"}
        ]

        where_clauses: List[str] = []
        params: List[Any] = []
        if normalized_statuses:
            placeholders = ", ".join(["%s"] * len(normalized_statuses))
            where_clauses.append(f"publish_status IN ({placeholders})")
            params.extend(normalized_statuses)
        if str(saga_id or "").strip():
            where_clauses.append("saga_id = %s")
            params.append(str(saga_id).strip())
        if str(event_type or "").strip():
            where_clauses.append("event_type = %s")
            params.append(str(event_type).strip())

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        rows = DbUtil.fetch_all(
            f"""
            SELECT
                event_id,
                saga_id,
                topic,
                event_type,
                event_key,
                publish_status,
                retry_count,
                last_error,
                next_retry_at,
                dead_letter_at,
                created_at,
                published_at,
                payload_json
            FROM trade_outbox_events
            {where_sql}
            ORDER BY COALESCE(dead_letter_at, published_at, created_at) DESC, created_at DESC
            LIMIT %s
            """,
            tuple(params + [max(1, min(int(limit or 50), 200))]),
        ) or []

        items: List[Dict[str, Any]] = []
        for row in rows:
            payload_raw = row.get("payload_json")
            payload = None
            if include_payload:
                payload = payload_raw
                if isinstance(payload_raw, str):
                    try:
                        payload = json.loads(payload_raw)
                    except Exception:
                        payload = {"raw": payload_raw}
            items.append(
                {
                    "eventId": row.get("event_id"),
                    "sagaId": row.get("saga_id"),
                    "topic": row.get("topic"),
                    "eventType": row.get("event_type"),
                    "eventKey": row.get("event_key"),
                    "publishStatus": row.get("publish_status"),
                    "retryCount": int(row.get("retry_count") or 0),
                    "lastError": row.get("last_error"),
                    "nextRetryAt": _serialize_datetime(row.get("next_retry_at")),
                    "deadLetterAt": _serialize_datetime(row.get("dead_letter_at")),
                    "createdAt": _serialize_datetime(row.get("created_at")),
                    "publishedAt": _serialize_datetime(row.get("published_at")),
                    **({"payload": payload} if include_payload else {}),
                }
            )
        return items

    def list_sagas(
        self,
        *,
        statuses: Optional[List[str]] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        normalized_statuses = [
            str(status or "").strip().lower()
            for status in (statuses or [])
            if str(status or "").strip()
        ]
        normalized_statuses = [
            status for status in normalized_statuses
            if status in {"pending", "failed", "published", "dead_letter"}
        ]

        where_clauses = ["saga_id IS NOT NULL", "saga_id <> ''"]
        params: List[Any] = []
        if normalized_statuses:
            placeholders = ", ".join(["%s"] * len(normalized_statuses))
            where_clauses.append(f"publish_status IN ({placeholders})")
            params.extend(normalized_statuses)

        rows = DbUtil.fetch_all(
            f"""
            SELECT
                saga_id,
                COUNT(*) AS event_count,
                SUM(CASE WHEN publish_status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                SUM(CASE WHEN publish_status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                SUM(CASE WHEN publish_status = 'published' THEN 1 ELSE 0 END) AS published_count,
                SUM(CASE WHEN publish_status = 'dead_letter' THEN 1 ELSE 0 END) AS dead_letter_count,
                MAX(created_at) AS last_created_at,
                MAX(dead_letter_at) AS last_dead_letter_at
            FROM trade_outbox_events
            WHERE {' AND '.join(where_clauses)}
            GROUP BY saga_id
            ORDER BY COALESCE(MAX(dead_letter_at), MAX(created_at)) DESC
            LIMIT %s
            """,
            tuple(params + [max(1, min(int(limit or 50), 200))]),
        ) or []

        items: List[Dict[str, Any]] = []
        for row in rows:
            items.append(
                {
                    "sagaId": row.get("saga_id"),
                    "eventCount": int(row.get("event_count") or 0),
                    "pendingCount": int(row.get("pending_count") or 0),
                    "failedCount": int(row.get("failed_count") or 0),
                    "publishedCount": int(row.get("published_count") or 0),
                    "deadLetterCount": int(row.get("dead_letter_count") or 0),
                    "lastCreatedAt": _serialize_datetime(row.get("last_created_at")),
                    "lastDeadLetterAt": _serialize_datetime(row.get("last_dead_letter_at")),
                }
            )
        return items

    def requeue_events(self, event_ids: List[str]) -> int:
        normalized_ids = [str(event_id or "").strip() for event_id in event_ids if str(event_id or "").strip()]
        if not normalized_ids:
            return 0
        placeholders = ", ".join(["%s"] * len(normalized_ids))
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                updated = cursor.execute(
                    f"""
                    UPDATE trade_outbox_events
                    SET publish_status = 'pending',
                        retry_count = 0,
                        last_error = NULL,
                        next_retry_at = NULL,
                        dead_letter_at = NULL,
                        published_at = NULL
                    WHERE event_id IN ({placeholders})
                      AND publish_status IN ('failed', 'dead_letter')
                    """,
                    tuple(normalized_ids),
                )
            conn.commit()
        return int(updated or 0)

    def requeue_sagas(self, saga_ids: List[str]) -> int:
        normalized_ids = [str(saga_id or "").strip() for saga_id in saga_ids if str(saga_id or "").strip()]
        if not normalized_ids:
            return 0
        placeholders = ", ".join(["%s"] * len(normalized_ids))
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                updated = cursor.execute(
                    f"""
                    UPDATE trade_outbox_events
                    SET publish_status = 'pending',
                        retry_count = 0,
                        last_error = NULL,
                        next_retry_at = NULL,
                        dead_letter_at = NULL,
                        published_at = NULL
                    WHERE saga_id IN ({placeholders})
                      AND publish_status IN ('failed', 'dead_letter')
                    """,
                    tuple(normalized_ids),
                )
            conn.commit()
        return int(updated or 0)

    def purge_dead_letters(self, event_ids: List[str]) -> int:
        normalized_ids = [str(event_id or "").strip() for event_id in event_ids if str(event_id or "").strip()]
        if not normalized_ids:
            return 0
        placeholders = ", ".join(["%s"] * len(normalized_ids))
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                deleted = cursor.execute(
                    f"""
                    DELETE FROM trade_outbox_events
                    WHERE event_id IN ({placeholders})
                      AND publish_status = 'dead_letter'
                    """,
                    tuple(normalized_ids),
                )
            conn.commit()
        return int(deleted or 0)

    def purge_dead_letters_by_saga(self, saga_ids: List[str]) -> int:
        normalized_ids = [str(saga_id or "").strip() for saga_id in saga_ids if str(saga_id or "").strip()]
        if not normalized_ids:
            return 0
        placeholders = ", ".join(["%s"] * len(normalized_ids))
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                deleted = cursor.execute(
                    f"""
                    DELETE FROM trade_outbox_events
                    WHERE saga_id IN ({placeholders})
                      AND publish_status = 'dead_letter'
                    """,
                    tuple(normalized_ids),
                )
            conn.commit()
        return int(deleted or 0)

    def _load_publish_candidates(self, limit: int) -> List[Dict[str, Any]]:
        return DbUtil.fetch_all(
            """
            SELECT event_id, topic, event_type, event_key, payload_json, retry_count
            FROM trade_outbox_events
            WHERE publish_status IN ('pending', 'failed')
              AND retry_count < %s
              AND (next_retry_at IS NULL OR next_retry_at <= UTC_TIMESTAMP())
            ORDER BY created_at ASC
            LIMIT %s
            """,
            (
                self._max_retries,
                max(1, min(int(limit or 50), 200)),
            ),
        ) or []

    def start(self) -> None:
        if self._publisher_thread and self._publisher_thread.is_alive():
            return

        self.repair_state()
        self._stop_event.clear()
        self._publisher_thread = threading.Thread(target=self._publish_loop, name="trade-outbox-relay", daemon=True)
        self._publisher_thread.start()

        if settings.KAFKA_ENABLED and KAFKA_CONSUMER_AVAILABLE:
            self._consumer_thread = threading.Thread(target=self._consume_loop, name="trade-event-inbox", daemon=True)
            self._consumer_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        for thread in (self._publisher_thread, self._consumer_thread):
            if thread and thread.is_alive():
                thread.join(timeout=2)

    def flush_pending(self, limit: int = 50) -> int:
        rows = self._load_publish_candidates(limit)
        if rows and not settings.KAFKA_ENABLED:
            self._last_error = "Kafka disabled; outbox relay paused"
            return 0

        published = 0
        for row in rows:
            payload_raw = row.get("payload_json")
            payload = payload_raw
            if isinstance(payload_raw, str):
                try:
                    payload = json.loads(payload_raw)
                except Exception:
                    payload = {"raw": payload_raw}

            ok = kafka_bus.publish(
                row.get("topic") or settings.KAFKA_TRADE_EVENT_TOPIC,
                {
                    "eventId": row.get("event_id"),
                    "eventType": row.get("event_type"),
                    "payload": payload,
                    "publishedAt": datetime.now().isoformat(),
                },
                key=row.get("event_key") or row.get("event_id"),
            )

            if ok:
                DbUtil.execute_sql(
                    """
                    UPDATE trade_outbox_events
                    SET publish_status = 'published',
                        published_at = CURRENT_TIMESTAMP,
                        next_retry_at = NULL,
                        last_error = NULL
                    WHERE event_id = %s
                    """,
                    (row.get("event_id"),),
                )
                published += 1
                self._last_publish_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            else:
                retry_count = int(row.get("retry_count") or 0) + 1
                should_dead_letter = retry_count >= self._max_retries
                retry_delay = min(self._base_retry_seconds * (2 ** max(retry_count - 1, 0)), self._max_retry_seconds)
                next_retry_sql = "NULL" if should_dead_letter else f"DATE_ADD(UTC_TIMESTAMP(), INTERVAL {int(retry_delay)} SECOND)"
                next_status = "dead_letter" if should_dead_letter else "failed"
                DbUtil.execute_sql(
                    f"""
                    UPDATE trade_outbox_events
                    SET publish_status = %s,
                        retry_count = retry_count + 1,
                        last_error = %s,
                        next_retry_at = {next_retry_sql},
                        dead_letter_at = CASE
                            WHEN %s = 'dead_letter' THEN CURRENT_TIMESTAMP
                            ELSE dead_letter_at
                        END
                    WHERE event_id = %s
                    """,
                    (
                        next_status,
                        str(kafka_bus.get_status().get("lastError") or "Kafka publish failed")[:255],
                        next_status,
                        row.get("event_id"),
                    ),
                )
                self._last_error = str(kafka_bus.get_status().get("lastError") or "Kafka publish failed")
        return published

    def _publish_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.flush_pending(limit=80)
            except Exception as exc:
                self._last_error = str(exc)
            time.sleep(2)

    def _consume_loop(self) -> None:
        if not settings.KAFKA_ENABLED or not KAFKA_CONSUMER_AVAILABLE:
            return

        consumer = None
        try:
            consumer = KafkaConsumer(
                settings.KAFKA_TRADE_COMMAND_TOPIC,
                settings.KAFKA_TRADE_EVENT_TOPIC,
                bootstrap_servers=settings.get_kafka_config().get("brokers"),
                group_id=f"{settings.KAFKA_CONSUMER_GROUP}-trade-service",
                auto_offset_reset="latest",
                enable_auto_commit=True,
                consumer_timeout_ms=1000,
                value_deserializer=lambda value: json.loads(value.decode("utf-8")),
            )
            while not self._stop_event.is_set():
                messages = consumer.poll(timeout_ms=1000, max_records=20)
                if not messages:
                    continue
                for records in messages.values():
                    for message in records:
                        payload = message.value or {}
                        event_id = str(payload.get("eventId") or uuid.uuid4().hex)
                        try:
                            DbUtil.execute_sql(
                                """
                                INSERT IGNORE INTO trade_event_inbox (event_id, topic, event_key, payload_json)
                                VALUES (%s, %s, %s, %s)
                                """,
                                (
                                    event_id,
                                    message.topic,
                                    getattr(message, "key", None).decode("utf-8") if getattr(message, "key", None) else None,
                                    _serialize_payload(payload),
                                ),
                            )
                            self._last_consume_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        except Exception as exc:
                            self._last_error = str(exc)
        except Exception as exc:
            self._last_error = str(exc)
        finally:
            if consumer is not None:
                try:
                    consumer.close()
                except Exception:
                    pass

    def get_status(self) -> Dict[str, Any]:
        row = DbUtil.fetch_one(
            """
            SELECT
                SUM(CASE WHEN publish_status = 'pending' THEN 1 ELSE 0 END) AS pending_count,
                SUM(CASE WHEN publish_status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
                SUM(CASE WHEN publish_status = 'published' THEN 1 ELSE 0 END) AS published_count,
                SUM(CASE WHEN publish_status = 'dead_letter' THEN 1 ELSE 0 END) AS dead_letter_count
            FROM trade_outbox_events
            """
        ) or {}
        return {
            "publisherRunning": bool(self._publisher_thread and self._publisher_thread.is_alive()),
            "consumerRunning": bool(self._consumer_thread and self._consumer_thread.is_alive()),
            "pendingCount": int(row.get("pending_count") or 0),
            "failedCount": int(row.get("failed_count") or 0),
            "publishedCount": int(row.get("published_count") or 0),
            "deadLetterCount": int(row.get("dead_letter_count") or 0),
            "lastPublishAt": self._last_publish_at,
            "lastConsumeAt": self._last_consume_at,
            "lastRepairAt": self._last_repair_at,
            "lastError": self._last_error,
        }


outbox_relay = OutboxRelay()
