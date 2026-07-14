from __future__ import annotations

from datetime import datetime
from urllib import error as urlerror
from urllib import request as urlrequest

from config.settings import settings
from core.broker.BrokerInterface import BrokerManager
from core.platform.SystemTaskService import SystemTaskService
from utils.DbUtil import DbUtil
from utils.kafka_bus import kafka_bus
from utils.rate_limiter import circuit_breakers
from utils.redis_client import redis_client
from utils.websocket import quote_pusher, ws_manager


class ServiceGovernanceService:
    @classmethod
    def get_snapshot(cls) -> dict[str, object]:
        mysql_ok = False
        try:
            mysql_ok = bool(DbUtil.query_one("SELECT 1"))
        except Exception:
            mysql_ok = False

        return {
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "runtime": {
                "environment": settings.APP_ENV,
                "debug": bool(settings.APP_DEBUG),
                "corsOrigins": settings.get_cors_origins(),
                "redisClusterEnabled": bool(settings.REDIS_CLUSTER_ENABLED),
                "kafkaEnabled": bool(settings.KAFKA_ENABLED),
                "timescaleEnabled": bool(settings.TIMESCALE_ENABLED),
                "websocketEnabled": bool(settings.WEBSOCKET_ENABLED),
            },
            "services": {
                "mysql": "connected" if mysql_ok else "disconnected",
                "redis": "connected" if redis_client.ping() else "disconnected",
                "kafka": kafka_bus.get_status(),
                "tradeService": cls._trade_service_status(),
                "websocket": {**quote_pusher.get_runtime_status(), "connections": ws_manager.get_stats()},
            },
            "brokers": BrokerManager.list_supported_brokers(),
            "circuits": cls._list_circuits(),
            "tasks": cls._task_summary(),
        }

    @staticmethod
    def _list_circuits() -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for name, breaker in sorted(circuit_breakers.items(), key=lambda item: item[0]):
            last_failure = getattr(breaker, "last_failure_time", None)
            items.append(
                {
                    "name": name,
                    "state": breaker.get_state(),
                    "failureCount": int(getattr(breaker, "failure_count", 0) or 0),
                    "successCount": int(getattr(breaker, "success_count", 0) or 0),
                    "recoveryTimeout": int(getattr(breaker, "recovery_timeout", 0) or 0),
                    "lastFailureAt": datetime.fromtimestamp(last_failure).strftime("%Y-%m-%d %H:%M:%S")
                    if last_failure
                    else None,
                }
            )
        return items

    @staticmethod
    def _task_summary() -> dict[str, object]:
        policies = SystemTaskService.list_policies()
        enabled_count = sum(1 for item in policies if item.get("enabled"))
        running_count = sum(1 for item in policies if (item.get("status") or {}).get("state") == "running")
        return {
            "enabledCount": enabled_count,
            "runningCount": running_count,
            "totalCount": len(policies),
            "items": policies,
        }

    @staticmethod
    def _trade_service_status() -> dict[str, object]:
        status = {
            "enabled": bool(settings.TRADE_SERVICE_ENABLED),
            "url": settings.TRADE_SERVICE_URL,
            "connected": False,
            "detail": None,
        }
        if not settings.TRADE_SERVICE_ENABLED or not settings.TRADE_SERVICE_URL:
            return status

        try:
            with urlrequest.urlopen(f"{settings.TRADE_SERVICE_URL.rstrip('/')}/health", timeout=2) as response:
                status["connected"] = response.status == 200
                status["detail"] = response.read().decode("utf-8")
        except urlerror.URLError as exc:
            status["detail"] = str(exc)
        except Exception as exc:
            status["detail"] = str(exc)
        return status
