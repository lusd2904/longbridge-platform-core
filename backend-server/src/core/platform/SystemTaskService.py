from __future__ import annotations

import json
import threading
from typing import Dict, List, Optional

from utils.DbUtil import DbUtil


class SystemTaskService:
    _schema_ready = False
    _lock = threading.Lock()

    DEFAULT_POLICIES: Dict[str, Dict[str, object]] = {
        "recommendation_refresh": {
            "taskName": "智能推荐刷新",
            "category": "analysis",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 1800,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 18,
            "batchSize": 12,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "后台定期刷新推荐结果。"
        },
        "market_universe_daily_sync": {
            "taskName": "市场底库全量同步",
            "category": "market",
            "scheduleType": "daily",
            "enabled": True,
            "intervalSeconds": None,
            "runHour": 6,
            "runMinute": 0,
            "maxRequestsPerMinute": 10,
            "batchSize": 3,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "每天同步股票与 ETF 标的清单和基础快照。"
        },
        "market_insight_refresh": {
            "taskName": "市场动态扫描",
            "category": "market",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 900,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 12,
            "batchSize": 18,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "工作台大盘动态和基准指数快照。"
        },
        "historical_market_data_daily_sync": {
            "taskName": "历史行情增量同步",
            "category": "history",
            "scheduleType": "daily",
            "enabled": True,
            "intervalSeconds": None,
            "runHour": 7,
            "runMinute": 10,
            "maxRequestsPerMinute": 8,
            "batchSize": 240,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "每天增量同步重点标的历史日线。"
        },
        "market_history_universe_backfill": {
            "taskName": "全市场历史慢补数",
            "category": "history",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 900,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 4,
            "batchSize": 2,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "后台慢速补全全市场股票与 ETF 历史行情和技术指标。"
        },
        "symbol_indicator_daily_refresh": {
            "taskName": "技术指标日刷新",
            "category": "history",
            "scheduleType": "daily",
            "enabled": True,
            "intervalSeconds": None,
            "runHour": 7,
            "runMinute": 40,
            "maxRequestsPerMinute": 0,
            "batchSize": 1500,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "基于历史行情生成日/周/月/季技术指标快照。"
        },
        "daily_market_ai_scan": {
            "taskName": "市场 AI 技术扫描",
            "category": "analysis",
            "scheduleType": "daily",
            "enabled": True,
            "intervalSeconds": None,
            "runHour": 8,
            "runMinute": 20,
            "maxRequestsPerMinute": 30,
            "batchSize": 3,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "每天对美股、A股、港股做市场级 AI 技术扫描。"
        },
        "watchlist_pre_open_review": {
            "taskName": "自选股盘前复核",
            "category": "analysis",
            "scheduleType": "daily",
            "enabled": True,
            "intervalSeconds": None,
            "runHour": 8,
            "runMinute": 45,
            "maxRequestsPerMinute": 4,
            "batchSize": 1,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "settings": {
                "autoBuyEnabled": False,
                "autoBuyMaxSymbols": 2,
                "autoBuyMaxAmount": 2000,
                "autoBuyMaxPositionRatio": 0.08,
                "autoBuyMinConfidence": 72
            },
            "description": "每天盘前生成自选股 AI 复核建议；可在任务中心显式开启机会股自动买入，并受仓位控制。"
        },
        "watchlist_post_close_review": {
            "taskName": "自选股盘后复核",
            "category": "analysis",
            "scheduleType": "daily",
            "enabled": True,
            "intervalSeconds": None,
            "runHour": 16,
            "runMinute": 30,
            "maxRequestsPerMinute": 4,
            "batchSize": 1,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "settings": {
                "autoBuyEnabled": False,
                "autoBuyMaxSymbols": 2,
                "autoBuyMaxAmount": 2000,
                "autoBuyMaxPositionRatio": 0.08,
                "autoBuyMinConfidence": 72
            },
            "description": "每天盘后生成自选股 AI 复核建议；可在任务中心显式开启机会股自动买入，并受仓位控制。"
        },
        "watchlist_us_open_ai_trade": {
            "taskName": "美股开盘 AI 自动交易",
            "category": "trade",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 900,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 4,
            "batchSize": 1,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "settings": {
                "autoTradeEnabled": True,
                "maxSymbols": 5,
                "targetPortfolioRatio": 0.70,
                "minConfidence": 72,
                "strategyProfile": "balanced",
                "market": "US",
                "regularSessionOnly": True,
                "refreshRealtimePrice": True,
                "requireRealtimePrice": True,
                "maxDailySubmittedOrders": 10,
                "maxDailyNotionalRatio": 0.70
            },
            "description": "美股常规开盘期间每 15 分钟扫描自选股池并触发 AI 自动交易，默认买入最多 5 只、总持仓占总资金 70%，下单前刷新券商实时价，并受纸账户、日内预算与交易边界保护。"
        },
        "daily_symbol_trend_ai_scan": {
            "taskName": "逐股 AI 趋势扫描",
            "category": "analysis",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 60,
            "runHour": 18,
            "runMinute": 40,
            "maxRequestsPerMinute": 20,
            "batchSize": 24,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "每天按批次扫描全市场股票和 ETF 截止昨日的趋势结果并落库。"
        },
        "finance_briefing_refresh": {
            "taskName": "财经信息刷新",
            "category": "market",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 900,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 0,
            "batchSize": 20,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "定期生成财经信息和市场简报。"
        },
        "account_asset_snapshot_refresh": {
            "taskName": "账户资产快照刷新",
            "category": "readmodel",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 300,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 12,
            "batchSize": 20,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "按账户固化总资产、现金、买力等展示快照，供工作台和个人中心默认读库。"
        },
        "position_snapshot_refresh": {
            "taskName": "持仓快照刷新",
            "category": "readmodel",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 300,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 12,
            "batchSize": 100,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "按账户固化持仓、权重与盈亏快照，供持仓页与风控页优先读取。"
        },
        "risk_overview_snapshot_refresh": {
            "taskName": "风控总览快照刷新",
            "category": "readmodel",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 900,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 6,
            "batchSize": 20,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "固化风险评分、事件摘要与保护单统计。"
        },
        "quote_snapshot_refresh": {
            "taskName": "展示行情快照刷新",
            "category": "readmodel",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 300,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 12,
            "batchSize": 180,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "为市场页、股票池、标的详情固化展示型最新价快照，前端默认读库，再由 WebSocket 覆盖。"
        },
        "symbol_content_cache_refresh": {
            "taskName": "标的内容缓存预热",
            "category": "readmodel",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 1800,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 6,
            "batchSize": 9,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "预热热门标的公告、资讯与讨论缓存，减少页面直拉外部内容。"
        },
        "websocket_quote_stream": {
            "taskName": "WebSocket 行情推送",
            "category": "market",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 2,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 20,
            "batchSize": 120,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": False,
            "description": "为行情页推送实时行情，支持后台限速与批量控制。"
        },
        "position_monitor": {
            "taskName": "持仓规则监控",
            "category": "user",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 300,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 10,
            "batchSize": 50,
            "allowAdminToggle": True,
            "userScope": "user",
            "singleRun": False,
            "description": "按用户规则监控持仓与告警。"
        },
        "quant_trading": {
            "taskName": "自选池量化交易",
            "category": "user",
            "scheduleType": "interval",
            "enabled": True,
            "intervalSeconds": 900,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 30,
            "batchSize": 20,
            "allowAdminToggle": True,
            "userScope": "user",
            "singleRun": False,
            "description": "只对用户自选股池做多因子策略扫描；自动执行仍受量化开关、账户权限、仓位和长桥模拟账户约束。"
        },
        "bootstrap_market_history_2024": {
            "taskName": "2024起全量历史回补",
            "category": "bootstrap",
            "scheduleType": "manual",
            "enabled": False,
            "intervalSeconds": None,
            "runHour": None,
            "runMinute": None,
            "maxRequestsPerMinute": 6,
            "batchSize": 160,
            "allowAdminToggle": True,
            "userScope": "system",
            "singleRun": True,
            "description": "一次性回补 2024 年以来股票和 ETF 历史数据，完成后自动关闭。"
        }
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
                CREATE TABLE IF NOT EXISTS system_task_policies (
                    task_key VARCHAR(80) NOT NULL PRIMARY KEY,
                    task_name VARCHAR(120) NOT NULL,
                    category VARCHAR(32) DEFAULT 'general',
                    schedule_type VARCHAR(16) DEFAULT 'interval',
                    enabled TINYINT(1) DEFAULT 1,
                    interval_seconds INT DEFAULT NULL,
                    run_hour INT DEFAULT NULL,
                    run_minute INT DEFAULT NULL,
                    max_requests_per_minute INT DEFAULT 0,
                    batch_size INT DEFAULT 0,
                    allow_admin_toggle TINYINT(1) DEFAULT 1,
                    user_scope VARCHAR(16) DEFAULT 'system',
                    single_run TINYINT(1) DEFAULT 0,
                    last_cursor VARCHAR(255) DEFAULT NULL,
                    settings_json JSON DEFAULT NULL,
                    description VARCHAR(255) DEFAULT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_category_enabled (category, enabled)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cls._seed_defaults()
            cls._schema_ready = True

    @classmethod
    def _seed_defaults(cls) -> None:
        for task_key, policy in cls.DEFAULT_POLICIES.items():
            DbUtil.execute_sql(
                """
                INSERT INTO system_task_policies (
                    task_key, task_name, category, schedule_type, enabled, interval_seconds,
                    run_hour, run_minute, max_requests_per_minute, batch_size, allow_admin_toggle,
                    user_scope, single_run, settings_json, description
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    task_name = VALUES(task_name),
                    category = VALUES(category),
                    schedule_type = VALUES(schedule_type),
                    description = VALUES(description),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    task_key,
                    policy["taskName"],
                    policy["category"],
                    policy["scheduleType"],
                    1 if policy["enabled"] else 0,
                    policy["intervalSeconds"],
                    policy["runHour"],
                    policy["runMinute"],
                    policy["maxRequestsPerMinute"],
                    policy["batchSize"],
                    1 if policy["allowAdminToggle"] else 0,
                    policy["userScope"],
                    1 if policy["singleRun"] else 0,
                    json.dumps(policy.get("settings", {}) or {}, ensure_ascii=False),
                    policy["description"]
                )
            )

    @classmethod
    def get_policy(cls, task_key: str) -> Dict[str, object]:
        cls.ensure_schema()
        base = dict(cls.DEFAULT_POLICIES.get(task_key, {}))
        row = DbUtil.fetch_one(
            """
            SELECT task_key, task_name, category, schedule_type, enabled, interval_seconds,
                   run_hour, run_minute, max_requests_per_minute, batch_size,
                   allow_admin_toggle, user_scope, single_run, last_cursor,
                   settings_json, description
            FROM system_task_policies
            WHERE task_key = %s
            LIMIT 1
            """,
            (task_key,)
        ) or {}

        if not row and not base:
            return {}

        base_settings = base.get("settings") if isinstance(base.get("settings"), dict) else {}
        stored_settings = cls._json_load(row.get("settings_json"))
        merged = {
            "taskKey": row.get("task_key") or task_key,
            "taskName": row.get("task_name") or base.get("taskName") or task_key,
            "category": row.get("category") or base.get("category") or "general",
            "scheduleType": row.get("schedule_type") or base.get("scheduleType") or "interval",
            "enabled": bool(row.get("enabled") if row else base.get("enabled", True)),
            "intervalSeconds": cls._safe_int(row.get("interval_seconds"), base.get("intervalSeconds")),
            "runHour": cls._safe_int(row.get("run_hour"), base.get("runHour")),
            "runMinute": cls._safe_int(row.get("run_minute"), base.get("runMinute")),
            "maxRequestsPerMinute": cls._safe_int(row.get("max_requests_per_minute"), base.get("maxRequestsPerMinute", 0)) or 0,
            "batchSize": cls._safe_int(row.get("batch_size"), base.get("batchSize", 0)) or 0,
            "allowAdminToggle": bool(row.get("allow_admin_toggle") if row else base.get("allowAdminToggle", True)),
            "userScope": row.get("user_scope") or base.get("userScope") or "system",
            "singleRun": bool(row.get("single_run") if row else base.get("singleRun", False)),
            "lastCursor": row.get("last_cursor"),
            "settings": {
                **base_settings,
                **stored_settings,
            },
            "description": row.get("description") or base.get("description") or ""
        }
        return merged

    @classmethod
    def list_policies(cls) -> List[Dict[str, object]]:
        cls.ensure_schema()
        policies = []
        for task_key in cls.DEFAULT_POLICIES.keys():
            policy = cls.get_policy(task_key)
            status = DbUtil.fetch_one(
                """
                SELECT job_name, last_run_date, last_run_at, status, message
                FROM scheduled_jobs
                WHERE job_name = %s
                LIMIT 1
                """,
                (task_key,)
            ) or {}
            policy["status"] = {
                "jobName": status.get("job_name") or task_key,
                "lastRunDate": status.get("last_run_date").strftime('%Y-%m-%d') if status.get("last_run_date") else None,
                "lastRunAt": status.get("last_run_at").strftime('%Y-%m-%d %H:%M:%S') if status.get("last_run_at") else None,
                "state": status.get("status") or "idle",
                "message": status.get("message") or ""
            }
            policies.append(policy)
        return policies

    @classmethod
    def update_policy(cls, task_key: str, payload: Dict[str, object]) -> Dict[str, object]:
        cls.ensure_schema()
        current = cls.get_policy(task_key)
        if not current:
            raise ValueError("未找到任务策略")

        next_policy = {
            **current,
            "enabled": bool(payload.get("enabled", current["enabled"])),
            "intervalSeconds": cls._safe_int(payload.get("intervalSeconds"), current.get("intervalSeconds")),
            "runHour": cls._safe_int(payload.get("runHour"), current.get("runHour")),
            "runMinute": cls._safe_int(payload.get("runMinute"), current.get("runMinute")),
            "maxRequestsPerMinute": cls._safe_int(payload.get("maxRequestsPerMinute"), current.get("maxRequestsPerMinute")) or 0,
            "batchSize": cls._safe_int(payload.get("batchSize"), current.get("batchSize")) or 0,
            "settings": payload.get("settings", current.get("settings") or {}),
            "description": payload.get("description", current.get("description") or "")
        }

        DbUtil.execute_sql(
            """
            UPDATE system_task_policies
            SET enabled = %s,
                interval_seconds = %s,
                run_hour = %s,
                run_minute = %s,
                max_requests_per_minute = %s,
                batch_size = %s,
                settings_json = %s,
                description = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE task_key = %s
            """,
            (
                1 if next_policy["enabled"] else 0,
                next_policy["intervalSeconds"],
                next_policy["runHour"],
                next_policy["runMinute"],
                next_policy["maxRequestsPerMinute"],
                next_policy["batchSize"],
                json.dumps(next_policy["settings"] or {}, ensure_ascii=False),
                next_policy["description"],
                task_key
            )
        )
        return cls.get_policy(task_key)

    @classmethod
    def set_last_cursor(cls, task_key: str, cursor_value: Optional[str]) -> None:
        cls.ensure_schema()
        DbUtil.execute_sql(
            "UPDATE system_task_policies SET last_cursor = %s, updated_at = CURRENT_TIMESTAMP WHERE task_key = %s",
            (cursor_value, task_key)
        )

    @classmethod
    def mark_single_run_completed(cls, task_key: str, message: str = "一次性任务已完成并自动关闭") -> None:
        cls.ensure_schema()
        DbUtil.execute_sql(
            """
            UPDATE system_task_policies
            SET enabled = 0,
                description = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE task_key = %s
            """,
            (message, task_key)
        )

    @classmethod
    def is_enabled(cls, task_key: str, default: bool = True) -> bool:
        policy = cls.get_policy(task_key)
        if not policy:
            return default
        return bool(policy.get("enabled"))

    @classmethod
    def get_interval(cls, task_key: str, default: int) -> int:
        policy = cls.get_policy(task_key)
        value = cls._safe_int(policy.get("intervalSeconds") if policy else None, default)
        return max(30, int(value or default))

    @classmethod
    def get_daily_time(cls, task_key: str, default_hour: int, default_minute: int) -> tuple[int, int]:
        policy = cls.get_policy(task_key)
        hour = cls._safe_int(policy.get("runHour") if policy else None, default_hour)
        minute = cls._safe_int(policy.get("runMinute") if policy else None, default_minute)
        return min(max(int(hour or default_hour), 0), 23), min(max(int(minute or default_minute), 0), 59)

    @classmethod
    def get_batch_size(cls, task_key: str, default: int) -> int:
        policy = cls.get_policy(task_key)
        value = cls._safe_int(policy.get("batchSize") if policy else None, default)
        return max(0, int(value or default))

    @classmethod
    def get_rate_limit(cls, task_key: str, default: int = 0) -> int:
        policy = cls.get_policy(task_key)
        value = cls._safe_int(policy.get("maxRequestsPerMinute") if policy else None, default)
        return max(0, int(value or default))

    @staticmethod
    def _safe_int(value, fallback=None):
        if value in (None, ""):
            return fallback
        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    @staticmethod
    def _json_load(raw_value):
        if isinstance(raw_value, dict):
            return raw_value
        if not raw_value:
            return {}
        try:
            parsed = json.loads(raw_value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
