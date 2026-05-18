"""
AI分析模块
负责AI海选、深度决策等功能
"""
import re
from core.analysis.ai_analyst import AIAnalyst
from core.analysis.AiConsultant import AiConsultant
from utils.MonitorLink import MonitorLink

class AIAnalyzer:
    @staticmethod
    def ai_screening(summary_data):
        """AI海选：从扫描结果中选出最具交易价值的股票"""
        try:
            if not summary_data:
                MonitorLink.log("⚠️ [AI海选] 无数据可供分析")
                return None
            
            MonitorLink.log(f"🧠 [AI 海选] 开始分析 {len(summary_data)} 只股票")
            
            # 直接使用手动筛选策略，跳过AI模型调用
            MonitorLink.log("🧠 [AI 海选] 使用手动筛选策略")
            return AIAnalyzer._manual_screening(summary_data)
        except Exception as e:
            MonitorLink.log(f"⚠️ [AI海选] 异常: {str(e)[:100]}")
            # 异常时使用备用策略
            return AIAnalyzer._manual_screening(summary_data)
    
    @staticmethod
    def _manual_screening(summary_data):
        """手动筛选符合条件的股票"""
        filtered_stocks = []
        
        MonitorLink.log(f"🧠 [AI 海选] 开始手动筛选 {len(summary_data)} 只股票")
        
        for item in summary_data:
            # 提取技术指标
            rsi_match = re.search(r'RSI:(\d+\.\d+)', item)
            kdj_match = re.search(r'KDJ:(\d+\.\d+)', item)
            cci_match = re.search(r'CCI:(\d+\.\d+)', item)
            macd_match = re.search(r'MACD:(\d+\.\d+)', item)
            
            # 提取股票代码
            symbol_match = re.search(r'([A-Z]{2,4}\.US)', item)
            if not symbol_match:
                continue
            symbol = symbol_match.group(1)
            
            if rsi_match:
                rsi = float(rsi_match.group(1))
                # 筛选RSI超买超卖的股票
                if rsi < 32 or rsi > 68:
                    if symbol not in filtered_stocks:
                        filtered_stocks.append(symbol)
                        MonitorLink.log(f"   [RSI筛选] {symbol} (RSI: {rsi})")
            
            if kdj_match:
                kdj = float(kdj_match.group(1))
                # 筛选KDJ超买超卖的股票
                if kdj < 20 or kdj > 80:
                    if symbol not in filtered_stocks:
                        filtered_stocks.append(symbol)
                        MonitorLink.log(f"   [KDJ筛选] {symbol} (KDJ: {kdj})")
            
            if cci_match:
                cci = float(cci_match.group(1))
                # 筛选CCI超买超卖的股票
                if cci < -100 or cci > 100:
                    if symbol not in filtered_stocks:
                        filtered_stocks.append(symbol)
                        MonitorLink.log(f"   [CCI筛选] {symbol} (CCI: {cci})")
        
        # 不限制数量，让所有符合条件的股票都进入深度分析阶段
        if filtered_stocks:
            MonitorLink.log(f"   [筛选结果] 共筛选出 {len(filtered_stocks)} 只符合条件的股票")
        
        if filtered_stocks:
            shortlist = ",".join(filtered_stocks)
            MonitorLink.log(f"🎯 备用策略潜力清单: {shortlist}")
            return shortlist
        else:
            MonitorLink.log("⚠️ [AI海选] 备用策略也未发现符合条件的股票")
            return None
    
    @staticmethod
    def clean_symbols(raw):
        """清洗AI返回的股票代码"""
        if not raw:
            return ""
        
        # 移除多余空格和换行
        cleaned = raw.strip().replace('\n', ' ')
        
        # 提取股票代码（支持 .US 和不带后缀的格式）
        symbols = re.findall(r'[A-Z]{2,4}(?:\.[A-Z]{2,3})?', cleaned)
        
        # 去重
        unique_symbols = list(dict.fromkeys(symbols))
        
        # 不限制数量，让所有符合条件的股票都进入深度分析阶段
        
        return ",".join(unique_symbols)
    
    @staticmethod
    def ai_deep_analysis(shortlist, summary_data, holds):
        """AI深度决策：对海选出的股票进行深度分析"""
        if not shortlist:
            MonitorLink.log("⚠️ [AI深度分析] 空的候选列表")
            return []
        
        targets = [s.strip() for s in shortlist.split(",") if s.strip()]
        results = []
        
        MonitorLink.log(f"🧐 [AI 诊断] 开始分析 {len(targets)} 只候选股票")
        
        # 遍历所有目标股票，分析所有符合条件的股票
        for target in targets:
            MonitorLink.log(f"🧐 [AI 诊断] 分析 {target} 的交易价值...")
            
            # 提取股票数据
            stock_data = AIAnalyzer._extract_stock_data(summary_data, target)
            
            MonitorLink.log(f"   [数据提取] 价格: {stock_data['price']}, RSI: {stock_data['rsi']}, KDJ: {stock_data['kdj']}, CCI: {stock_data['cci']}")
            
            if stock_data["price"] > 0:
                # 确定交易方向
                if stock_data["rsi"] < 32:
                    algo_side = "BUY"
                elif stock_data["rsi"] > 68:
                    algo_side = "SELL"
                elif stock_data["kdj"] < 20:
                    algo_side = "BUY"
                elif stock_data["kdj"] > 80:
                    algo_side = "SELL"
                elif stock_data["cci"] < -100:
                    algo_side = "BUY"
                elif stock_data["cci"] > 100:
                    algo_side = "SELL"
                else:
                    # 如果没有明显的超买超卖信号，根据RSI的一般水平决定方向
                    algo_side = "BUY" if stock_data["rsi"] < 50 else "SELL"
                
                MonitorLink.log(f"   [交易方向] {algo_side}")
                
                # 使用 AiConsultant 进行三模型分析
                verdict, reason = AiConsultant.get_final_decision(target, algo_side, stock_data)
                
                MonitorLink.log(f"   [AI决策] {verdict}")
                
                # 分析所有符合条件的股票
                if verdict in ["BUY", "SELL"]:
                    MonitorLink.log(f"🎯 [AI 诊断] {target} 符合交易条件")
                    results.append((target, stock_data, verdict, reason))
                else:
                    MonitorLink.log(f"⚠️ [AI诊断] {target} 不符合交易条件，决策: {verdict}")
            else:
                MonitorLink.log(f"⚠️ [AI诊断] {target} 数据不完整，价格: {stock_data['price']}")
        
        # 如果没有符合条件的股票，返回空列表
        if not results:
            MonitorLink.log("⚠️ [AI深度分析] 未发现符合交易条件的股票")
        else:
            MonitorLink.log(f"🎯 [AI深度分析] 发现 {len(results)} 只符合交易条件的股票")
        
        return results
    
    @staticmethod
    def _extract_stock_data(summary_data, target):
        """从汇总数据中提取目标股票的技术指标"""
        curr_p = 0.0
        rsi = 0.0
        kdj_k = 0.0
        cci = 0.0
        macd_h = 0.0
        atr = 0.0
        roc = 0.0
        
        for item in summary_data:
            if target in item:
                price_match = re.search(r'P:(\d+\.\d+)', item)
                rsi_match = re.search(r'RSI:(\d+\.\d+)', item)
                kdj_match = re.search(r'KDJ:(\d+\.\d+)', item)
                cci_match = re.search(r'CCI:(\d+\.\d+)', item)
                macd_match = re.search(r'MACD:(\d+\.\d+)', item)
                atr_match = re.search(r'ATR:(\d+\.\d+)', item)
                roc_match = re.search(r'ROC:(\d+\.\d+)', item)
                
                if price_match:
                    curr_p = float(price_match.group(1))
                if rsi_match:
                    rsi = float(rsi_match.group(1))
                if kdj_match:
                    kdj_k = float(kdj_match.group(1))
                if cci_match:
                    cci = float(cci_match.group(1))
                if macd_match:
                    macd_h = float(macd_match.group(1))
                if atr_match:
                    atr = float(atr_match.group(1))
                if roc_match:
                    roc = float(roc_match.group(1))
                break
        
        return {
            "price": curr_p,
            "rsi": rsi,
            "kdj": kdj_k,
            "cci": cci,
            "macd": macd_h,
            "atr": atr,
            "roc": roc
        }
    
    @staticmethod
    def analyze_single_stock(symbol, stock_data, holds):
        """对单个股票进行AI分析"""
        try:
            # 确定交易方向
            algo_side = "SELL"  # 对于持仓股票，默认为卖出分析
            
            # 使用 AiConsultant 进行三模型分析
            verdict, reason = AiConsultant.get_final_decision(symbol, algo_side, stock_data)
            
            return verdict, reason
        except Exception as e:
            MonitorLink.log(f"⚠️ [AI分析] 分析 {symbol} 时出错: {str(e)[:100]}")
            return "HOLD", "分析出错"