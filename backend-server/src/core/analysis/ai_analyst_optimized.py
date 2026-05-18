import requests
import time
from config.Config import AppConfig 
from utils.MonitorLink import MonitorLink
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

class AIAnalyst:
    @staticmethod
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((requests.exceptions.Timeout, requests.exceptions.ConnectionError)),
        reraise=True
    )
    def get_decision_with_retry(model: str, prompt: str) -> str:
        """带重试机制的AI决策获取"""
        return AIAnalyst._call_ai_model(model, prompt)
    
    @staticmethod
    def get_decision(model: str, prompt: str) -> str:
        """获取AI决策（带基本重试）"""
        for attempt in range(3):
            try:
                result = AIAnalyst._call_ai_model(model, prompt)
                if result and result != "ERROR":
                    return result
                MonitorLink.log(f"⚠️ AI {model} 返回空结果，重试 {attempt+1}/3")
                time.sleep(2 ** attempt)
            except Exception as e:
                MonitorLink.log(f"⚠️ AI {model} 调用失败 (尝试 {attempt+1}/3): {e}")
                if attempt < 2:
                    time.sleep(2 ** attempt)
                else:
                    import traceback
                    MonitorLink.log(f"❌ AI {model} 调用彻底失败:")
                    MonitorLink.log(traceback.format_exc())
        return "ERROR"
    
    @staticmethod
    def _call_ai_model(model: str, prompt: str) -> str:
        """调用AI模型的核心方法"""
        # 根据模型调整参数
        if "deepseek" in model.lower():
            timeout = 180
            num_predict = 1000
        else:
            timeout = AppConfig.get("AI_TIMEOUT", 60)
            num_predict = 500
            
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_thread": 4,
                "temperature": 0.4,
                "num_predict": num_predict
            }
        }

        MonitorLink.log(f"🔗 [AI] 请求模型: {model}")
        
        response = requests.post(
            AppConfig.get('AI_URL'), 
            json=payload, 
            timeout=timeout
        )
        
        if response.status_code != 200:
            raise Exception(f"API返回错误状态码: {response.status_code}, 响应: {response.text[:200]}")
        
        response_json = response.json()
        
        # 对于DeepSeek模型，检查thinking字段
        if "deepseek" in model.lower():
            thinking = response_json.get('thinking', "").strip()
            response_text = response_json.get('response', "").strip()
            result = f"{thinking}\n{response_text}"
            
            # 从思考过程中提取决策结果
            if "BUY" in thinking.upper() or "BUY" in response_text.upper():
                decision = "BUY"
            elif "SELL" in thinking.upper() or "SELL" in response_text.upper():
                decision = "SELL"
            elif "HOLD" in thinking.upper() or "HOLD" in response_text.upper():
                decision = "HOLD"
            else:
                decision = AIAnalyst._infer_decision(thinking, response_text)
            
            score = AIAnalyst._calculate_score(decision, thinking, response_text)
            result = f"{result}\n\n[决策]: {decision}\n[评分]: {score}/10"
        else:
            result = response_json.get('response', "").strip()
        
        if not result:
            raise Exception("AI模型返回空响应")
        
        MonitorLink.log(f"✅ [AI] {model} 调用成功")
        return result
    
    @staticmethod
    def _infer_decision(thinking: str, response: str) -> str:
        """从AI响应中推断决策"""
        combined_text = f"{thinking} {response}".upper()
        if "买入" in combined_text:
            return "BUY"
        elif "卖出" in combined_text:
            return "SELL"
        else:
            return "HOLD"
    
    @staticmethod
    def _calculate_score(decision: str, thinking: str, response: str) -> int:
        """根据决策和指标分析计算评分"""
        score = 7
        
        if decision == "BUY":
            if "RSI" in thinking and "超卖" in thinking:
                score = 9
            elif "KDJ" in thinking and "金叉" in thinking:
                score = 8
            elif "支撑位" in thinking:
                score = 8
        elif decision == "SELL":
            if "RSI" in thinking and "超买" in thinking:
                score = 9
            elif "KDJ" in thinking and "死叉" in thinking:
                score = 8
            elif "阻力位" in thinking:
                score = 8
        
        return score
