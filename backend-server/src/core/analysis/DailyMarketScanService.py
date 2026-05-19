from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List

from core.analysis.IndicatorSnapshotService import IndicatorSnapshotService
from core.analysis.MarketInsightService import MarketInsightService
from core.analysis.ai_analyst import AIAnalyst
from utils.DbUtil import DbUtil


class DailyMarketScanService:
    TABLE_NAME = "market_ai_scans"

    @classmethod
    def ensure_schema(cls) -> None:
        DbUtil.execute_sql(
            f"""
            CREATE TABLE IF NOT EXISTS {cls.TABLE_NAME} (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                market VARCHAR(10) NOT NULL,
                trade_date DATE NOT NULL,
                technical_score DECIMAL(12, 4) DEFAULT 0,
                breadth_ratio DECIMAL(12, 4) DEFAULT 0,
                status VARCHAR(32) DEFAULT NULL,
                model_id VARCHAR(120) DEFAULT NULL,
                model_alias VARCHAR(80) DEFAULT NULL,
                headline VARCHAR(180) DEFAULT NULL,
                summary TEXT,
                insights_json JSON DEFAULT NULL,
                benchmarks_json JSON DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uniq_market_trade_date (market, trade_date),
                INDEX idx_market_created (market, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """
        )

    @classmethod
    def refresh_all_markets(cls, user_id: int = 1) -> Dict[str, object]:
        cls.ensure_schema()
        results = []
        for market in ["US", "CN", "HK"]:
            results.append(cls.refresh_market(market, user_id=user_id))
        return {
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "markets": results
        }

    @classmethod
    def refresh_market(cls, market: str, user_id: int = 1) -> Dict[str, object]:
        cls.ensure_schema()
        safe_market = str(market or "US").upper()
        insight = MarketInsightService.build_market_insight(safe_market, user_id=user_id)
        benchmark_indicators = []
        positive_count = 0

        for benchmark in insight.get("benchmarks", []):
            symbol = benchmark.get("symbol")
            if not symbol:
                continue
            daily_snapshot = {}
            try:
                IndicatorSnapshotService.refresh_symbol(symbol, user_id=user_id, timeframes=("daily", "weekly"))
            except Exception:
                pass
            try:
                overview = IndicatorSnapshotService.get_symbol_overview(symbol, user_id=user_id)
                daily_snapshot = (overview.get("snapshots") or {}).get("daily") or {}
            except Exception:
                daily_snapshot = {}
            signal_up = float(daily_snapshot.get("changePercent") or 0) >= 0
            if signal_up:
                positive_count += 1
            benchmark_indicators.append({
                "symbol": symbol,
                "name": benchmark.get("name") or symbol,
                "price": float(benchmark.get("price") or 0),
                "changePercent": float(benchmark.get("changePercent") or 0),
                "trendLabel": daily_snapshot.get("trendLabel") or ("上涨" if float(benchmark.get("changePercent") or 0) > 0 else "下跌" if float(benchmark.get("changePercent") or 0) < 0 else "震荡"),
                "rsi": float(daily_snapshot.get("rsi") or 50),
                "momentumScore": float(daily_snapshot.get("momentumScore") or (55 if float(benchmark.get("changePercent") or 0) > 0 else 45 if float(benchmark.get("changePercent") or 0) < 0 else 50))
            })

        breadth_ratio = (positive_count / len(benchmark_indicators) * 100) if benchmark_indicators else 0
        technical_score = cls._technical_score(benchmark_indicators)

        prompt = f"""你是市场技术总览分析师，请根据下面的真实市场数据给出简洁技术扫描。

请严格输出：
标题: ...
市场状态: ...
技术观察: ...
风险提示: ...
操作节奏: ...
一句结论: ...

市场: {safe_market}
市场情绪摘要: {insight.get('summary', '')}
市场状态: {insight.get('statusText', '')}
广度比率: {breadth_ratio:.2f}%
综合技术分: {technical_score:.2f}

基准指标:
{cls._format_benchmarks(benchmark_indicators)}
"""
        text = AIAnalyst.get_decision(None, prompt, task="scan_final", user_id=user_id)
        if not text or str(text).strip().startswith("ERROR"):
            fallback_text = cls._build_fallback_summary(
                market_label=insight.get("marketLabel", safe_market),
                status_text=insight.get("statusText", insight.get("regime", "balanced")),
                breadth_ratio=breadth_ratio,
                technical_score=technical_score,
                benchmarks=benchmark_indicators
            )
            text = fallback_text

        title = cls._extract_field(text, "标题") or f"{insight.get('marketLabel', safe_market)}技术扫描"
        status_text = cls._extract_field(text, "市场状态") or insight.get("statusText", "")
        status = cls._normalize_status(
            status_text=status_text,
            regime=insight.get("regime", "balanced"),
            technical_score=technical_score,
            breadth_ratio=breadth_ratio,
        )
        summary = cls._extract_field(text, "一句结论") or text.strip()
        insights = {
            "statusText": status_text,
            "technicalObservation": cls._extract_field(text, "技术观察"),
            "riskHint": cls._extract_field(text, "风险提示"),
            "rhythm": cls._extract_field(text, "操作节奏"),
            "fullText": text
        }

        plan = AIAnalyst.get_task_model_plan(user_id=user_id).get("final") or {}
        result = {
            "market": safe_market,
            "marketLabel": insight.get("marketLabel", safe_market),
            "tradeDate": datetime.now().strftime("%Y-%m-%d"),
            "technicalScore": round(technical_score, 2),
            "breadthRatio": round(breadth_ratio, 2),
            "status": status,
            "headline": title,
            "summary": summary,
            "insights": insights,
            "benchmarks": benchmark_indicators,
            "modelId": plan.get("id"),
            "modelAlias": plan.get("alias"),
            "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        cls._save_result(result)
        return result

    @classmethod
    def get_latest_scans(cls) -> List[Dict[str, object]]:
        cls.ensure_schema()
        rows = DbUtil.fetch_all(
            f"""
            SELECT *
            FROM {cls.TABLE_NAME}
            ORDER BY trade_date DESC, id DESC
            """
        )
        latest: Dict[str, Dict[str, object]] = {}
        for row in rows:
            market = row.get("market")
            if market in latest:
                continue
            latest[market] = {
                "market": market,
                "tradeDate": row.get("trade_date").strftime("%Y-%m-%d") if row.get("trade_date") else None,
                "technicalScore": float(row.get("technical_score") or 0),
                "breadthRatio": float(row.get("breadth_ratio") or 0),
                "status": row.get("status") or "",
                "headline": row.get("headline") or "",
                "summary": row.get("summary") or "",
                "insights": cls._json_load(row.get("insights_json")),
                "benchmarks": cls._json_load(row.get("benchmarks_json")).get("items", []),
                "modelId": row.get("model_id") or "",
                "modelAlias": row.get("model_alias") or "",
                "generatedAt": row.get("updated_at").strftime("%Y-%m-%d %H:%M:%S") if row.get("updated_at") else None
            }
            if len(latest) == 3:
                break
        return [latest[key] for key in ["US", "CN", "HK"] if key in latest]

    @classmethod
    def _save_result(cls, result: Dict[str, object]) -> None:
        status = str(result.get("status") or "").strip()
        if status not in {"偏强", "偏弱", "中性"} or len(status) > 32:
            status = cls._normalize_status(
                status_text=status,
                regime="",
                technical_score=float(result.get("technicalScore") or 0),
                breadth_ratio=float(result.get("breadthRatio") or 0),
            )
        DbUtil.execute_sql(
            f"""
            INSERT INTO {cls.TABLE_NAME} (
                market, trade_date, technical_score, breadth_ratio, status,
                model_id, model_alias, headline, summary, insights_json, benchmarks_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                technical_score = VALUES(technical_score),
                breadth_ratio = VALUES(breadth_ratio),
                status = VALUES(status),
                model_id = VALUES(model_id),
                model_alias = VALUES(model_alias),
                headline = VALUES(headline),
                summary = VALUES(summary),
                insights_json = VALUES(insights_json),
                benchmarks_json = VALUES(benchmarks_json),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                result["market"],
                result["tradeDate"],
                result["technicalScore"],
                result["breadthRatio"],
                status,
                result.get("modelId"),
                result.get("modelAlias"),
                result["headline"],
                result["summary"],
                json.dumps(result["insights"], ensure_ascii=False),
                json.dumps({"items": result["benchmarks"]}, ensure_ascii=False)
            )
        )

    @staticmethod
    def _technical_score(benchmarks: List[Dict[str, object]]) -> float:
        if not benchmarks:
            return 0.0
        total = 0.0
        for item in benchmarks:
            total += float(item.get("momentumScore") or 0)
        return total / len(benchmarks)

    @staticmethod
    def _format_benchmarks(benchmarks: List[Dict[str, object]]) -> str:
        if not benchmarks:
            return "- 暂无基准数据"
        lines = []
        for item in benchmarks:
            lines.append(
                f"- {item.get('name', item.get('symbol'))}: "
                f"{float(item.get('price') or 0):.2f} / {float(item.get('changePercent') or 0):+.2f}% / "
                f"趋势 {item.get('trendLabel', '--')} / RSI {float(item.get('rsi') or 0):.2f}"
            )
        return "\n".join(lines)

    @staticmethod
    def _extract_field(text: str, label: str) -> str:
        if not text:
            return ""
        prefix = f"{label}:"
        alt_prefix = f"{label}："
        for line in str(text).splitlines():
            clean = line.strip()
            if clean.startswith(prefix):
                return clean.split(":", 1)[1].strip()
            if clean.startswith(alt_prefix):
                return clean.split("：", 1)[1].strip()
        return ""

    @staticmethod
    def _normalize_status(
        *,
        status_text: str,
        regime: str,
        technical_score: float,
        breadth_ratio: float,
    ) -> str:
        raw = str(status_text or "").strip()
        known = {
            "risk_on": "偏强",
            "risk_off": "偏弱",
            "balanced": "中性",
            "偏强": "偏强",
            "偏弱": "偏弱",
            "中性": "中性",
            "平衡": "中性",
        }
        lowered = raw.lower()
        if lowered in known:
            return known[lowered]
        for marker, normalized in (
            ("risk_on", "偏强"),
            ("risk-off", "偏弱"),
            ("risk_off", "偏弱"),
            ("偏强", "偏强"),
            ("强势", "偏强"),
            ("风险偏好回升", "偏强"),
            ("偏弱", "偏弱"),
            ("防守", "偏弱"),
            ("避险", "偏弱"),
            ("风险偏好下降", "偏弱"),
            ("震荡", "中性"),
            ("平衡", "中性"),
            ("中性", "中性"),
        ):
            if marker in raw:
                return normalized

        normalized_regime = str(regime or "").strip().lower()
        if normalized_regime in known:
            return known[normalized_regime]
        if technical_score >= 60 and breadth_ratio >= 50:
            return "偏强"
        if technical_score <= 40 and breadth_ratio <= 45:
            return "偏弱"
        return "中性"

    @staticmethod
    def _build_fallback_summary(
        market_label: str,
        status_text: str,
        breadth_ratio: float,
        technical_score: float,
        benchmarks: List[Dict[str, object]]
    ) -> str:
        strongest = sorted(
            benchmarks,
            key=lambda item: abs(float(item.get("changePercent") or 0)),
            reverse=True
        )[:2]
        benchmark_text = "、".join(
            f"{item.get('name', item.get('symbol'))}{float(item.get('changePercent') or 0):+.2f}%"
            for item in strongest
        ) or "基准行情平稳"
        rhythm = "顺势分批" if breadth_ratio >= 55 and technical_score >= 50 else "控制节奏" if breadth_ratio >= 40 else "偏防守"
        risk_hint = "波动偏大，注意仓位控制" if breadth_ratio < 40 else "主线尚在，注意强弱分化"
        return (
            f"标题: {market_label}技术扫描\n"
            f"市场状态: {status_text}\n"
            f"技术观察: 广度 {breadth_ratio:.2f}% ，综合技术分 {technical_score:.2f} ，重点观察 {benchmark_text}\n"
            f"风险提示: {risk_hint}\n"
            f"操作节奏: {rhythm}\n"
            f"一句结论: {market_label} 当前以真实行情快照为主，系统已生成无模型降级摘要。"
        )

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
