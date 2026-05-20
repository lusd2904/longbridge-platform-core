from __future__ import annotations

import copy
import json
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from utils.DbUtil import DbUtil


class PlatformAccessService:
    _schema_ready = False
    _lock = threading.Lock()
    _bootstrap_cache_lock = threading.Lock()
    _bootstrap_cache: Dict[int, Dict[str, Any]] = {}
    BOOTSTRAP_CACHE_TTL_SECONDS = 15
    DEFAULT_ROLE_CODE = "user"
    OBSOLETE_ROLE_CODES = {"analyst", "viewer"}

    SUBSYSTEM_SEEDS = [
        {
            "subsystem_code": "workspace",
            "title": "仪表盘",
            "description": "登录后的默认总览入口，承载核心经营与交易概览。",
            "icon": "Odometer",
            "sort_index": 10,
            "landing_route_name": "Dashboard",
            "landing_route_path": "/dashboard"
        },
        {
            "subsystem_code": "trading",
            "title": "交易中心",
            "description": "围绕实盘交易、持仓、订单和风险处理的核心交易区。",
            "icon": "Wallet",
            "sort_index": 20,
            "landing_route_name": "Trading",
            "landing_route_path": "/trading"
        },
        {
            "subsystem_code": "market",
            "title": "市场中心",
            "description": "集中承载实时行情、标的检索、股票池、资讯和研究底库。",
            "icon": "Histogram",
            "sort_index": 30,
            "landing_route_name": "MarketData",
            "landing_route_path": "/market"
        },
        {
            "subsystem_code": "analysis",
            "title": "策略研究",
            "description": "用于 AI 研判、策略编排、回测和研究结果复核。",
            "icon": "Cpu",
            "sort_index": 40,
            "landing_route_name": "AIAnalysis",
            "landing_route_path": "/ai-analysis"
        },
        {
            "subsystem_code": "platform",
            "title": "系统管理",
            "description": "用于系统配置、用户体系、菜单授权与任务调度治理。",
            "icon": "Setting",
            "sort_index": 50,
            "landing_route_name": "Settings",
            "landing_route_path": "/settings"
        }
    ]

    ROLE_SEEDS = [
        {
            "role_code": "admin",
            "role_name": "系统管理员",
            "description": "可管理系统、用户、菜单和调度任务，但不查看其他用户量化结果。",
            "priority": 100,
            "capabilities": [
                "dashboard.view",
                "stock.pool.view",
                "market.view",
                "market.detail.view",
                "market.news.view",
                "market.sentiment.view",
                "ai.analysis",
                "recommendations.view",
                "trade.live",
                "positions.view",
                "orders.view",
                "strategy.manage",
                "strategy.backtest",
                "risk.manage",
                "profile.view",
                "notifications.view",
                "settings.manage",
                "tasks.manage",
                "users.manage",
                "menus.manage",
                "roles.manage"
            ]
        },
        {
            "role_code": "user",
            "role_name": "普通用户",
            "description": "仅允许查看市场行情与历史K线，不提供交易与系统管理能力。",
            "priority": 30,
            "capabilities": [
                "market.view",
                "market.detail.view",
                "market.sentiment.view"
            ]
        },
        {
            "role_code": "trader",
            "role_name": "交易用户",
            "description": "可查看行情、绑定券商账户并执行交易。",
            "priority": 70,
            "capabilities": [
                "dashboard.view",
                "market.view",
                "market.detail.view",
                "market.sentiment.view",
                "trade.live",
                "positions.view",
                "orders.view",
                "profile.view",
                "notifications.view",
                "quant.use"
            ]
        }
    ]

    MENU_SEEDS = [
        {"menu_code": "dashboard", "title": "仪表盘", "route_name": "Dashboard", "route_path": "/dashboard", "menu_group": "overview", "subsystem_code": "workspace", "icon": "Odometer", "sort_index": 10, "required_capability": "dashboard.view"},
        {"menu_code": "trading", "title": "交易台", "route_name": "Trading", "route_path": "/trading", "menu_group": "trading", "subsystem_code": "trading", "icon": "Wallet", "sort_index": 20, "required_capability": "trade.live"},
        {"menu_code": "positions", "title": "持仓管理", "route_name": "Positions", "route_path": "/positions", "menu_group": "trading", "subsystem_code": "trading", "icon": "Coin", "sort_index": 30, "required_capability": "positions.view"},
        {"menu_code": "orders", "title": "订单管理", "route_name": "Orders", "route_path": "/orders", "menu_group": "trading", "subsystem_code": "trading", "icon": "List", "sort_index": 40, "required_capability": "orders.view"},
        {"menu_code": "stock-pool", "title": "股票池", "route_name": "StockPool", "route_path": "/stock-pool", "menu_group": "analysis", "subsystem_code": "market", "icon": "Collection", "sort_index": 50, "required_capability": "stock.pool.view"},
        {"menu_code": "watchlist-pool", "title": "自选股票池", "route_name": "WatchlistPool", "route_path": "/watchlist-pool", "menu_group": "analysis", "subsystem_code": "market", "icon": "Star", "sort_index": 55, "required_capability": "stock.pool.view"},
        {"menu_code": "ai-analysis", "title": "AI研判", "route_name": "AIAnalysis", "route_path": "/ai-analysis", "menu_group": "analysis", "subsystem_code": "analysis", "icon": "Cpu", "sort_index": 60, "required_capability": "ai.analysis"},
        {"menu_code": "strategy", "title": "策略管理", "route_name": "Strategy", "route_path": "/strategy", "menu_group": "strategy", "subsystem_code": "analysis", "icon": "TrendCharts", "sort_index": 70, "required_capability": "strategy.manage"},
        {"menu_code": "backtest", "title": "策略回测", "route_name": "Backtest", "route_path": "/backtest", "menu_group": "strategy", "subsystem_code": "analysis", "icon": "DataLine", "sort_index": 80, "required_capability": "strategy.backtest"},
        {"menu_code": "risk", "title": "风控管理", "route_name": "RiskManagement", "route_path": "/risk", "menu_group": "risk", "subsystem_code": "trading", "icon": "Warning", "sort_index": 90, "required_capability": "risk.manage"},
        {"menu_code": "market", "title": "实时行情", "route_name": "MarketData", "route_path": "/market", "menu_group": "market", "subsystem_code": "market", "icon": "Histogram", "sort_index": 100, "required_capability": "market.view"},
        {"menu_code": "kline", "title": "历史K线", "route_name": "Kline", "route_path": "/kline", "menu_group": "market", "subsystem_code": "market", "icon": "TrendCharts", "sort_index": 110, "required_capability": "market.detail.view"},
        {"menu_code": "recommendations", "title": "智能推荐", "route_name": "Recommendations", "route_path": "/recommendations", "menu_group": "market", "subsystem_code": "market", "icon": "Star", "sort_index": 120, "required_capability": "recommendations.view"},
        {"menu_code": "sentiment-center", "title": "市场舆情", "route_name": "MarketSentiment", "route_path": "/sentiment-center", "menu_group": "market", "subsystem_code": "market", "icon": "Cpu", "sort_index": 125, "required_capability": "market.sentiment.view"},
        {"menu_code": "finance-news", "title": "财经快讯", "route_name": "FinanceNews", "route_path": "/finance-news", "menu_group": "market", "subsystem_code": "market", "icon": "Bell", "sort_index": 130, "required_capability": "market.news.view"},
        {"menu_code": "profile", "title": "个人中心", "route_name": "Profile", "route_path": "/profile", "menu_group": "user", "subsystem_code": "platform", "icon": "User", "sort_index": 140, "required_capability": "profile.view"},
        {"menu_code": "broker-management", "title": "券商连接", "route_name": "BrokerManagement", "route_path": "/broker-management", "menu_group": "user", "subsystem_code": "platform", "icon": "Wallet", "sort_index": 145, "required_capability": "profile.view"},
        {"menu_code": "notifications", "title": "消息通知", "route_name": "Notifications", "route_path": "/notifications", "menu_group": "user", "subsystem_code": "platform", "icon": "Bell", "sort_index": 150, "required_capability": "notifications.view"},
        {"menu_code": "settings", "title": "系统设置", "route_name": "Settings", "route_path": "/settings", "menu_group": "system", "subsystem_code": "platform", "icon": "Setting", "sort_index": 160, "required_capability": "settings.manage"},
        {"menu_code": "user-management", "title": "用户管理", "route_name": "UserManagement", "route_path": "/user-management", "menu_group": "system", "subsystem_code": "platform", "icon": "UserFilled", "sort_index": 170, "required_capability": "users.manage"},
        {"menu_code": "scheduler-center", "title": "任务中心", "route_name": "SchedulerCenter", "route_path": "/scheduler-center", "menu_group": "system", "subsystem_code": "platform", "icon": "Timer", "sort_index": 180, "required_capability": "tasks.manage"},
        {"menu_code": "history-coverage", "title": "历史补价覆盖", "route_name": "HistoryCoverage", "route_path": "/history-coverage", "menu_group": "system", "subsystem_code": "platform", "icon": "DataLine", "sort_index": 185, "required_capability": "tasks.manage"}
    ]

    GROUP_TITLES = {
        "overview": "总览",
        "trading": "交易",
        "analysis": "扫描",
        "strategy": "策略",
        "market": "市场",
        "risk": "风控",
        "user": "个人",
        "system": "系统"
    }

    @classmethod
    def ensure_schema(cls) -> None:
        if cls._schema_ready:
            return

        with cls._lock:
            if cls._schema_ready:
                return

            cls._ensure_user_columns()
            DbUtil.execute_sql(
                """
                CREATE TABLE IF NOT EXISTS platform_subsystems (
                    subsystem_code VARCHAR(32) NOT NULL PRIMARY KEY,
                    title VARCHAR(80) NOT NULL,
                    description VARCHAR(255) DEFAULT NULL,
                    icon VARCHAR(40) DEFAULT NULL,
                    sort_index INT DEFAULT 0,
                    landing_route_name VARCHAR(80) DEFAULT NULL,
                    landing_route_path VARCHAR(120) DEFAULT NULL,
                    enabled TINYINT(1) DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_sort (sort_index)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            DbUtil.execute_sql(
                """
                CREATE TABLE IF NOT EXISTS platform_roles (
                    role_code VARCHAR(32) NOT NULL PRIMARY KEY,
                    role_name VARCHAR(80) NOT NULL,
                    description VARCHAR(255) DEFAULT NULL,
                    priority INT DEFAULT 0,
                    capabilities_json JSON DEFAULT NULL,
                    is_system TINYINT(1) DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_priority (priority)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            DbUtil.execute_sql(
                """
                CREATE TABLE IF NOT EXISTS platform_menus (
                    menu_code VARCHAR(64) NOT NULL PRIMARY KEY,
                    title VARCHAR(80) NOT NULL,
                    route_name VARCHAR(80) DEFAULT NULL,
                    route_path VARCHAR(120) DEFAULT NULL,
                    menu_group VARCHAR(32) DEFAULT NULL,
                    subsystem_code VARCHAR(32) DEFAULT NULL,
                    icon VARCHAR(40) DEFAULT NULL,
                    sort_index INT DEFAULT 0,
                    required_capability VARCHAR(80) DEFAULT NULL,
                    enabled TINYINT(1) DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    INDEX idx_group_sort (menu_group, sort_index),
                    INDEX idx_subsystem_sort (subsystem_code, sort_index)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )
            cls._ensure_platform_schema_columns()
            DbUtil.execute_sql(
                """
                CREATE TABLE IF NOT EXISTS platform_role_menus (
                    role_code VARCHAR(32) NOT NULL,
                    menu_code VARCHAR(64) NOT NULL,
                    can_view TINYINT(1) DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    PRIMARY KEY (role_code, menu_code),
                    INDEX idx_menu_code (menu_code)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
                """
            )

            cls._seed_roles()
            cls._seed_subsystems()
            cls._seed_menus()
            cls._cleanup_obsolete_roles()
            cls._sync_user_defaults()
            cls._schema_ready = True

    @classmethod
    def _ensure_user_columns(cls) -> None:
        desired_columns = {
            "platform_role_code": "VARCHAR(32) DEFAULT NULL COMMENT '平台角色编码'",
            "quant_api_enabled": "TINYINT(1) DEFAULT 0 COMMENT '是否允许量化交易 API'",
            "task_admin_enabled": "TINYINT(1) DEFAULT 0 COMMENT '是否允许管理任务中心'",
            "dashboard_layout": "VARCHAR(32) DEFAULT 'workbench' COMMENT '工作台布局'",
            "preferred_subsystem_code": "VARCHAR(32) DEFAULT 'workspace' COMMENT '默认进入的子系统编码'"
        }

        for column_name, column_sql in desired_columns.items():
            cls._ensure_column("users", column_name, column_sql)

    @classmethod
    def _ensure_platform_schema_columns(cls) -> None:
        cls._ensure_column(
            "platform_menus",
            "subsystem_code",
            "VARCHAR(32) DEFAULT 'workspace' COMMENT '所属子系统编码'"
        )

    @classmethod
    def _ensure_column(cls, table_name: str, column_name: str, column_sql: str) -> None:
        table_exists = DbUtil.query_one(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = DATABASE() AND table_name = %s
            """,
            (table_name,)
        )
        if not table_exists:
            return

        exists = DbUtil.query_one(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s
            """,
            (table_name, column_name)
        )
        if not exists:
            DbUtil.execute_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")

    @classmethod
    def _seed_roles(cls) -> None:
        for role in cls.ROLE_SEEDS:
            DbUtil.execute_sql(
                """
                INSERT INTO platform_roles (role_code, role_name, description, priority, capabilities_json, is_system)
                VALUES (%s, %s, %s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    role_name = IF(is_system = 1, VALUES(role_name), role_name),
                    description = IF(is_system = 1, VALUES(description), description),
                    priority = IF(is_system = 1, VALUES(priority), priority),
                    capabilities_json = IF(is_system = 1, VALUES(capabilities_json), capabilities_json),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    role["role_code"],
                    role["role_name"],
                    role["description"],
                    role["priority"],
                    json.dumps(role["capabilities"], ensure_ascii=False)
                )
            )

    @classmethod
    def _cleanup_obsolete_roles(cls) -> None:
        obsolete_role_codes = tuple(sorted(cls.OBSOLETE_ROLE_CODES))
        if not obsolete_role_codes:
            return

        placeholders = ", ".join(["%s"] * len(obsolete_role_codes))
        DbUtil.execute_sql(
            f"""
            UPDATE users
            SET platform_role_code = %s
            WHERE role <> 'admin'
              AND platform_role_code IN ({placeholders})
            """,
            (cls.DEFAULT_ROLE_CODE, *obsolete_role_codes)
        )
        DbUtil.execute_sql(
            f"DELETE FROM platform_role_menus WHERE role_code IN ({placeholders})",
            obsolete_role_codes
        )
        DbUtil.execute_sql(
            f"DELETE FROM platform_roles WHERE is_system = 1 AND role_code IN ({placeholders})",
            obsolete_role_codes
        )

    @classmethod
    def _seed_subsystems(cls) -> None:
        for subsystem in cls.SUBSYSTEM_SEEDS:
            DbUtil.execute_sql(
                """
                INSERT INTO platform_subsystems (
                    subsystem_code, title, description, icon, sort_index, landing_route_name, landing_route_path, enabled
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    description = VALUES(description),
                    icon = VALUES(icon),
                    sort_index = VALUES(sort_index),
                    landing_route_name = VALUES(landing_route_name),
                    landing_route_path = VALUES(landing_route_path),
                    enabled = VALUES(enabled),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    subsystem["subsystem_code"],
                    subsystem["title"],
                    subsystem["description"],
                    subsystem["icon"],
                    subsystem["sort_index"],
                    subsystem["landing_route_name"],
                    subsystem["landing_route_path"]
                )
            )

    @classmethod
    def _seed_menus(cls) -> None:
        for menu in cls.MENU_SEEDS:
            DbUtil.execute_sql(
                """
                INSERT INTO platform_menus (
                    menu_code, title, route_name, route_path, menu_group, subsystem_code, icon, sort_index, required_capability, enabled
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    route_name = VALUES(route_name),
                    route_path = VALUES(route_path),
                    menu_group = VALUES(menu_group),
                    subsystem_code = VALUES(subsystem_code),
                    icon = VALUES(icon),
                    sort_index = VALUES(sort_index),
                    required_capability = VALUES(required_capability),
                    enabled = VALUES(enabled),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    menu["menu_code"],
                    menu["title"],
                    menu["route_name"],
                    menu["route_path"],
                    menu["menu_group"],
                    menu["subsystem_code"],
                    menu["icon"],
                    menu["sort_index"],
                    menu["required_capability"]
                )
            )

        role_caps = {role["role_code"]: set(role["capabilities"]) for role in cls.ROLE_SEEDS}
        for role_code, capabilities in role_caps.items():
            for menu in cls.MENU_SEEDS:
                can_view = 1 if (not menu["required_capability"] or menu["required_capability"] in capabilities or role_code == "admin") else 0
                DbUtil.execute_sql(
                    """
                    INSERT INTO platform_role_menus (role_code, menu_code, can_view)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        can_view = IF(
                            VALUES(can_view) = 1 AND (can_view IS NULL OR can_view = 0),
                            VALUES(can_view),
                            can_view
                        ),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (role_code, menu["menu_code"], can_view)
                )

    @classmethod
    def _sync_user_defaults(cls) -> None:
        DbUtil.execute_sql(
            """
            UPDATE users
            SET platform_role_code = CASE
                WHEN role = 'admin' THEN 'admin'
                WHEN platform_role_code IS NULL OR platform_role_code = '' THEN %s
                WHEN platform_role_code IN ('analyst', 'viewer') THEN %s
                ELSE platform_role_code
            END
            """,
            (cls.DEFAULT_ROLE_CODE, cls.DEFAULT_ROLE_CODE)
        )
        DbUtil.execute_sql(
            """
            UPDATE users
            SET task_admin_enabled = 1
            WHERE role = 'admin'
            """
        )
        DbUtil.execute_sql(
            """
            UPDATE users
            SET preferred_subsystem_code = 'workspace'
            WHERE preferred_subsystem_code IS NULL OR preferred_subsystem_code = ''
            """
        )

    @classmethod
    def list_roles(cls) -> List[Dict[str, object]]:
        cls.ensure_schema()
        menus = cls.list_menus()
        menu_capability_map = {
            str(item.get("code") or ""): str(item.get("requiredCapability") or "").strip()
            for item in menus
        }
        all_menu_capabilities = {
            capability
            for capability in menu_capability_map.values()
            if capability
        }
        role_menu_map = cls._role_menu_map()
        rows = DbUtil.fetch_all(
            """
            SELECT role_code, role_name, description, priority, capabilities_json, is_system
            FROM platform_roles
            ORDER BY priority DESC, role_code ASC
            """
        )
        roles = []
        for row in rows:
            capabilities = cls._json_load(row.get("capabilities_json"))
            menu_codes = role_menu_map.get(str(row.get("role_code") or ""), [])
            roles.append({
                "roleCode": row.get("role_code"),
                "roleName": row.get("role_name"),
                "description": row.get("description"),
                "priority": int(row.get("priority") or 0),
                "capabilities": capabilities,
                "menuCodes": menu_codes,
                "menuCount": len(menu_codes),
                "isSystem": bool(row.get("is_system")),
                "extraCapabilities": sorted([
                    capability for capability in capabilities
                    if capability and capability not in all_menu_capabilities
                ])
            })
        return roles

    @classmethod
    def list_menus(cls) -> List[Dict[str, object]]:
        cls.ensure_schema()
        rows = DbUtil.fetch_all(
            """
            SELECT m.menu_code, m.title, m.route_name, m.route_path, m.menu_group, m.subsystem_code, m.icon,
                   m.sort_index, m.required_capability, m.enabled,
                   s.title AS subsystem_title,
                   s.sort_index AS subsystem_sort_index
            FROM platform_menus m
            LEFT JOIN platform_subsystems s
              ON s.subsystem_code = m.subsystem_code
            ORDER BY COALESCE(s.sort_index, 999), m.menu_group ASC, m.sort_index ASC
            """
        ) or []
        return [
            {
                "code": row.get("menu_code"),
                "title": row.get("title"),
                "routeName": row.get("route_name"),
                "path": row.get("route_path"),
                "group": row.get("menu_group"),
                "groupTitle": cls.GROUP_TITLES.get(row.get("menu_group"), row.get("menu_group")),
                "subsystemCode": row.get("subsystem_code") or "workspace",
                "subsystemTitle": row.get("subsystem_title") or "",
                "subsystemSortIndex": int(row.get("subsystem_sort_index") or 999),
                "icon": row.get("icon") or "Menu",
                "sortIndex": int(row.get("sort_index") or 0),
                "requiredCapability": row.get("required_capability") or "",
                "enabled": bool(row.get("enabled"))
            }
            for row in rows
        ]

    @classmethod
    def upsert_role(
        cls,
        role_code: str,
        role_name: str,
        description: str = "",
        priority: int = 0,
        menu_codes: Optional[List[str]] = None,
        extra_capabilities: Optional[List[str]] = None,
        is_system: Optional[bool] = None
    ) -> Dict[str, object]:
        cls.ensure_schema()
        normalized_role_code = str(role_code or "").strip().lower()
        normalized_role_name = str(role_name or "").strip()
        if not normalized_role_code:
            raise ValueError("角色编码不能为空")
        if not normalized_role_name:
            raise ValueError("角色名称不能为空")

        menus = cls.list_menus()
        menu_capability_map = {
            str(item.get("code") or ""): str(item.get("requiredCapability") or "").strip()
            for item in menus
        }
        all_menu_codes = list(menu_capability_map.keys())
        all_menu_capabilities = {
            capability
            for capability in menu_capability_map.values()
            if capability
        }
        current_row = DbUtil.fetch_one(
            """
            SELECT role_code, capabilities_json, is_system
            FROM platform_roles
            WHERE role_code = %s
            LIMIT 1
            """,
            (normalized_role_code,)
        ) or {}
        current_capabilities = set(cls._json_load(current_row.get("capabilities_json")))
        selected_menu_codes = [
            code for code in (menu_codes if menu_codes is not None else cls._role_menu_map().get(normalized_role_code, []))
            if code in menu_capability_map
        ]
        preserved_extra_capabilities = (
            {
                str(item).strip() for item in (extra_capabilities or [])
                if str(item or "").strip()
            }
            if extra_capabilities is not None
            else {
                capability for capability in current_capabilities
                if capability and capability not in all_menu_capabilities
            }
        )
        capabilities = sorted(
            {
                menu_capability_map[code]
                for code in selected_menu_codes
                if menu_capability_map.get(code)
            }.union(preserved_extra_capabilities)
        )
        next_is_system = int(
            bool(current_row.get("is_system"))
            if is_system is None and current_row
            else bool(is_system)
        )

        DbUtil.execute_sql(
            """
            INSERT INTO platform_roles (role_code, role_name, description, priority, capabilities_json, is_system)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                role_name = VALUES(role_name),
                description = VALUES(description),
                priority = VALUES(priority),
                capabilities_json = VALUES(capabilities_json),
                is_system = VALUES(is_system),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                normalized_role_code,
                normalized_role_name,
                str(description or "").strip(),
                int(priority or 0),
                json.dumps(capabilities, ensure_ascii=False),
                next_is_system
            )
        )

        selected_menu_code_set = set(selected_menu_codes)
        for menu_code in all_menu_codes:
            DbUtil.execute_sql(
                """
                INSERT INTO platform_role_menus (role_code, menu_code, can_view)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    can_view = VALUES(can_view),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    normalized_role_code,
                    menu_code,
                    1 if menu_code in selected_menu_code_set else 0
                )
            )

        cls.invalidate_bootstrap_cache()
        role_map = {item.get("roleCode"): item for item in cls.list_roles()}
        return role_map.get(normalized_role_code) or {}

    @classmethod
    def _role_menu_map(cls) -> Dict[str, List[str]]:
        cls.ensure_schema()
        rows = DbUtil.fetch_all(
            """
            SELECT role_code, menu_code
            FROM platform_role_menus
            WHERE can_view = 1
            ORDER BY role_code ASC, menu_code ASC
            """
        ) or []
        role_menu_map: Dict[str, List[str]] = {}
        for row in rows:
            role_code = str(row.get("role_code") or "").strip()
            menu_code = str(row.get("menu_code") or "").strip()
            if not role_code or not menu_code:
                continue
            role_menu_map.setdefault(role_code, []).append(menu_code)
        return role_menu_map

    @classmethod
    def get_user_record(cls, user_id: int) -> Optional[Dict[str, object]]:
        cls.ensure_schema()
        return DbUtil.fetch_one(
            """
            SELECT id, username, email, phone, nickname, avatar, role, status,
                   platform_role_code, quant_api_enabled, task_admin_enabled,
                   dashboard_layout, preferred_subsystem_code, last_login_time, created_at
            FROM users
            WHERE id = %s
            LIMIT 1
            """,
            (user_id,)
        )

    @classmethod
    def _build_user_capabilities(cls, user_id: int, record: Optional[Dict[str, object]]) -> Dict[str, object]:
        if not record:
            return {
                "roleCode": cls.DEFAULT_ROLE_CODE,
                "legacyRole": "user",
                "capabilities": [],
                "hasBoundAccount": False,
                "boundAccountCount": 0,
                "canUseQuantTrading": False,
                "canTradeLive": False,
                "canManageTasks": False,
                "dataScope": "self",
                "dashboardLayout": "workbench",
                "preferredSubsystemCode": "workspace"
            }

        role_code = cls._resolve_role_code(
            record.get("platform_role_code"),
            legacy_role=record.get("role"),
        )
        role_row = DbUtil.fetch_one(
            "SELECT capabilities_json FROM platform_roles WHERE role_code = %s LIMIT 1",
            (role_code,)
        ) or {}
        capabilities = cls._json_load(role_row.get("capabilities_json"))

        account_row = DbUtil.fetch_one(
            """
            SELECT COUNT(*) AS total_accounts
            FROM broker_accounts
            WHERE user_id = %s AND is_active = 1
            """,
            (user_id,)
        ) or {}
        bound_account_count = int(account_row.get("total_accounts") or 0)
        has_bound_account = bound_account_count > 0

        dynamic_caps = set(capabilities)
        can_manage_tasks = bool(record.get("task_admin_enabled")) or role_code == "admin"
        if can_manage_tasks:
            dynamic_caps.add("tasks.manage")

        can_trade_live = has_bound_account and ("trade.live" in dynamic_caps or role_code == "admin")
        can_use_quant = has_bound_account and bool(record.get("quant_api_enabled")) and ("quant.use" in dynamic_caps or role_code == "admin")

        return {
            "roleCode": role_code,
            "legacyRole": record.get("role") or "user",
            "capabilities": sorted(dynamic_caps),
            "hasBoundAccount": has_bound_account,
            "boundAccountCount": bound_account_count,
            "canUseQuantTrading": can_use_quant,
            "canTradeLive": can_trade_live,
            "canManageTasks": can_manage_tasks,
            "dataScope": "all" if role_code == "admin" else "self",
            "dashboardLayout": record.get("dashboard_layout") or "workbench",
            "preferredSubsystemCode": record.get("preferred_subsystem_code") or "workspace",
            "quantApiEnabled": bool(record.get("quant_api_enabled")),
            "taskAdminEnabled": bool(record.get("task_admin_enabled"))
        }

    @classmethod
    def get_user_capabilities(cls, user_id: int) -> Dict[str, object]:
        cls.ensure_schema()
        return cls._build_user_capabilities(user_id, cls.get_user_record(user_id))

    @classmethod
    def _build_user_menus(cls, access: Dict[str, object]) -> List[Dict[str, object]]:
        role_code = str(access.get("roleCode") or cls.DEFAULT_ROLE_CODE).strip() or cls.DEFAULT_ROLE_CODE
        capabilities = set(access.get("capabilities") or [])

        rows = DbUtil.fetch_all(
            """
            SELECT m.menu_code, m.title, m.route_name, m.route_path, m.menu_group, m.subsystem_code, m.icon,
                   m.sort_index, m.required_capability, rm.can_view,
                   s.title AS subsystem_title,
                   s.description AS subsystem_description,
                   s.icon AS subsystem_icon,
                   s.sort_index AS subsystem_sort_index,
                   s.landing_route_name AS subsystem_route_name,
                   s.landing_route_path AS subsystem_route_path
            FROM platform_menus m
            LEFT JOIN platform_role_menus rm
              ON rm.menu_code = m.menu_code AND rm.role_code = %s
            LEFT JOIN platform_subsystems s
              ON s.subsystem_code = m.subsystem_code AND s.enabled = 1
            WHERE m.enabled = 1
            ORDER BY COALESCE(s.sort_index, 999), m.menu_group ASC, m.sort_index ASC
            """,
            (role_code,)
        )

        menus = []
        for row in rows:
            required_capability = row.get("required_capability")
            if not bool(row.get("can_view")):
                continue
            if required_capability and required_capability not in capabilities and role_code != "admin":
                continue
            if row.get("menu_code") == "trading" and not access.get("canTradeLive"):
                continue
            if row.get("menu_code") in {"positions", "orders"} and not access.get("hasBoundAccount"):
                continue
            menus.append({
                "code": row.get("menu_code"),
                "title": row.get("title"),
                "routeName": row.get("route_name"),
                "path": row.get("route_path"),
                "group": row.get("menu_group"),
                "groupTitle": cls.GROUP_TITLES.get(row.get("menu_group"), row.get("menu_group")),
                "subsystemCode": row.get("subsystem_code") or "workspace",
                "subsystemTitle": row.get("subsystem_title") or "",
                "subsystemDescription": row.get("subsystem_description") or "",
                "subsystemIcon": row.get("subsystem_icon") or "Menu",
                "subsystemSortIndex": int(row.get("subsystem_sort_index") or 999),
                "subsystemRouteName": row.get("subsystem_route_name"),
                "subsystemRoutePath": row.get("subsystem_route_path"),
                "icon": row.get("icon") or "Menu",
                "requiredCapability": required_capability
            })
        return menus

    @classmethod
    def get_user_menus(cls, user_id: int) -> List[Dict[str, object]]:
        cls.ensure_schema()
        return cls._build_user_menus(cls.get_user_capabilities(user_id))

    @classmethod
    def get_user_subsystems(cls, user_id: int, menus: Optional[List[Dict[str, object]]] = None) -> List[Dict[str, object]]:
        cls.ensure_schema()
        visible_menus = menus if menus is not None else cls.get_user_menus(user_id)
        subsystem_rows = DbUtil.fetch_all(
            """
            SELECT subsystem_code, title, description, icon, sort_index, landing_route_name, landing_route_path
            FROM platform_subsystems
            WHERE enabled = 1
            ORDER BY sort_index ASC, subsystem_code ASC
            """
        ) or []
        menus_by_subsystem: Dict[str, List[Dict[str, object]]] = {}
        for menu in visible_menus:
            subsystem_code = str(menu.get("subsystemCode") or "workspace").strip() or "workspace"
            menus_by_subsystem.setdefault(subsystem_code, []).append(menu)

        subsystems: List[Dict[str, object]] = []
        for row in subsystem_rows:
            subsystem_code = str(row.get("subsystem_code") or "").strip()
            related_menus = menus_by_subsystem.get(subsystem_code, [])
            if not related_menus:
                continue

            preferred_route_name = row.get("landing_route_name")
            preferred_route_path = row.get("landing_route_path")
            landing_menu = next(
                (item for item in related_menus if item.get("routeName") == preferred_route_name),
                related_menus[0]
            )

            subsystems.append({
                "code": subsystem_code,
                "title": row.get("title") or subsystem_code,
                "description": row.get("description") or "",
                "icon": row.get("icon") or "Menu",
                "sortIndex": int(row.get("sort_index") or 0),
                "routeName": landing_menu.get("routeName") or preferred_route_name,
                "path": landing_menu.get("path") or preferred_route_path,
                "menuCount": len(related_menus),
                "menuGroups": sorted({str(item.get("group") or "") for item in related_menus if item.get("group")}),
                "menuTitles": [str(item.get("title") or "") for item in related_menus[:8]]
            })

        return subsystems

    @classmethod
    def _bootstrap_cache_now(cls) -> float:
        return time.monotonic()

    @classmethod
    def invalidate_bootstrap_cache(cls, user_id: Optional[int] = None) -> None:
        with cls._bootstrap_cache_lock:
            if user_id is None:
                cls._bootstrap_cache.clear()
                return
            cls._bootstrap_cache.pop(int(user_id), None)

    @classmethod
    def _get_cached_bootstrap_bundle(
        cls,
        user_id: int,
    ) -> Optional[Tuple[Dict[str, object], Dict[str, object]]]:
        now = cls._bootstrap_cache_now()
        with cls._bootstrap_cache_lock:
            entry = cls._bootstrap_cache.get(int(user_id))
            if not entry:
                return None
            if float(entry.get("expires_at") or 0) <= now:
                cls._bootstrap_cache.pop(int(user_id), None)
                return None
            return (
                copy.deepcopy(entry.get("payload") or {}),
                copy.deepcopy(entry.get("record") or {}),
            )

    @classmethod
    def _set_cached_bootstrap_bundle(
        cls,
        user_id: int,
        payload: Dict[str, object],
        record: Dict[str, object],
    ) -> None:
        ttl = max(int(cls.BOOTSTRAP_CACHE_TTL_SECONDS or 0), 0)
        if ttl <= 0:
            return
        with cls._bootstrap_cache_lock:
            cls._bootstrap_cache[int(user_id)] = {
                "payload": copy.deepcopy(payload),
                "record": copy.deepcopy(record),
                "expires_at": cls._bootstrap_cache_now() + ttl,
            }

    @classmethod
    def _build_user_bootstrap_bundle_uncached(
        cls,
        user_id: int,
    ) -> Tuple[Dict[str, object], Dict[str, object]]:
        record = cls.get_user_record(user_id) or {}
        access = cls._build_user_capabilities(user_id, record)
        menus = cls._build_user_menus(access)
        subsystems = cls.get_user_subsystems(user_id, menus=menus)
        preferred_subsystem_code = str(record.get("preferred_subsystem_code") or access.get("preferredSubsystemCode") or "workspace").strip() or "workspace"
        visible_subsystem_codes = {item.get("code") for item in subsystems}
        if preferred_subsystem_code not in visible_subsystem_codes:
            preferred_subsystem_code = subsystems[0].get("code") if subsystems else "workspace"
        home_path = menus[0].get("path") if menus else "/dashboard"

        return ({
            "user": {
                "id": int(record.get("id") or user_id),
                "username": record.get("username") or "",
                "nickname": record.get("nickname") or record.get("username") or "",
                "email": record.get("email") or "",
                "phone": record.get("phone") or "",
                "avatar": record.get("avatar"),
                "role": record.get("role") or "user",
                "roleCode": access.get("roleCode") or cls.DEFAULT_ROLE_CODE,
                "preferredSubsystemCode": preferred_subsystem_code,
                "status": record.get("status") or "active"
            },
            "access": access,
            "menus": menus,
            "subsystems": subsystems,
            "navigation": {
                "homePath": home_path,
                "preferredSubsystemCode": preferred_subsystem_code
            }
        }, record)

    @classmethod
    def build_user_bootstrap_bundle(
        cls,
        user_id: int,
        *,
        use_cache: bool = True,
    ) -> Tuple[Dict[str, object], Dict[str, object]]:
        cls.ensure_schema()
        normalized_user_id = int(user_id)
        if use_cache:
            cached = cls._get_cached_bootstrap_bundle(normalized_user_id)
            if cached is not None:
                return cached
        payload, record = cls._build_user_bootstrap_bundle_uncached(normalized_user_id)
        if use_cache and record:
            cls._set_cached_bootstrap_bundle(normalized_user_id, payload, record)
        return payload, record

    @classmethod
    def build_user_bootstrap(cls, user_id: int) -> Dict[str, object]:
        payload, _ = cls.build_user_bootstrap_bundle(user_id)
        return payload

    @classmethod
    def update_user_access(
        cls,
        user_id: int,
        platform_role_code: Optional[str] = None,
        quant_api_enabled: Optional[bool] = None,
        task_admin_enabled: Optional[bool] = None,
        preferred_subsystem_code: Optional[str] = None
    ) -> None:
        cls.ensure_schema()
        updates = []
        params: List[object] = []

        if platform_role_code is not None:
            updates.append("platform_role_code = %s")
            params.append(cls._resolve_role_code(platform_role_code))
        if quant_api_enabled is not None:
            updates.append("quant_api_enabled = %s")
            params.append(1 if quant_api_enabled else 0)
        if task_admin_enabled is not None:
            updates.append("task_admin_enabled = %s")
            params.append(1 if task_admin_enabled else 0)
        if preferred_subsystem_code is not None:
            updates.append("preferred_subsystem_code = %s")
            params.append(str(preferred_subsystem_code).strip() or "workspace")

        if not updates:
            return

        params.append(user_id)
        DbUtil.execute_sql(
            f"UPDATE users SET {', '.join(updates)} WHERE id = %s",
            tuple(params)
        )
        cls.invalidate_bootstrap_cache(user_id)

    @staticmethod
    def _json_load(raw_value) -> List[str]:
        if isinstance(raw_value, list):
            return raw_value
        if not raw_value:
            return []
        try:
            parsed = json.loads(raw_value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    @classmethod
    def _resolve_role_code(cls, role_code: object, legacy_role: object = None) -> str:
        raw_role_code = str(role_code or "").strip().lower()
        raw_legacy_role = str(legacy_role or "").strip().lower()

        if raw_role_code == "admin" or raw_legacy_role == "admin":
            return "admin"
        if raw_role_code in cls.OBSOLETE_ROLE_CODES:
            return cls.DEFAULT_ROLE_CODE
        return raw_role_code or cls.DEFAULT_ROLE_CODE
