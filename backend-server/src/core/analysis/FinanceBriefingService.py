from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Dict, List
from urllib.parse import quote_plus
from xml.etree import ElementTree

import requests
from core.analysis.DailyMarketScanService import DailyMarketScanService
from core.analysis.MarketInsightService import MarketInsightService
from core.analysis.RecommendationService import RecommendationService
from utils.DbUtil import DbUtil


class FinanceBriefingService:
    TABLE_NAME = "finance_briefings"
    SOURCE_LINK_MAX_LENGTH = 2048
    MARKET_LABELS = {"US": "美股", "CN": "A股", "HK": "港股"}
    EXTERNAL_NEWS_QUERIES = {
        "US": "US stock market OR Nasdaq OR S&P 500 OR Federal Reserve",
        "CN": "A-share market OR China stocks OR CSI 300 OR Shanghai Composite",
        "HK": "Hong Kong stocks OR Hang Seng OR China Hong Kong market"
    }

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                market VARCHAR(10) NOT NULL,
                briefing_type VARCHAR(32) DEFAULT 'internal',
                headline VARCHAR(200) NOT NULL,
                summary TEXT,
                source_name VARCHAR(80) DEFAULT 'system',
                source_link VARCHAR(2048) DEFAULT NULL,
                payload_json JSON DEFAULT NULL,
                generated_at DATETIME NOT NULL,
                expires_at DATETIME DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_market_generated (market, generated_at),
                INDEX idx_expires_at (expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )
        cls._ensure_source_link_capacity()

    @classmethod
    def _ensure_source_link_capacity(cls) -> None:
        try:
            column = DbUtil.fetch_one(f"SHOW COLUMNS FROM {cls.TABLE_NAME} LIKE 'source_link'")
            column_type = str((column or {}).get("Type") or "").lower()
            if "varchar" in column_type:
                raw_length = column_type.split("varchar(", 1)[1].split(")", 1)[0]
                if int(raw_length) >= cls.SOURCE_LINK_MAX_LENGTH:
                    return
            DbUtil.execute_sql(
                f"ALTER TABLE {cls.TABLE_NAME} MODIFY COLUMN source_link VARCHAR({cls.SOURCE_LINK_MAX_LENGTH}) DEFAULT NULL"
            )
        except Exception:
            # 表存在即可服务页面；字段扩容失败时写入侧仍会裁剪到兼容长度。
            pass

    @classmethod
    def refresh_all_markets(cls, user_id: int = 1) -> Dict[str, object]:
        cls.ensure_schema()
        insights = {item["market"]: item for item in MarketInsightService.get_latest_snapshots(user_id=user_id)}
        market_scans = {item["market"]: item for item in DailyMarketScanService.get_latest_scans()}
        recommendation = RecommendationService.get_latest(profile="growth", user_id=user_id) or {}

        generated_items = []
        for market in ["US", "CN", "HK"]:
            market_items = cls._build_market_items(
                market=market,
                insight=insights.get(market) or {},
                market_scan=market_scans.get(market) or {},
                recommendation=recommendation
            )
            generated_items.extend(market_items)
            generated_items.extend(cls._fetch_external_news_items(market))

        cls._prune_old()
        return {
            "generatedAt": cls._db_now().strftime("%Y-%m-%d %H:%M:%S"),
            "items": generated_items
        }

    @classmethod
    def get_latest(cls, limit: int = 18, market: str | None = None) -> List[Dict[str, object]]:
        cls.ensure_schema()
        conditions = ["(expires_at IS NULL OR expires_at >= %s)"]
        params: List[object] = []
        params.append(cls._db_now())
        if market:
            conditions.append("market = %s")
            params.append(str(market).upper())
        params.append(int(limit))
        rows = DbUtil.fetch_all(
            f"""
            SELECT id, market, briefing_type, headline, summary, source_name, source_link, payload_json, generated_at, expires_at
            FROM {cls.TABLE_NAME}
            WHERE {' AND '.join(conditions)}
            ORDER BY generated_at DESC, id DESC
            LIMIT %s
            """,
            tuple(params)
        ) or []
        return [cls._normalize_row(row) for row in rows]

    @classmethod
    def _build_market_items(
        cls,
        market: str,
        insight: Dict[str, object],
        market_scan: Dict[str, object],
        recommendation: Dict[str, object]
    ) -> List[Dict[str, object]]:
        label = cls.MARKET_LABELS.get(market, market)
        generated_at = cls._db_now()
        expires_at = generated_at + timedelta(minutes=30)

        items = []
        market_payload = {
            "headline": insight.get("headline") or f"{label}市场脉冲",
            "summary": insight.get("summary") or f"{label}暂无新的市场动态。",
            "briefingType": "market-insight",
            "sourceName": "market-insight",
            "payload": {
                "marketScore": insight.get("marketScore"),
                "regime": insight.get("regime"),
                "benchmarks": insight.get("benchmarks", [])
            }
        }
        items.append(cls._save_item(market, market_payload, generated_at, expires_at))

        if market_scan:
            scan_payload = {
                "headline": market_scan.get("headline") or f"{label}技术扫描",
                "summary": market_scan.get("summary") or "",
                "briefingType": "market-ai-scan",
                "sourceName": "daily-market-scan",
                "payload": {
                    "technicalScore": market_scan.get("technicalScore"),
                    "breadthRatio": market_scan.get("breadthRatio"),
                    "benchmarks": market_scan.get("benchmarks", [])
                }
            }
            items.append(cls._save_item(market, scan_payload, generated_at, expires_at))

        recommendation_items = recommendation.get("items") or []
        candidate = next((item for item in recommendation_items if item.get("market") == market), None)
        if candidate:
            recommendation_payload = {
                "headline": f"{label}推荐关注 {candidate.get('symbol')}",
                "summary": candidate.get("thesis") or candidate.get("name") or candidate.get("symbol"),
                "briefingType": "recommendation",
                "sourceName": "recommendation-service",
                "payload": {
                    "symbol": candidate.get("symbol"),
                    "name": candidate.get("name"),
                    "aiScore": candidate.get("ai_score"),
                    "confidence": candidate.get("confidence")
                }
            }
            items.append(cls._save_item(market, recommendation_payload, generated_at, expires_at))

        return items

    @classmethod
    def _fetch_external_news_items(cls, market: str) -> List[Dict[str, object]]:
        query = cls.EXTERNAL_NEWS_QUERIES.get(market)
        if not query:
            return []

        try:
            url = (
                "https://news.google.com/rss/search"
                f"?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
            )
            session = requests.Session()
            session.trust_env = False
            response = session.get(
                url,
                timeout=12,
                headers={"User-Agent": "Mozilla/5.0 LongbridgeTrade/1.0"}
            )
            response.raise_for_status()
            root = ElementTree.fromstring(response.text)
        except Exception:
            return []

        generated_items: List[Dict[str, object]] = []
        for item in root.findall(".//channel/item")[:3]:
            headline = (item.findtext("title") or "").strip()
            summary = cls._strip_html((item.findtext("description") or "").strip())
            source_link = (item.findtext("link") or "").strip() or None
            if not headline:
                continue
            if cls._recent_duplicate(market, headline):
                continue

            generated_at = cls._db_now()
            expires_at = generated_at + timedelta(minutes=90)
            generated_items.append(
                cls._save_item(
                    market,
                    {
                        "headline": headline[:190],
                        "summary": summary[:800] or f"{cls.MARKET_LABELS.get(market, market)}市场外部资讯更新",
                        "briefingType": "market-news",
                        "sourceName": "Google News RSS",
                        "sourceLink": source_link,
                        "payload": {
                            "kind": "external-news",
                            "source": "google-news-rss"
                        }
                    },
                    generated_at,
                    expires_at
                )
            )
        return generated_items

    @classmethod
    def _save_item(
        cls,
        market: str,
        payload: Dict[str, object],
        generated_at: datetime,
        expires_at: datetime
    ) -> Dict[str, object]:
        source_link = cls._truncate_text(payload.get("sourceLink"), cls.SOURCE_LINK_MAX_LENGTH)
        DbUtil.execute_sql(
            f"""
            INSERT INTO {cls.TABLE_NAME} (
                market, briefing_type, headline, summary, source_name, source_link, payload_json, generated_at, expires_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                market,
                payload.get("briefingType") or "internal",
                payload.get("headline") or "",
                payload.get("summary") or "",
                payload.get("sourceName") or "system",
                source_link,
                json.dumps(payload.get("payload") or {}, ensure_ascii=False),
                generated_at,
                expires_at
            )
        )
        return {
            "market": market,
            "briefingType": payload.get("briefingType") or "internal",
            "headline": payload.get("headline") or "",
            "summary": payload.get("summary") or "",
            "sourceName": payload.get("sourceName") or "system",
            "sourceLink": source_link,
            "payload": payload.get("payload") or {},
            "generatedAt": generated_at.strftime("%Y-%m-%d %H:%M:%S"),
            "expiresAt": expires_at.strftime("%Y-%m-%d %H:%M:%S")
        }

    @classmethod
    def _prune_old(cls) -> None:
        DbUtil.execute_sql(
            f"DELETE FROM {cls.TABLE_NAME} WHERE generated_at < %s",
            (cls._db_now() - timedelta(days=5),)
        )

    @classmethod
    def _recent_duplicate(cls, market: str, headline: str) -> bool:
        row = DbUtil.fetch_one(
            f"""
            SELECT id
            FROM {cls.TABLE_NAME}
            WHERE market = %s AND headline = %s
              AND generated_at >= DATE_SUB(NOW(), INTERVAL 6 HOUR)
            LIMIT 1
            """,
            (market, headline[:190])
        )
        return bool(row)

    @staticmethod
    def _strip_html(text: str) -> str:
        import re
        return re.sub(r"<[^>]+>", "", text or "").strip()

    @staticmethod
    def _db_now() -> datetime:
        row = DbUtil.fetch_one("SELECT NOW() AS current_db_time") or {}
        value = row.get("current_db_time")
        return value if isinstance(value, datetime) else datetime.now()

    @staticmethod
    def _truncate_text(value: object, max_length: int) -> str | None:
        if value is None:
            return None
        text = str(value)
        if len(text) <= max_length:
            return text
        return text[:max_length]

    @classmethod
    def _normalize_row(cls, row: Dict[str, object]) -> Dict[str, object]:
        return {
            "id": int(row.get("id") or 0),
            "market": row.get("market") or "",
            "briefingType": row.get("briefing_type") or "internal",
            "headline": row.get("headline") or "",
            "summary": row.get("summary") or "",
            "sourceName": row.get("source_name") or "system",
            "sourceLink": row.get("source_link"),
            "payload": cls._json_load(row.get("payload_json")),
            "generatedAt": row.get("generated_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("generated_at") else None,
            "expiresAt": row.get("expires_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("expires_at") else None
        }

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
