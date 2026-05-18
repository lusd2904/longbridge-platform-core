"""
Kafka 事件总线封装。
本地开发环境优先保证可用性，连接失败时自动降级但保留状态。
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from config.settings import settings

try:
    from kafka import KafkaProducer
    KAFKA_AVAILABLE = True
except Exception:  # pragma: no cover - 兼容本地未安装依赖
    KafkaProducer = None
    KAFKA_AVAILABLE = False


class KafkaBus:
    def __init__(self) -> None:
        self._producer = None
        self._lock = threading.Lock()
        self._last_error: Optional[str] = None
        self._last_published_at: Optional[str] = None

    @property
    def enabled(self) -> bool:
        return bool(settings.KAFKA_ENABLED and settings.get_kafka_config().get("brokers"))

    def _ensure_producer(self):
        if not self.enabled or not KAFKA_AVAILABLE:
            return None

        if self._producer is not None:
            return self._producer

        with self._lock:
            if self._producer is not None:
                return self._producer
            try:
                self._producer = KafkaProducer(
                    bootstrap_servers=settings.get_kafka_config().get("brokers"),
                    value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
                    key_serializer=lambda value: value.encode("utf-8") if value else None,
                    linger_ms=20,
                    acks=1,
                    retries=1,
                    request_timeout_ms=5000,
                    api_version_auto_timeout_ms=3000
                )
                self._last_error = None
            except Exception as exc:
                self._producer = None
                self._last_error = str(exc)
            return self._producer

    def publish(self, topic: str, payload: Dict[str, Any], *, key: Optional[str] = None) -> bool:
        producer = self._ensure_producer()
        if producer is None:
            return False

        try:
            future = producer.send(topic, key=key, value=payload)
            future.get(timeout=5)
            self._last_error = None
            self._last_published_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return True
        except Exception as exc:
            self._last_error = str(exc)
            return False

    def publish_market_quotes(self, *, account_id: int, quotes: Iterable[Dict[str, Any]]) -> bool:
        payload = {
            "eventType": "market.quotes.snapshot",
            "accountId": int(account_id),
            "quotes": list(quotes),
            "publishedAt": datetime.now().isoformat()
        }
        return self.publish(settings.KAFKA_MARKET_TOPIC, payload, key=f"account:{account_id}")

    def get_status(self) -> Dict[str, Any]:
        producer = self._ensure_producer()
        connected = False
        if producer is not None:
            try:
                connected = bool(producer.bootstrap_connected())
            except Exception:
                connected = False
        if not connected and self._last_published_at and not self._last_error:
            connected = True

        return {
            "enabled": self.enabled,
            "available": KAFKA_AVAILABLE,
            "connected": connected,
            "brokers": settings.get_kafka_config().get("brokers"),
            "marketTopic": settings.KAFKA_MARKET_TOPIC,
            "tradeCommandTopic": settings.KAFKA_TRADE_COMMAND_TOPIC,
            "tradeEventTopic": settings.KAFKA_TRADE_EVENT_TOPIC,
            "lastPublishedAt": self._last_published_at,
            "lastError": self._last_error
        }

    def close(self) -> None:
        with self._lock:
            if self._producer is not None:
                try:
                    self._producer.flush(timeout=5)
                    self._producer.close()
                except Exception:
                    pass
                finally:
                    self._producer = None


kafka_bus = KafkaBus()
