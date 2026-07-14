from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any

from utils.DbUtil import DbUtil


class SymbolContentCacheService:
    TABLE_NAME = "symbol_content_cache"
    TTL_MINUTES = {
        "announcements": 240,
        "news": 60,
        "topics": 30,
    }

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(32) NOT NULL,
                market VARCHAR(10) NOT NULL,
                content_type VARCHAR(24) NOT NULL,
                source_name VARCHAR(64) NOT NULL,
                source_item_id VARCHAR(128) DEFAULT NULL,
                title VARCHAR(255) NOT NULL,
                summary TEXT,
                source_link VARCHAR(500) DEFAULT NULL,
                published_at DATETIME DEFAULT NULL,
                fetched_at DATETIME NOT NULL,
                expires_at DATETIME DEFAULT NULL,
                content_hash VARCHAR(64) DEFAULT NULL,
                payload_json JSON DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_symbol_content (symbol, content_type, source_name, source_item_id),
                INDEX idx_symbol_type_time (symbol, content_type, published_at),
                INDEX idx_expires_at (expires_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def upsert_items(
        cls,
        *,
        symbol: str,
        market: str,
        content_type: str,
        items: Iterable[dict[str, Any]],
        source_name: str,
        fetched_at: datetime | None = None,
    ) -> int:
        cls.ensure_schema()
        normalized_symbol = str(symbol or "").strip().upper()
        normalized_market = str(market or cls._detect_market(normalized_symbol)).strip().upper()
        normalized_type = cls._normalize_content_type(content_type)
        safe_fetched_at = fetched_at or datetime.now()
        expires_at = safe_fetched_at + timedelta(minutes=cls.TTL_MINUTES.get(normalized_type, 60))
        saved = 0

        for raw in items or []:
            normalized = cls._normalize_item(
                symbol=normalized_symbol,
                market=normalized_market,
                content_type=normalized_type,
                item=raw,
                source_name=source_name,
                fetched_at=safe_fetched_at,
                expires_at=expires_at,
            )
            if not normalized:
                continue
            DbUtil.execute_sql(
                f"""
                INSERT INTO {cls.TABLE_NAME} (
                    symbol, market, content_type, source_name, source_item_id, title,
                    summary, source_link, published_at, fetched_at, expires_at, content_hash, payload_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    title = VALUES(title),
                    summary = VALUES(summary),
                    source_link = VALUES(source_link),
                    published_at = VALUES(published_at),
                    fetched_at = VALUES(fetched_at),
                    expires_at = VALUES(expires_at),
                    content_hash = VALUES(content_hash),
                    payload_json = VALUES(payload_json),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    normalized["symbol"],
                    normalized["market"],
                    normalized["contentType"],
                    normalized["sourceName"],
                    normalized["sourceItemId"],
                    normalized["title"],
                    normalized["summary"],
                    normalized["sourceLink"],
                    normalized["publishedAt"],
                    normalized["fetchedAt"],
                    normalized["expiresAt"],
                    normalized["contentHash"],
                    json.dumps(normalized["payload"], ensure_ascii=False),
                ),
            )
            saved += 1
        return saved

    @classmethod
    def get_cached(
        cls,
        *,
        symbol: str,
        content_type: str,
        limit: int = 20,
        use_primary: bool = False,
        include_expired: bool = False,
    ) -> list[dict[str, Any]]:
        cls.ensure_schema()
        fetch_all = DbUtil.fetch_all_primary if use_primary else DbUtil.fetch_all
        conditions = ["symbol = %s", "content_type = %s"]
        params: list[Any] = [str(symbol or "").strip().upper(), cls._normalize_content_type(content_type)]
        if not include_expired:
            conditions.append("(expires_at IS NULL OR expires_at >= NOW())")
        rows = (
            fetch_all(
                f"""
            SELECT *
            FROM {cls.TABLE_NAME}
            WHERE {' AND '.join(conditions)}
            ORDER BY COALESCE(published_at, fetched_at) DESC, id DESC
            LIMIT %s
            """,
                tuple(params + [max(1, min(int(limit or 20), 100))]),
            )
            or []
        )
        return [cls._normalize_row(row) for row in rows]

    @classmethod
    def _normalize_item(
        cls,
        *,
        symbol: str,
        market: str,
        content_type: str,
        item: dict[str, Any],
        source_name: str,
        fetched_at: datetime,
        expires_at: datetime,
    ) -> dict[str, Any] | None:
        title = str(item.get("title") or item.get("file_name") or item.get("name") or "").strip()
        if not title:
            return None
        summary = str(item.get("description") or item.get("summary") or item.get("content") or title).strip()
        source_link = item.get("url") or item.get("link") or (item.get("file_urls") or [None])[0] or None
        published_at = cls._parse_datetime(
            item.get("published_at")
            or item.get("publish_time")
            or item.get("publishedAt")
            or item.get("time")
            or item.get("created_at")
        )
        source_item_id = str(
            item.get("id")
            or item.get("item_id")
            or source_link
            or cls._stable_hash(f"{symbol}|{content_type}|{title}|{published_at}")
        )[:128]

        payload = {
            **item,
            "id": item.get("id") or source_item_id,
            "title": title,
            "description": summary,
            "summary": summary,
            "url": source_link,
            "published_at": published_at.strftime("%Y-%m-%d %H:%M:%S") if published_at else None,
            "symbol": symbol,
            "market": market,
            "content_type": content_type,
        }
        return {
            "symbol": symbol,
            "market": market,
            "contentType": content_type,
            "sourceName": source_name,
            "sourceItemId": source_item_id,
            "title": title[:255],
            "summary": summary,
            "sourceLink": source_link,
            "publishedAt": published_at,
            "fetchedAt": fetched_at,
            "expiresAt": expires_at,
            "contentHash": cls._stable_hash(f"{title}|{summary}|{source_link}|{published_at}"),
            "payload": payload,
        }

    @classmethod
    def _normalize_row(cls, row: dict[str, Any]) -> dict[str, Any]:
        payload = row.get("payload_json")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = {}
        elif not isinstance(payload, dict):
            payload = {}

        published_at = row.get("published_at")
        fetched_at = row.get("fetched_at")
        expires_at = row.get("expires_at")
        payload.setdefault("id", row.get("source_item_id") or row.get("id"))
        payload.setdefault("title", row.get("title") or "")
        payload.setdefault("description", row.get("summary") or "")
        payload.setdefault("summary", row.get("summary") or "")
        payload.setdefault("url", row.get("source_link"))
        payload.setdefault("published_at", published_at.strftime("%Y-%m-%d %H:%M:%S") if published_at else None)
        payload.setdefault("symbol", row.get("symbol") or "")
        payload.setdefault("market", row.get("market") or "")
        payload.setdefault("content_type", row.get("content_type") or "")
        payload.setdefault("source_name", row.get("source_name") or "")
        payload.setdefault("cache_fetched_at", fetched_at.strftime("%Y-%m-%d %H:%M:%S") if fetched_at else None)
        payload.setdefault("cache_expires_at", expires_at.strftime("%Y-%m-%d %H:%M:%S") if expires_at else None)
        payload.setdefault("data_source", "content-cache")
        return payload

    @staticmethod
    def _normalize_content_type(content_type: str) -> str:
        normalized = str(content_type or "").strip().lower()
        if normalized in {"announcement", "announcements", "filings"}:
            return "announcements"
        if normalized in {"topic", "topics"}:
            return "topics"
        return "news"

    @staticmethod
    def _detect_market(symbol: str) -> str:
        if symbol.endswith(".HK"):
            return "HK"
        if symbol.endswith(".SH") or symbol.endswith(".SZ") or symbol.endswith(".BJ"):
            return "CN"
        return "US"

    @staticmethod
    def _stable_hash(value: str) -> str:
        return hashlib.sha256(str(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        text = str(value or "").strip()
        if not text:
            return None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d"):
            try:
                return datetime.strptime(text[:19], fmt)
            except ValueError:
                continue
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None
