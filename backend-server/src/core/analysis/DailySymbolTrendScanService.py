from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from core.analysis.HistoricalMarketDataService import HistoricalMarketDataService
from core.analysis.IndicatorSnapshotService import IndicatorSnapshotService
from core.analysis.ai_analyst import AIAnalyst
from utils.DbUtil import DbUtil


class DailySymbolTrendScanService:
    TABLE_NAME = "symbol_ai_trend_scans"
    TASK_KEY = "daily_symbol_trend_ai_scan"

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(32) NOT NULL,
                market VARCHAR(10) NOT NULL,
                analysis_date DATE NOT NULL,
                data_trade_date DATE DEFAULT NULL,
                trend_direction VARCHAR(16) DEFAULT 'sideways',
                trend_strength DECIMAL(10, 4) DEFAULT 0,
                risk_level VARCHAR(16) DEFAULT 'medium',
                technical_score DECIMAL(10, 4) DEFAULT 0,
                headline VARCHAR(180) DEFAULT NULL,
                summary VARCHAR(255) DEFAULT NULL,
                analysis_text TEXT,
                model_id VARCHAR(120) DEFAULT NULL,
                model_alias VARCHAR(80) DEFAULT NULL,
                indicators_json JSON DEFAULT NULL,
                meta_json JSON DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_symbol_analysis_date (symbol, analysis_date),
                INDEX idx_analysis_date_market (analysis_date, market),
                INDEX idx_symbol_updated (symbol, updated_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def run_batch(
        cls,
        analysis_date=None,
        batch_size: int = 24,
        cursor: int = 0,
        user_id: int = 1
    ) -> Dict[str, object]:
        cls.ensure_schema()
        target_date = cls._coerce_date(analysis_date) or (date.today() - timedelta(days=1))
        safe_cursor = max(0, int(cursor or 0))
        safe_batch_size = max(1, min(int(batch_size or 24), 60))

        universe = IndicatorSnapshotService._collect_universe_symbols(limit=safe_batch_size, offset=safe_cursor)
        if not universe:
            return {
                "analysisDate": target_date.strftime("%Y-%m-%d"),
                "processed": 0,
                "saved": 0,
                "nextCursor": 0,
                "completed": True,
                "symbols": [],
                "fallbackCount": 0
            }

        metrics_batch = [
            cls._build_symbol_metrics(
                symbol=item.get("symbol"),
                market=item.get("market"),
                analysis_date=target_date
            )
            for item in universe
            if item.get("symbol")
        ]

        ai_ready_batch = [item for item in metrics_batch if item.get("historyCount", 0) >= 40 and item.get("dataTradeDate")]
        ai_result_map = cls._request_batch_analysis(ai_ready_batch, target_date, user_id=user_id) if ai_ready_batch else {}
        model_plan = AIAnalyst.get_task_model_plan(user_id=user_id).get("trendBatch") or AIAnalyst.get_task_model_plan(user_id=user_id).get("pulse") or {}

        saved = 0
        fallback_count = 0
        results = []
        for metric in metrics_batch:
            ai_payload = ai_result_map.get(metric["symbol"])
            source = "ai" if ai_payload else "rule"
            if source == "rule":
                fallback_count += 1
            result = cls._compose_result(
                metric=metric,
                analysis_date=target_date,
                ai_payload=ai_payload,
                model_plan=model_plan,
                source=source
            )
            cls._save_result(result)
            results.append(result)
            saved += 1

        next_cursor = safe_cursor + len(universe)
        completed = len(universe) < safe_batch_size
        return {
            "analysisDate": target_date.strftime("%Y-%m-%d"),
            "processed": len(metrics_batch),
            "saved": saved,
            "nextCursor": 0 if completed else next_cursor,
            "completed": completed,
            "symbols": [item["symbol"] for item in metrics_batch],
            "fallbackCount": fallback_count,
            "aiCount": max(0, saved - fallback_count),
            "results": [
                {
                    "symbol": item["symbol"],
                    "trendDirection": item["trendDirection"],
                    "riskLevel": item["riskLevel"],
                    "technicalScore": item["technicalScore"],
                    "summary": item["summary"],
                    "source": item.get("meta", {}).get("source", "rule")
                }
                for item in results[:10]
            ]
        }

    @classmethod
    def get_latest_for_symbol(cls, symbol: str) -> Optional[Dict[str, object]]:
        cls.ensure_schema()
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        row = DbUtil.fetch_one(
            f"""
            SELECT *
            FROM {cls.TABLE_NAME}
            WHERE symbol = %s
            ORDER BY analysis_date DESC, id DESC
            LIMIT 1
            """,
            (normalized_symbol,)
        )
        if not row:
            return None
        return cls._normalize_row(row)

    @classmethod
    def get_latest_batch(
        cls,
        symbols: Optional[List[str]] = None,
        market: Optional[str] = None,
        limit: int = 24
    ) -> List[Dict[str, object]]:
        cls.ensure_schema()
        conditions = []
        params: List[object] = []

        normalized_symbols: List[str] = []
        for raw_symbol in symbols or []:
            normalized_symbol = HistoricalMarketDataService.normalize_symbol(raw_symbol)
            if normalized_symbol and normalized_symbol not in normalized_symbols:
                normalized_symbols.append(normalized_symbol)

        if normalized_symbols:
            placeholders = ", ".join(["%s"] * len(normalized_symbols))
            conditions.append(f"symbol IN ({placeholders})")
            params.extend(normalized_symbols)

        safe_market = str(market or "").strip().upper()
        if safe_market:
            conditions.append("market = %s")
            params.append(safe_market)

        where_clause = " AND ".join(conditions) if conditions else "1=1"
        fetch_limit = max(limit * 6, len(normalized_symbols) * 4 if normalized_symbols else 0, 60)

        rows = DbUtil.fetch_all(
            f"""
            SELECT *
            FROM {cls.TABLE_NAME}
            WHERE {where_clause}
            ORDER BY analysis_date DESC, updated_at DESC, id DESC
            LIMIT %s
            """,
            tuple(params + [fetch_limit])
        ) or []

        results: List[Dict[str, object]] = []
        seen_symbols = set()
        for row in rows:
            symbol = str(row.get("symbol") or "").upper()
            if not symbol or symbol in seen_symbols:
                continue
            seen_symbols.add(symbol)
            results.append(cls._normalize_row(row))
            if len(results) >= max(1, int(limit or 24)):
                break

        return results

    @classmethod
    def _build_symbol_metrics(cls, symbol: str, market: Optional[str], analysis_date: date) -> Dict[str, object]:
        normalized_symbol = HistoricalMarketDataService.normalize_symbol(symbol)
        safe_market = str(market or HistoricalMarketDataService.detect_market(normalized_symbol)).upper()
        series = HistoricalMarketDataService.get_daily_series_until(normalized_symbol, end_date=analysis_date, limit=260)
        closes = [float(item.get("close") or 0) for item in series]
        highs = [float(item.get("high") or 0) for item in series]
        lows = [float(item.get("low") or 0) for item in series]
        volumes = [float(item.get("volume") or 0) for item in series]

        latest = series[-1] if series else {}
        previous = series[-2] if len(series) >= 2 else {}
        latest_close = float(latest.get("close") or 0)
        previous_close = float(previous.get("close") or 0)
        history_count = len(series)

        ma5 = cls._moving_average(closes, 5)
        ma20 = cls._moving_average(closes, 20)
        ma60 = cls._moving_average(closes, 60)
        ma120 = cls._moving_average(closes, 120)
        return20 = cls._period_return(closes, 20)
        return60 = cls._period_return(closes, 60)
        return120 = cls._period_return(closes, 120)
        rsi14 = cls._rsi(closes, 14)
        volatility20 = cls._volatility(closes, 20)
        avg_volume20 = cls._moving_average(volumes[:-1], 20) if len(volumes) > 1 else 0.0
        volume_ratio20 = round((volumes[-1] / avg_volume20), 2) if volumes and avg_volume20 else 0.0
        high20 = max(highs[-20:]) if highs else 0.0
        low20 = min(lows[-20:]) if lows else 0.0
        distance_high20 = round(((latest_close - high20) / high20) * 100, 2) if latest_close and high20 else 0.0
        distance_low20 = round(((latest_close - low20) / low20) * 100, 2) if latest_close and low20 else 0.0
        day_change_percent = round(((latest_close - previous_close) / previous_close) * 100, 2) if latest_close and previous_close else 0.0

        trend_hint = cls._trend_hint(latest_close, ma20, ma60, return20, return60, rsi14)
        trend_direction = cls._direction_from_hint(trend_hint)
        technical_score = cls._technical_score(latest_close, ma20, ma60, return20, return60, rsi14, volatility20)
        risk_level = cls._risk_level(volatility20, return20, distance_high20)
        trend_strength = cls._trend_strength(latest_close, ma20, ma60, return20, return60, rsi14)

        return {
            "symbol": normalized_symbol,
            "market": safe_market,
            "analysisDate": analysis_date.strftime("%Y-%m-%d"),
            "dataTradeDate": latest.get("date"),
            "historyCount": history_count,
            "latestClose": round(latest_close, 4),
            "dayChangePercent": day_change_percent,
            "ma5": ma5,
            "ma20": ma20,
            "ma60": ma60,
            "ma120": ma120,
            "return20": return20,
            "return60": return60,
            "return120": return120,
            "rsi14": rsi14,
            "volatility20": volatility20,
            "avgVolume20": round(avg_volume20, 2),
            "volumeRatio20": volume_ratio20,
            "distanceHigh20": distance_high20,
            "distanceLow20": distance_low20,
            "trendHint": trend_hint,
            "trendDirection": trend_direction,
            "technicalScore": technical_score,
            "riskLevel": risk_level,
            "trendStrength": trend_strength
        }

    @classmethod
    def _request_batch_analysis(
        cls,
        metrics_batch: List[Dict[str, object]],
        analysis_date: date,
        user_id: int = 1
    ) -> Dict[str, Dict[str, object]]:
        if not metrics_batch:
            return {}

        prompt = cls._build_batch_prompt(metrics_batch, analysis_date)
        model_plan = AIAnalyst.get_task_model_plan(user_id=user_id).get("trendBatch") or {}
        requested_model = model_plan.get("id")
        text = AIAnalyst.get_decision(requested_model, prompt, task="trend_batch", user_id=user_id)
        if not text or str(text).strip().startswith("ERROR"):
            return {}

        parsed_items = cls._parse_ai_items(text)
        normalized: Dict[str, Dict[str, object]] = {}
        for item in parsed_items:
            symbol = HistoricalMarketDataService.normalize_symbol(item.get("symbol") or "")
            if not symbol:
                continue
            normalized[symbol] = item
        return normalized

    @classmethod
    def _build_batch_prompt(cls, metrics_batch: List[Dict[str, object]], analysis_date: date) -> str:
        lines = []
        for item in metrics_batch:
            lines.append(
                f"{item['symbol']}|market={item['market']}|tradeDate={item.get('dataTradeDate') or analysis_date.strftime('%Y-%m-%d')}|"
                f"close={float(item.get('latestClose') or 0):.4f}|chg1d={float(item.get('dayChangePercent') or 0):+.2f}%|"
                f"ret20={float(item.get('return20') or 0):+.2f}%|ret60={float(item.get('return60') or 0):+.2f}%|"
                f"ret120={float(item.get('return120') or 0):+.2f}%|ma20={float(item.get('ma20') or 0):.4f}|"
                f"ma60={float(item.get('ma60') or 0):.4f}|rsi14={float(item.get('rsi14') or 0):.2f}|"
                f"vol20={float(item.get('volatility20') or 0):.2f}|volRatio20={float(item.get('volumeRatio20') or 0):.2f}|"
                f"distHigh20={float(item.get('distanceHigh20') or 0):+.2f}%|distLow20={float(item.get('distanceLow20') or 0):+.2f}%|"
                f"hint={item.get('trendHint') or '震荡整理'}|score={float(item.get('technicalScore') or 0):.2f}|"
                f"risk={item.get('riskLevel') or 'medium'}"
            )

        return f"""你是量化趋势扫描员，请根据截至 {analysis_date.strftime('%Y-%m-%d')} 的日线技术摘要，为每个标的给出趋势判断。

要求：
1. 只输出 JSON 数组，不要 Markdown，不要解释。
2. 每个对象必须包含：symbol, trendDirection, trendStrength, riskLevel, technicalScore, headline, summary。
3. trendDirection 只能是 up / down / sideways。
4. riskLevel 只能是 low / medium / high。
5. trendStrength 和 technicalScore 使用 0-100 数字。
6. headline 不超过 18 个汉字，summary 不超过 60 个汉字。

技术摘要：
{chr(10).join(lines)}
"""

    @classmethod
    def _compose_result(
        cls,
        metric: Dict[str, object],
        analysis_date: date,
        ai_payload: Optional[Dict[str, object]],
        model_plan: Dict[str, object],
        source: str = "rule"
    ) -> Dict[str, object]:
        fallback = cls._fallback_payload(metric)
        merged = {**fallback, **(ai_payload or {})}
        trend_direction = cls._normalize_direction(merged.get("trendDirection") or merged.get("trend_direction") or metric.get("trendDirection"))
        risk_level = cls._normalize_risk_level(merged.get("riskLevel") or merged.get("risk_level") or metric.get("riskLevel"))
        technical_score = cls._clamp_number(merged.get("technicalScore"), fallback["technicalScore"])
        trend_strength = cls._clamp_number(merged.get("trendStrength"), fallback["trendStrength"])
        headline = str(fallback["headline"]).strip()[:180]
        summary = str(fallback["summary"]).strip()[:255]

        return {
            "symbol": metric["symbol"],
            "market": metric["market"],
            "analysisDate": analysis_date.strftime("%Y-%m-%d"),
            "dataTradeDate": metric.get("dataTradeDate"),
            "trendDirection": trend_direction,
            "trendStrength": trend_strength,
            "riskLevel": risk_level,
            "technicalScore": technical_score,
            "headline": headline,
            "summary": summary,
            "analysisText": json.dumps(
                {
                    "headline": headline,
                    "summary": summary,
                    "trendDirection": trend_direction,
                    "trendStrength": trend_strength,
                    "riskLevel": risk_level,
                    "technicalScore": technical_score
                },
                ensure_ascii=False
            ),
            "modelId": model_plan.get("id"),
            "modelAlias": model_plan.get("alias"),
            "indicators": {
                "latestClose": metric.get("latestClose"),
                "dayChangePercent": metric.get("dayChangePercent"),
                "ma5": metric.get("ma5"),
                "ma20": metric.get("ma20"),
                "ma60": metric.get("ma60"),
                "ma120": metric.get("ma120"),
                "return20": metric.get("return20"),
                "return60": metric.get("return60"),
                "return120": metric.get("return120"),
                "rsi14": metric.get("rsi14"),
                "volatility20": metric.get("volatility20"),
                "volumeRatio20": metric.get("volumeRatio20"),
                "distanceHigh20": metric.get("distanceHigh20"),
                "distanceLow20": metric.get("distanceLow20"),
                "trendHint": metric.get("trendHint")
            },
            "meta": {
                "source": source,
                "historyCount": int(metric.get("historyCount") or 0),
                "providerRoute": model_plan.get("providerRoute"),
                "analysisDate": analysis_date.strftime("%Y-%m-%d"),
                "aiPayload": ai_payload or {}
            }
        }

    @classmethod
    def _save_result(cls, result: Dict[str, object]) -> None:
        DbUtil.execute_sql(
            f"""
            INSERT INTO {cls.TABLE_NAME} (
                symbol, market, analysis_date, data_trade_date, trend_direction, trend_strength,
                risk_level, technical_score, headline, summary, analysis_text, model_id, model_alias,
                indicators_json, meta_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                market = VALUES(market),
                data_trade_date = VALUES(data_trade_date),
                trend_direction = VALUES(trend_direction),
                trend_strength = VALUES(trend_strength),
                risk_level = VALUES(risk_level),
                technical_score = VALUES(technical_score),
                headline = VALUES(headline),
                summary = VALUES(summary),
                analysis_text = VALUES(analysis_text),
                model_id = VALUES(model_id),
                model_alias = VALUES(model_alias),
                indicators_json = VALUES(indicators_json),
                meta_json = VALUES(meta_json),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                result["symbol"],
                result["market"],
                result["analysisDate"],
                result.get("dataTradeDate"),
                result["trendDirection"],
                result["trendStrength"],
                result["riskLevel"],
                result["technicalScore"],
                result["headline"],
                result["summary"],
                result["analysisText"],
                result.get("modelId"),
                result.get("modelAlias"),
                json.dumps(result.get("indicators") or {}, ensure_ascii=False),
                json.dumps(result.get("meta") or {}, ensure_ascii=False)
            )
        )

    @classmethod
    def _normalize_row(cls, row: Dict[str, object]) -> Dict[str, object]:
        return {
            "symbol": row.get("symbol"),
            "market": row.get("market"),
            "analysisDate": row.get("analysis_date").strftime("%Y-%m-%d") if row.get("analysis_date") else None,
            "dataTradeDate": row.get("data_trade_date").strftime("%Y-%m-%d") if row.get("data_trade_date") else None,
            "trendDirection": cls._normalize_direction(row.get("trend_direction")),
            "trendStrength": float(row.get("trend_strength") or 0),
            "riskLevel": cls._normalize_risk_level(row.get("risk_level")),
            "technicalScore": float(row.get("technical_score") or 0),
            "headline": row.get("headline") or "",
            "summary": row.get("summary") or "",
            "analysisText": row.get("analysis_text") or "",
            "modelId": row.get("model_id") or "",
            "modelAlias": row.get("model_alias") or "",
            "indicators": cls._json_load(row.get("indicators_json")),
            "meta": cls._json_load(row.get("meta_json")),
            "generatedAt": row.get("updated_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("updated_at") else None
        }

    @classmethod
    def _fallback_payload(cls, metric: Dict[str, object]) -> Dict[str, object]:
        data_trade_date = metric.get("dataTradeDate") or metric.get("analysisDate")
        if not metric.get("dataTradeDate"):
            return {
                "trendDirection": "sideways",
                "trendStrength": 0.0,
                "riskLevel": "high",
                "technicalScore": 0.0,
                "headline": f"{metric['symbol']} 数据不足",
                "summary": f"截至 {metric.get('analysisDate')} 暂无足够日线数据，等待历史补数完成。"
            }

        return {
            "trendDirection": metric.get("trendDirection"),
            "trendStrength": float(metric.get("trendStrength") or 0),
            "riskLevel": metric.get("riskLevel"),
            "technicalScore": float(metric.get("technicalScore") or 0),
            "headline": f"{metric['symbol']} {metric.get('trendHint') or '趋势观察'}",
            "summary": (
                f"截至 {data_trade_date}，20日收益 {float(metric.get('return20') or 0):+.2f}%，"
                f"RSI {float(metric.get('rsi14') or 0):.1f}，趋势偏向 {metric.get('trendHint') or '震荡整理'}。"
            )[:255]
        }

    @staticmethod
    def _moving_average(values: List[float], window: int) -> float:
        if not values:
            return 0.0
        sample = values[-window:] if len(values) >= window else values
        if not sample:
            return 0.0
        return round(sum(sample) / len(sample), 4)

    @staticmethod
    def _period_return(values: List[float], periods: int) -> float:
        if len(values) <= periods:
            return 0.0
        base = float(values[-periods - 1] or 0)
        latest = float(values[-1] or 0)
        if not base:
            return 0.0
        return round(((latest - base) / base) * 100, 2)

    @staticmethod
    def _rsi(values: List[float], periods: int = 14) -> float:
        if len(values) <= periods:
            return 50.0
        changes = [values[index] - values[index - 1] for index in range(1, len(values))]
        sample = changes[-periods:]
        gains = [max(change, 0) for change in sample]
        losses = [abs(min(change, 0)) for change in sample]
        avg_gain = sum(gains) / periods
        avg_loss = sum(losses) / periods
        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return round(100 - (100 / (1 + rs)), 2)

    @staticmethod
    def _volatility(values: List[float], periods: int = 20) -> float:
        if len(values) <= periods:
            return 0.0
        returns = []
        sample = values[-periods - 1:]
        for index in range(1, len(sample)):
            base = float(sample[index - 1] or 0)
            current = float(sample[index] or 0)
            if not base:
                continue
            returns.append(((current - base) / base) * 100)
        if not returns:
            return 0.0
        mean = sum(returns) / len(returns)
        variance = sum((item - mean) ** 2 for item in returns) / len(returns)
        return round(variance ** 0.5, 2)

    @staticmethod
    def _trend_hint(
        latest_close: float,
        ma20: float,
        ma60: float,
        return20: float,
        return60: float,
        rsi14: float
    ) -> str:
        if latest_close and latest_close >= ma20 >= ma60 and return20 >= 0 and return60 >= 0 and rsi14 >= 55:
            return "多头强化"
        if latest_close and latest_close >= ma20 and ma20 >= ma60:
            return "偏多震荡"
        if latest_close and latest_close <= ma20 <= ma60 and return20 <= 0 and return60 <= 0 and rsi14 <= 45:
            return "空头压制"
        return "震荡整理"

    @staticmethod
    def _direction_from_hint(trend_hint: str) -> str:
        if trend_hint in {"多头强化", "偏多震荡"}:
            return "up"
        if trend_hint == "空头压制":
            return "down"
        return "sideways"

    @staticmethod
    def _technical_score(
        latest_close: float,
        ma20: float,
        ma60: float,
        return20: float,
        return60: float,
        rsi14: float,
        volatility20: float
    ) -> float:
        score = 50.0
        if latest_close and ma20:
            score += 8 if latest_close >= ma20 else -8
        if ma20 and ma60:
            score += 10 if ma20 >= ma60 else -10
        score += max(-12, min(12, return20 / 1.2))
        score += max(-8, min(8, return60 / 2.5))
        score += max(-10, min(10, (rsi14 - 50) * 0.55))
        score -= max(0, min(10, max(volatility20 - 3.5, 0) * 1.5))
        return round(max(0.0, min(100.0, score)), 2)

    @staticmethod
    def _risk_level(volatility20: float, return20: float, distance_high20: float) -> str:
        if volatility20 >= 4.2 or return20 <= -12 or distance_high20 <= -12:
            return "high"
        if volatility20 >= 2.6 or return20 <= -4:
            return "medium"
        return "low"

    @staticmethod
    def _trend_strength(
        latest_close: float,
        ma20: float,
        ma60: float,
        return20: float,
        return60: float,
        rsi14: float
    ) -> float:
        strength = 48.0
        if latest_close and ma20:
            strength += 8 if latest_close >= ma20 else -8
        if ma20 and ma60:
            strength += 10 if ma20 >= ma60 else -10
        strength += max(-12, min(12, return20 / 1.5))
        strength += max(-8, min(8, return60 / 3.0))
        strength += max(-10, min(10, (rsi14 - 50) * 0.5))
        return round(max(0.0, min(100.0, strength)), 2)

    @staticmethod
    def _parse_ai_items(raw_text: str) -> List[Dict[str, object]]:
        text = str(raw_text or "").strip()
        if not text:
            return []
        if text.startswith("```"):
            text = text.strip("`")
            if "\n" in text:
                text = text.split("\n", 1)[1]
        start_index = text.find("[")
        end_index = text.rfind("]")
        candidate = text[start_index:end_index + 1] if start_index >= 0 and end_index > start_index else text
        try:
            parsed = json.loads(candidate)
        except Exception:
            return []
        if isinstance(parsed, dict):
            parsed = parsed.get("items") or parsed.get("results") or []
        return [item for item in parsed if isinstance(item, dict)]

    @staticmethod
    def _normalize_direction(value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"up", "bullish", "上涨", "偏多", "多头", "多头强化"}:
            return "up"
        if normalized in {"down", "bearish", "下跌", "偏空", "空头", "空头压制"}:
            return "down"
        return "sideways"

    @staticmethod
    def _normalize_risk_level(value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized in {"high", "高", "high-risk"}:
            return "high"
        if normalized in {"low", "低", "low-risk"}:
            return "low"
        return "medium"

    @staticmethod
    def _clamp_number(value: object, fallback: float) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = float(fallback or 0)
        return round(max(0.0, min(100.0, number)), 2)

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

    @staticmethod
    def _coerce_date(value):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").date()
            except ValueError:
                return None
        return None
