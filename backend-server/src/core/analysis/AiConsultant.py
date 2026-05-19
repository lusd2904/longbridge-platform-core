import re
from typing import Dict, Optional, Tuple

from core.analysis.ai_analyst import AIAnalyst
from utils.MonitorLink import MonitorLink


class AiConsultant:
    @staticmethod
    def get_final_decision(symbol, algo_side, data):
        verdict, reason, *_ = AiConsultant.get_final_decision_with_details(symbol, algo_side, data)
        return verdict, reason

    @staticmethod
    def get_final_decision_with_details(symbol, algo_side, data):
        """三层 AI 扫描：市场脉冲层、风险筛查层、决策终审层。"""
        MonitorLink.log(f"🔍 [AI联调] 启动: {symbol} (原始信号: {algo_side})")

        stock_name = AiConsultant._lookup_stock_name(symbol)
        market_context = AiConsultant._market_context(data)
        indicators_desc = AiConsultant._indicator_overview(symbol, stock_name, algo_side, data, market_context)
        user_id = int(data.get('user_id') or 1)

        combined_prompt = AiConsultant._build_combined_analysis_prompt(
            stock_name=stock_name,
            symbol=symbol,
            algo_side=algo_side,
            indicators_desc=indicators_desc,
        )
        combined_text = AIAnalyst.get_decision(None, combined_prompt, task='scan_final', user_id=user_id)

        sections = AiConsultant._extract_combined_sections(combined_text)
        if sections:
            pulse_text = sections["pulse"]
            risk_text = sections["risk"]
            decision_text = sections["decision"]

            if not AiConsultant._is_unusable_response(
                pulse_text,
                required_fields=['趋势判断', '指标共振', '大盘联动', '机会窗口', '一句结论', '建议标签']
            ) and not AiConsultant._is_unusable_response(
                risk_text,
                required_fields=['情绪温度', '资金流与波动', '主要风险', '仓位建议', '市场环境', '一句结论', '建议标签']
            ) and not AiConsultant._is_unusable_response(
                decision_text,
                required_fields=['趋势判断', '关键指标', '市场扫描', '操作策略', '目标价位', '止损价位', '综合置信度', '最终决策', '详细理由']
            ):
                MonitorLink.log(f"   [市场脉冲层]: {pulse_text[:240]}")
                MonitorLink.log(f"   [风险筛查层]: {risk_text[:240]}")
                MonitorLink.log(f"   [决策终审层]: {decision_text[:240]}")
                verdict = AiConsultant._extract_verdict(decision_text, fallback=algo_side)
                pulse_analysis = AiConsultant._build_pulse_analysis(pulse_text, algo_side, data, verdict)
                risk_analysis = AiConsultant._build_risk_analysis(risk_text, data, verdict)
                decision_analysis = AiConsultant._build_decision_analysis(decision_text, data, market_context, verdict)

                reason = (
                    f"市场环境{market_context.get('summary', '中性')}，"
                    f"脉冲层判断{pulse_analysis.get('trend', '震荡整理')}，"
                    f"风险层提示{risk_analysis.get('risk', '中性风险')}，"
                    f"终审层给出{verdict}。"
                )

                try:
                    from utils.DbUtil import DbUtil

                    DbUtil.add_web_log(
                        f"[AI决策] {symbol} | Pulse:{pulse_text[:100]}... | "
                        f"Risk:{risk_text[:100]}... | Final:{decision_text[:100]}... | 状态:{verdict}"
                    )
                except Exception as exc:
                    MonitorLink.log(f"⚠️ [AI联调] 记录日志失败: {exc}")

                return verdict, reason, pulse_analysis, risk_analysis, decision_analysis

        if AiConsultant._is_timeout_fallback(combined_text, task='scan_final'):
            MonitorLink.log("⚠️ [AI联调] 综合分析超时，使用本地降级结果")
            return AiConsultant._build_timeout_downgrade(symbol, algo_side, data, market_context, combined_text)

        MonitorLink.log("⚠️ [AI联调] 综合单次分析返回格式不完整，回退三层链路")
        return AiConsultant._run_legacy_layered_analysis(symbol, algo_side, data, market_context, user_id)

    @staticmethod
    def _build_combined_analysis_prompt(stock_name: str, symbol: str, algo_side: str, indicators_desc: str) -> str:
        return f"""你是“持仓综合分析器”。
请一次性输出三个区块，且必须严格按以下标题和字段顺序返回，不要使用 Markdown，不要输出额外解释。
先基于指标快照生成“市场脉冲层”，再结合脉冲层生成“风险筛查层”，最后结合前两层生成“决策终审层”。

市场脉冲层:
趋势判断: ...
指标共振: ...
大盘联动: ...
机会窗口: ...
一句结论: ...
建议标签: BUY/SELL/HOLD

风险筛查层:
情绪温度: ...
资金流与波动: ...
主要风险: ...
仓位建议: ...
市场环境: ...
一句结论: ...
建议标签: BUY/SELL/HOLD

决策终审层:
趋势判断: ...
关键指标: ...
市场扫描: ...
操作策略: ...
目标价位: $...
止损价位: $...
基本面评分: x/10
技术面评分: x/10
资金面评分: x/10
大盘共振评分: x/10
综合置信度: x%
最终决策: BUY/SELL/HOLD
详细理由: ...

标的: {stock_name} ({symbol})
算法原始信号: {algo_side}

{indicators_desc}
"""

    @staticmethod
    def _extract_layer_block(text: str, label: str, trailing_labels: Tuple[str, ...] = ()) -> str:
        content = str(text or "").strip()
        if not content:
            return ""

        if trailing_labels:
            trailing_pattern = "|".join(re.escape(item) for item in trailing_labels)
            pattern = rf"{re.escape(label)}\s*[:：]\s*(.*?)(?=\n(?:{trailing_pattern})\s*[:：]|\Z)"
        else:
            pattern = rf"{re.escape(label)}\s*[:：]\s*(.*)\Z"

        match = re.search(pattern, content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""

    @staticmethod
    def _extract_combined_sections(text: str) -> Optional[Dict[str, str]]:
        pulse_text = AiConsultant._extract_layer_block(
            text,
            "市场脉冲层",
            ("风险筛查层", "决策终审层"),
        )
        risk_text = AiConsultant._extract_layer_block(
            text,
            "风险筛查层",
            ("决策终审层",),
        )
        decision_text = AiConsultant._extract_layer_block(text, "决策终审层")

        if not pulse_text or not risk_text or not decision_text:
            return None
        return {
            "pulse": pulse_text,
            "risk": risk_text,
            "decision": decision_text,
        }

    @staticmethod
    def _is_timeout_fallback(text: str, task: str) -> bool:
        fallback = AIAnalyst._safe_scan_fallback(task)
        if not fallback:
            return False
        return str(text or "").strip() == fallback.strip()

    @staticmethod
    def _build_timeout_downgrade(symbol: str, algo_side: str, data: Dict, market_context: Dict, decision_text: str):
        pulse_text = AIAnalyst._safe_scan_fallback("scan_pulse") or ""
        risk_text = AIAnalyst._safe_scan_fallback("scan_risk") or ""
        final_text = decision_text or AIAnalyst._safe_scan_fallback("scan_final") or ""

        verdict = AiConsultant._extract_verdict(final_text, fallback=algo_side)
        pulse_analysis = AiConsultant._build_pulse_analysis(pulse_text, algo_side, data, verdict)
        risk_analysis = AiConsultant._build_risk_analysis(risk_text, data, verdict)
        decision_analysis = AiConsultant._build_decision_analysis(final_text, data, market_context, verdict)

        reason = (
            f"市场环境{market_context.get('summary', '中性')}，"
            f"脉冲层判断{pulse_analysis.get('trend', '震荡整理')}，"
            f"风险层提示{risk_analysis.get('risk', '中性风险')}，"
            f"终审层给出{verdict}。"
        )
        return verdict, reason, pulse_analysis, risk_analysis, decision_analysis

    @staticmethod
    def _run_legacy_layered_analysis(symbol, algo_side, data, market_context, user_id):
        stock_name = AiConsultant._lookup_stock_name(symbol)
        indicators_desc = AiConsultant._indicator_overview(symbol, stock_name, algo_side, data, market_context)

        pulse_prompt = f"""你是“市场脉冲层”分析师。
请只输出 6 行，禁止额外解释，必须使用以下字段：
趋势判断: ...
指标共振: ...
大盘联动: ...
机会窗口: ...
一句结论: ...
建议标签: BUY/SELL/HOLD

{indicators_desc}
"""
        pulse_text = AIAnalyst.get_decision(None, pulse_prompt, task='scan_pulse', user_id=user_id)
        if AiConsultant._is_unusable_response(
            pulse_text,
            required_fields=['趋势判断', '指标共振', '大盘联动', '机会窗口', '一句结论', '建议标签']
        ):
            raise RuntimeError("市场脉冲层未返回可用内容")
        MonitorLink.log(f"   [市场脉冲层]: {pulse_text[:240]}")

        risk_prompt = f"""你是“风险筛查层”分析师。
请只输出 6 行，禁止额外解释，必须使用以下字段：
情绪温度: ...
资金流与波动: ...
主要风险: ...
仓位建议: ...
市场环境: ...
一句结论: ...
建议标签: BUY/SELL/HOLD

{indicators_desc}

市场脉冲层结论:
{pulse_text}
"""
        risk_text = AIAnalyst.get_decision(None, risk_prompt, task='scan_risk', user_id=user_id)
        if AiConsultant._is_unusable_response(
            risk_text,
            required_fields=['情绪温度', '资金流与波动', '主要风险', '仓位建议', '市场环境', '一句结论', '建议标签']
        ):
            raise RuntimeError("风险筛查层未返回可用内容")
        MonitorLink.log(f"   [风险筛查层]: {risk_text[:240]}")

        decision_prompt = f"""你是“决策终审层”。
请严格按以下字段返回，尽量简短，不要使用 Markdown：
趋势判断: ...
关键指标: ...
市场扫描: ...
操作策略: ...
目标价位: $...
止损价位: $...
基本面评分: x/10
技术面评分: x/10
资金面评分: x/10
大盘共振评分: x/10
综合置信度: x%
最终决策: BUY/SELL/HOLD
详细理由: ...

{indicators_desc}

市场脉冲层:
{pulse_text}

风险筛查层:
{risk_text}
"""
        decision_text = AIAnalyst.get_decision(None, decision_prompt, task='scan_final', user_id=user_id)
        if AiConsultant._is_unusable_response(
            decision_text,
            required_fields=['趋势判断', '关键指标', '市场扫描', '操作策略', '目标价位', '止损价位', '综合置信度', '最终决策', '详细理由']
        ):
            raise RuntimeError("决策终审层未返回可用内容")
        MonitorLink.log(f"   [决策终审层]: {decision_text[:240]}")

        verdict = AiConsultant._extract_verdict(decision_text, fallback=algo_side)

        pulse_analysis = AiConsultant._build_pulse_analysis(pulse_text, algo_side, data, verdict)
        risk_analysis = AiConsultant._build_risk_analysis(risk_text, data, verdict)
        decision_analysis = AiConsultant._build_decision_analysis(decision_text, data, market_context, verdict)

        reason = (
            f"市场环境{market_context.get('summary', '中性')}，"
            f"脉冲层判断{pulse_analysis.get('trend', '震荡整理')}，"
            f"风险层提示{risk_analysis.get('risk', '中性风险')}，"
            f"终审层给出{verdict}。"
        )

        try:
            from utils.DbUtil import DbUtil

            DbUtil.add_web_log(
                f"[AI决策] {symbol} | Pulse:{pulse_text[:100]}... | "
                f"Risk:{risk_text[:100]}... | Final:{decision_text[:100]}... | 状态:{verdict}"
            )
        except Exception as exc:
            MonitorLink.log(f"⚠️ [AI联调] 记录日志失败: {exc}")

        return verdict, reason, pulse_analysis, risk_analysis, decision_analysis

    @staticmethod
    def _raise_on_model_error(layer_name: str, text: str) -> None:
        content = str(text or '').strip()
        if not content:
            raise RuntimeError(f"{layer_name}未返回有效内容")
        if content == 'ERROR' or content.startswith('ERROR'):
            detail = content.split(':', 1)[-1].strip() if ':' in content else content
            raise RuntimeError(f"{layer_name}模型调用失败: {detail}")

    @staticmethod
    def _is_model_error(text: str) -> bool:
        content = str(text or '').strip()
        return (not content) or content == 'ERROR' or content.startswith('ERROR')

    @staticmethod
    def _is_unusable_response(text: str, required_fields=None) -> bool:
        content = str(text or '').strip()
        if AiConsultant._is_model_error(content):
            return True

        lowered = content.lower()
        suspicious_markers = [
            'we need to output',
            'the user says',
            'no extra explanation',
            'must use',
            'exactly 6 lines',
            'exactly 7 lines',
            'that\'s 7 fields',
            'probably they want',
            'wait the user says',
            'must be chinese',
        ]
        if any(marker in lowered for marker in suspicious_markers):
            return True

        if required_fields:
            matched = sum(1 for field in required_fields if field in content)
            if matched < min(3, len(required_fields)):
                return True

        return False

    @staticmethod
    def _fallback_pulse_text(symbol: str, algo_side: str, data: Dict, market_context: Dict) -> str:
        rsi = float(data.get('rsi', 0) or 0)
        macd = float(data.get('macd', 0) or 0)
        trend = '偏强上行' if macd >= 0 and rsi >= 50 else '偏弱震荡' if macd < 0 and rsi <= 50 else '区间整理'
        window = '等待突破后跟随' if 45 <= rsi <= 65 else '短线已有节奏'
        signal = 'BUY' if algo_side == 'BUY' else 'SELL' if algo_side == 'SELL' else 'HOLD'
        return (
            f"趋势判断: {trend}\n"
            f"指标共振: RSI {rsi:.1f}，MACD {macd:.3f}，围绕均线系统波动\n"
            f"大盘联动: {market_context.get('summary', '暂无大盘快照')}\n"
            f"机会窗口: {window}\n"
            f"一句结论: {symbol} 当前以真实指标快照生成脉冲层判断，建议结合量价再确认。\n"
            f"建议标签: {signal}"
        )

    @staticmethod
    def _fallback_risk_text(symbol: str, data: Dict, market_context: Dict) -> str:
        atr = float(data.get('atr', 0) or 0)
        roc = float(data.get('roc', 0) or 0)
        risk = '波动放大，注意回撤' if atr > 5 or abs(roc) > 6 else '波动可控'
        signal = 'HOLD' if market_context.get('regime') == 'balanced' else 'BUY' if market_context.get('regime') == 'risk_on' else 'SELL'
        return (
            f"情绪温度: {market_context.get('risk_temperature', '中性')}\n"
            f"资金流与波动: ATR {atr:.2f} / ROC {roc:.2f}%\n"
            f"主要风险: {risk}\n"
            f"仓位建议: {'轻仓试探' if signal == 'BUY' else '控制仓位' if signal == 'HOLD' else '收缩敞口'}\n"
            f"市场环境: {market_context.get('summary', '暂无实时市场环境')}\n"
            f"一句结论: {symbol} 风险层已按真实波动数据完成降级判断。\n"
            f"建议标签: {signal}"
        )

    @staticmethod
    def _fallback_decision_text(
        symbol: str,
        algo_side: str,
        data: Dict,
        market_context: Dict,
        pulse_text: str,
        risk_text: str
    ) -> str:
        price = float(data.get('price', 0) or 0)
        support = float(data.get('support', 0) or 0)
        resistance = float(data.get('resistance', 0) or 0)
        verdict = 'BUY' if algo_side == 'BUY' and market_context.get('regime') != 'risk_off' else 'SELL' if algo_side == 'SELL' else 'HOLD'
        confidence = 68 if verdict == 'HOLD' else 74
        return (
            f"趋势判断: 结合脉冲层与风险层后，当前更适合 {verdict} 节奏\n"
            f"关键指标: 现价 {price:.2f}，支撑 {support:.2f}，阻力 {resistance:.2f}\n"
            f"市场扫描: {market_context.get('summary', '暂无')}\n"
            f"操作策略: {'顺势分批' if verdict == 'BUY' else '高位减仓' if verdict == 'SELL' else '继续观察'}\n"
            f"目标价位: ${max(price, resistance, support):.2f}\n"
            f"止损价位: ${support if support > 0 else max(price * 0.95, 0):.2f}\n"
            f"基本面评分: 6.8/10\n"
            f"技术面评分: 7.1/10\n"
            f"资金面评分: 6.6/10\n"
            f"大盘共振评分: 6.9/10\n"
            f"综合置信度: {confidence}%\n"
            f"最终决策: {verdict}\n"
            f"详细理由: 模型链路未返回完整结果，系统已基于真实技术指标、大盘快照和前两层降级摘要({pulse_text[:36]} / {risk_text[:36]})生成终审结论。"
        )

    @staticmethod
    def _lookup_stock_name(symbol: str) -> str:
        stock_name = symbol

        try:
            from utils.DbUtil import DbUtil

            queries = []
            if symbol.endswith('.SZ') or symbol.endswith('.SH') or symbol.endswith('.BJ'):
                queries = [
                    "SELECT name FROM cn_stocks WHERE symbol = %s LIMIT 1",
                    "SELECT etf_name FROM cn_etf WHERE symbol = %s LIMIT 1"
                ]
            elif symbol.endswith('.HK'):
                queries = [
                    "SELECT name FROM hk_stocks WHERE symbol = %s LIMIT 1",
                    "SELECT etf_name FROM hk_etf WHERE symbol = %s LIMIT 1"
                ]
            else:
                queries = [
                    "SELECT company_name FROM large_cap_stocks WHERE symbol = %s LIMIT 1",
                    "SELECT etf_name FROM us_etf WHERE symbol = %s LIMIT 1"
                ]

            for sql in queries:
                result = DbUtil.query_one(sql, (symbol,))
                if result and result[0]:
                    stock_name = result[0]
                    break
        except Exception as exc:
            MonitorLink.log(f"⚠️ [AI联调] 获取股票名称失败: {exc}")

        return stock_name

    @staticmethod
    def _market_context(data: Dict) -> Dict:
        context = data.get('market_context')
        if isinstance(context, dict) and context:
            return context

        return {
            "market": "US",
            "regime": "balanced",
            "risk_temperature": "中性",
            "summary": "暂无实时大盘快照，按中性环境处理",
            "benchmarks": []
        }

    @staticmethod
    def _indicator_overview(symbol: str, stock_name: str, algo_side: str, data: Dict, market_context: Dict) -> str:
        benchmark_lines = []
        for benchmark in market_context.get('benchmarks', []):
            benchmark_lines.append(
                f"- {benchmark.get('name', benchmark.get('symbol', '--'))}: "
                f"{benchmark.get('price', 0):.2f} ({benchmark.get('changePercent', 0):+.2f}%)"
            )

        benchmark_block = "\n".join(benchmark_lines) if benchmark_lines else "- 暂无基准行情"
        price = float(data.get('price', 0) or 0)
        rsi = float(data.get('rsi', 0) or 0)
        macd = float(data.get('macd', 0) or 0)
        kdj = float(data.get('kdj', 0) or 0)

        return f"""标的: {stock_name} ({symbol})
当前价格: ${price:.2f}
算法原始信号: {algo_side}

个股技术指标:
- RSI(14): {rsi:.1f} ({'超买' if rsi > 70 else '超卖' if rsi < 30 else '中性'})
- MACD: {macd:.3f} ({'多头' if macd >= 0 else '空头'})
- KDJ J值: {kdj:.1f}
- 布林带: 上轨 ${float(data.get('boll_upper', 0) or 0):.2f} / 中轨 ${float(data.get('boll_mid', 0) or 0):.2f} / 下轨 ${float(data.get('boll_lower', 0) or 0):.2f}
- EMA: 短期 ${float(data.get('ema_short', 0) or 0):.2f} / 长期 ${float(data.get('ema_long', 0) or 0):.2f}
- ATR: {float(data.get('atr', 0) or 0):.2f}
- ROC: {float(data.get('roc', 0) or 0):.2f}%
- CCI: {float(data.get('cci', 0) or 0):.1f}
- OBV: {float(data.get('obv', 0) or 0):.0f}
- 支撑位: ${float(data.get('support', 0) or 0):.2f}
- 阻力位: ${float(data.get('resistance', 0) or 0):.2f}

大盘扫描:
- 市场区域: {market_context.get('market', 'US')}
- 市场状态: {market_context.get('summary', '暂无')}
- 风险温度: {market_context.get('risk_temperature', '中性')}
- 基准表现:
{benchmark_block}
"""

    @staticmethod
    def _extract_field(text: str, patterns, default: str = "") -> str:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return default

    @staticmethod
    def _extract_score(text: str, label: str, default: float = 7.0) -> float:
        pattern = rf"{label}\s*[:：]\s*(\d+(?:\.\d+)?)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return default

    @staticmethod
    def _extract_confidence(text: str, default: int = 72) -> int:
        match = re.search(r"综合置信度\s*[:：]\s*(\d+)", text)
        if match:
            return int(match.group(1))

        generic = re.search(r"(\d+)%", text)
        if generic:
            return int(generic.group(1))
        return default

    @staticmethod
    def _extract_verdict(text: str, fallback: str = "HOLD") -> str:
        final_match = re.search(r"最终决策\s*[:：]\s*(BUY|SELL|HOLD)", text, re.IGNORECASE)
        if final_match:
            return final_match.group(1).upper()

        upper_text = text.upper()
        if "SELL" in upper_text or "卖出" in text:
            return "SELL"
        if "BUY" in upper_text or "买入" in text:
            return "BUY"
        if "HOLD" in upper_text or "持有" in text or "观望" in text:
            return "HOLD"
        return fallback if fallback in {"BUY", "SELL", "HOLD"} else "HOLD"

    @staticmethod
    def _build_pulse_analysis(text: str, algo_side: str, data: Dict, final_verdict: str) -> Dict:
        trend = AiConsultant._extract_field(
            text,
            [
                r"趋势判断\s*[:：]\s*(.+?)(?:\n|$)"
            ],
            default='上升趋势' if algo_side == 'BUY' else '下降趋势' if algo_side == 'SELL' else '震荡整理'
        )
        indicators = AiConsultant._extract_field(
            text,
            [
                r"指标共振\s*[:：]\s*(.+?)(?:\n|$)"
            ],
            default=f"RSI {float(data.get('rsi', 0) or 0):.1f} / MACD {float(data.get('macd', 0) or 0):.3f}"
        )
        market_link = AiConsultant._extract_field(
            text,
            [
                r"大盘联动\s*[:：]\s*(.+?)(?:\n|$)"
            ],
            default='与市场保持同步观察'
        )
        window = AiConsultant._extract_field(
            text,
            [
                r"机会窗口\s*[:：]\s*(.+?)(?:\n|$)"
            ],
            default='等待进一步确认'
        )
        summary = AiConsultant._extract_field(
            text,
            [
                r"一句结论\s*[:：]\s*(.+?)(?:\n|$)"
            ],
            default=text.strip()
        )
        signal = AiConsultant._extract_verdict(text, fallback=final_verdict)

        return {
            'role': '市场脉冲层',
            'summary': summary,
            'trend': trend,
            'indicators': indicators,
            'levels': f"支撑:${float(data.get('support', 0) or 0):.2f}, 阻力:${float(data.get('resistance', 0) or 0):.2f}",
            'market_link': market_link,
            'window': window,
            'signal': signal,
            'decision': signal,
            'full_text': text
        }

    @staticmethod
    def _build_risk_analysis(text: str, data: Dict, final_verdict: str) -> Dict:
        sentiment = AiConsultant._extract_field(
            text,
            [r"情绪温度\s*[:：]\s*(.+?)(?:\n|$)"],
            default='中性'
        )
        flow = AiConsultant._extract_field(
            text,
            [r"资金流与波动\s*[:：]\s*(.+?)(?:\n|$)"],
            default=f"ATR {float(data.get('atr', 0) or 0):.2f} / ROC {float(data.get('roc', 0) or 0):.2f}%"
        )
        risk = AiConsultant._extract_field(
            text,
            [r"主要风险\s*[:：]\s*(.+?)(?:\n|$)"],
            default='需结合仓位谨慎处理'
        )
        position_advice = AiConsultant._extract_field(
            text,
            [r"仓位建议\s*[:：]\s*(.+?)(?:\n|$)"],
            default='轻仓试探'
        )
        market_env = AiConsultant._extract_field(
            text,
            [r"市场环境\s*[:：]\s*(.+?)(?:\n|$)"],
            default='市场波动中'
        )
        summary = AiConsultant._extract_field(
            text,
            [r"一句结论\s*[:：]\s*(.+?)(?:\n|$)"],
            default=text.strip()
        )
        signal = AiConsultant._extract_verdict(text, fallback=final_verdict)

        return {
            'role': '风险筛查层',
            'summary': summary,
            'sentiment': sentiment,
            'flow': flow,
            'risk': risk,
            'market_env': market_env,
            'position_advice': position_advice,
            'signal': signal,
            'decision': signal,
            'full_text': text
        }

    @staticmethod
    def _build_decision_analysis(text: str, data: Dict, market_context: Dict, verdict: str) -> Dict:
        trend = AiConsultant._extract_field(
            text,
            [r"趋势判断\s*[:：]\s*(.+?)(?:\n|$)"],
            default='震荡整理'
        )
        indicators = AiConsultant._extract_field(
            text,
            [r"关键指标\s*[:：]\s*(.+?)(?:\n|$)"],
            default=f"RSI {float(data.get('rsi', 0) or 0):.1f}, MACD {float(data.get('macd', 0) or 0):.3f}"
        )
        market_scan = AiConsultant._extract_field(
            text,
            [r"市场扫描\s*[:：]\s*(.+?)(?:\n|$)"],
            default=market_context.get('summary', '暂无大盘快照')
        )
        strategy = AiConsultant._extract_field(
            text,
            [r"操作策略\s*[:：]\s*(.+?)(?:\n|$)"],
            default='建议等待确认后再操作'
        )
        target = AiConsultant._extract_field(
            text,
            [r"目标价位\s*[:：]\s*(\$?[\d,.]+)"],
            default=f"${float(data.get('resistance', 0) or 0):.2f}"
        )
        stop_loss = AiConsultant._extract_field(
            text,
            [r"止损价位\s*[:：]\s*(\$?[\d,.]+)"],
            default=f"${float(data.get('support', 0) or 0):.2f}"
        )
        detail_reason = AiConsultant._extract_field(
            text,
            [r"详细理由\s*[:：]\s*(.+?)(?:\n*$|$)"],
            default=text.strip()
        )

        fundamental_score = AiConsultant._extract_score(text, "基本面评分", default=6.8)
        technical_score = AiConsultant._extract_score(text, "技术面评分", default=7.4)
        capital_score = AiConsultant._extract_score(text, "资金面评分", default=7.1)
        market_score = AiConsultant._extract_score(text, "大盘共振评分", default=7.0)
        confidence = AiConsultant._extract_confidence(text, default=74)

        return {
            'role': '决策终审层',
            'summary': detail_reason,
            'trend': trend,
            'indicators': indicators,
            'market_scan': market_scan,
            'strategy': strategy,
            'target': target if target.startswith('$') else f"${target}",
            'stop_loss': stop_loss if stop_loss.startswith('$') else f"${stop_loss}",
            'fundamental_score': fundamental_score,
            'technical_score': technical_score,
            'capital_score': capital_score,
            'market_score': market_score,
            'confidence': confidence,
            'decision': verdict,
            'signal': verdict,
            'full_text': text
        }
