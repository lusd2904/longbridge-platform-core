"""
数据持久化模块
管理扫描结果、AI分析历史的存储和查询
"""
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from utils.DbUtil import DbUtil
from utils.LoggerUtil import get_logger

logger = get_logger(__name__)


def _trim_text(value: Optional[Any], max_length: Optional[int] = None) -> str:
    """清洗并截断文本，避免写库时超过字段容量。"""
    text = "" if value is None else str(value).strip()
    if max_length is not None and len(text) > max_length:
        return text[:max_length]
    return text


@dataclass
class ScanResult:
    """扫描结果数据类"""
    id: Optional[int] = None
    symbol: str = ""
    market: str = ""
    price: float = 0.0
    score: int = 0
    suggestion: str = ""
    suggestion_detail: str = ""
    indicators: Dict[str, Any] = None
    scan_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        # 处理datetime序列化
        for key in ['scan_time', 'created_at']:
            if data[key]:
                data[key] = data[key].isoformat()
        # 处理indicators JSON
        if data['indicators']:
            data['indicators'] = json.dumps(data['indicators'])
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScanResult':
        """从字典创建"""
        # 处理datetime反序列化
        for key in ['scan_time', 'created_at']:
            if data.get(key) and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        # 处理indicators JSON
        if data.get('indicators') and isinstance(data['indicators'], str):
            data['indicators'] = json.loads(data['indicators'])
        return cls(**data)


@dataclass
class AIAnalysisHistory:
    """AI分析历史数据类"""
    id: Optional[int] = None
    user_id: int = 1
    symbol: str = ""
    market: str = ""
    price: float = 0.0
    
    # Gemma分析
    gemma_decision: str = ""
    gemma_confidence: float = 0.0
    gemma_analysis: str = ""
    
    # Llama分析
    llama_decision: str = ""
    llama_confidence: float = 0.0
    llama_analysis: str = ""
    
    # DeepSeek分析
    deepseek_decision: str = ""
    deepseek_confidence: float = 0.0
    deepseek_analysis: str = ""
    
    # 综合决策
    final_decision: str = ""
    final_confidence: float = 0.0
    
    # 技术指标
    indicators: Dict[str, Any] = None
    
    analysis_time: Optional[datetime] = None
    created_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        for key in ['analysis_time', 'created_at']:
            if data[key]:
                data[key] = data[key].isoformat()
        if data['indicators']:
            data['indicators'] = json.dumps(data['indicators'])
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AIAnalysisHistory':
        """从字典创建"""
        for key in ['analysis_time', 'created_at']:
            if data.get(key) and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key])
        if data.get('indicators') and isinstance(data['indicators'], str):
            data['indicators'] = json.loads(data['indicators'])
        return cls(**data)


class DataPersistenceManager:
    """数据持久化管理器"""
    
    def __init__(self):
        """初始化数据持久化管理器"""
        self.db = DbUtil()
        self._ensure_tables()
    
    def _ensure_tables(self):
        """确保表结构存在"""
        # 扫描结果表
        scan_table_sql = """
        CREATE TABLE IF NOT EXISTS scan_results (
            id INT AUTO_INCREMENT PRIMARY KEY,
            symbol VARCHAR(20) NOT NULL,
            market VARCHAR(10) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            score INT NOT NULL,
            suggestion VARCHAR(50) NOT NULL,
            suggestion_detail TEXT,
            indicators JSON,
            scan_time DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_symbol (symbol),
            INDEX idx_scan_time (scan_time),
            INDEX idx_market (market),
            INDEX idx_suggestion (suggestion)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        
        # AI分析历史表
        ai_analysis_table_sql = """
        CREATE TABLE IF NOT EXISTS ai_analysis_history (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL DEFAULT 1,
            symbol VARCHAR(20) NOT NULL,
            market VARCHAR(10) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            gemma_decision VARCHAR(20),
            gemma_confidence DECIMAL(5, 2),
            gemma_analysis TEXT,
            llama_decision VARCHAR(20),
            llama_confidence DECIMAL(5, 2),
            llama_analysis TEXT,
            deepseek_decision VARCHAR(20),
            deepseek_confidence DECIMAL(5, 2),
            deepseek_analysis TEXT,
            final_decision VARCHAR(20),
            final_confidence DECIMAL(5, 2),
            indicators JSON,
            analysis_time DATETIME NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user_symbol (user_id, symbol),
            INDEX idx_symbol (symbol),
            INDEX idx_analysis_time (analysis_time),
            INDEX idx_market (market),
            INDEX idx_final_decision (final_decision)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        
        try:
            self.db.execute(scan_table_sql)
            self.db.execute(ai_analysis_table_sql)
            self._ensure_ai_analysis_columns()
            logger.info("数据持久化表结构检查完成")
        except Exception as e:
            logger.error(f"创建表失败: {e}")
            raise

    def _ensure_ai_analysis_columns(self):
        desired_columns = {
            'user_id': "INT NOT NULL DEFAULT 1",
        }
        for column_name, column_sql in desired_columns.items():
            exists = self.db.fetch_one(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = DATABASE() AND table_name = 'ai_analysis_history' AND column_name = %s
                """,
                (column_name,)
            )
            if not exists:
                self.db.execute(f"ALTER TABLE ai_analysis_history ADD COLUMN {column_name} {column_sql}")
    
    # ==================== 扫描结果操作 ====================
    
    def save_scan_result(self, result: ScanResult) -> int:
        """
        保存扫描结果
        
        Args:
            result: 扫描结果对象
            
        Returns:
            插入的记录ID
        """
        sql = """
        INSERT INTO scan_results 
        (symbol, market, price, score, suggestion, suggestion_detail, indicators, scan_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        params = (
            result.symbol,
            result.market,
            result.price,
            result.score,
            result.suggestion,
            result.suggestion_detail,
            json.dumps(result.indicators) if result.indicators else None,
            result.scan_time or datetime.now()
        )
        
        try:
            result_id = self.db.execute(sql, params)
            logger.info(f"扫描结果已保存: {result.symbol}, ID: {result_id}")
            return result_id
        except Exception as e:
            logger.error(f"保存扫描结果失败: {e}")
            raise
    
    def save_scan_results_batch(self, results: List[ScanResult]) -> int:
        """
        批量保存扫描结果
        
        Args:
            results: 扫描结果列表
            
        Returns:
            插入的记录数
        """
        if not results:
            return 0
        
        sql = """
        INSERT INTO scan_results 
        (symbol, market, price, score, suggestion, suggestion_detail, indicators, scan_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        params_list = [
            (
                r.symbol,
                r.market,
                r.price,
                r.score,
                r.suggestion,
                r.suggestion_detail,
                json.dumps(r.indicators) if r.indicators else None,
                r.scan_time or datetime.now()
            )
            for r in results
        ]
        
        try:
            count = self.db.execute_many(sql, params_list)
            logger.info(f"批量保存扫描结果: {count}条")
            return count
        except Exception as e:
            logger.error(f"批量保存扫描结果失败: {e}")
            raise
    
    def get_scan_results(self, 
                        symbol: Optional[str] = None,
                        market: Optional[str] = None,
                        start_time: Optional[datetime] = None,
                        end_time: Optional[datetime] = None,
                        suggestion: Optional[str] = None,
                        min_score: Optional[int] = None,
                        max_score: Optional[int] = None,
                        limit: int = 100,
                        offset: int = 0) -> Tuple[List[ScanResult], int]:
        """
        查询扫描结果
        
        Returns:
            (结果列表, 总数)
        """
        where_conditions = []
        params = []
        
        if symbol:
            where_conditions.append("symbol = %s")
            params.append(symbol)
        
        if market:
            where_conditions.append("market = %s")
            params.append(market)
        
        if start_time:
            where_conditions.append("scan_time >= %s")
            params.append(start_time)
        
        if end_time:
            where_conditions.append("scan_time <= %s")
            params.append(end_time)
        
        if suggestion:
            where_conditions.append("suggestion = %s")
            params.append(suggestion)
        
        if min_score is not None:
            where_conditions.append("score >= %s")
            params.append(min_score)
        
        if max_score is not None:
            where_conditions.append("score <= %s")
            params.append(max_score)
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        # 查询总数
        count_sql = f"SELECT COUNT(*) as total FROM scan_results WHERE {where_clause}"
        total_result = self.db.fetch_one(count_sql, params)
        total = total_result['total'] if total_result else 0

        # 查询数据
        sql = f"""
        SELECT * FROM scan_results 
        WHERE {where_clause}
        ORDER BY scan_time DESC
        LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])

        rows = self.db.query_all(sql, tuple(params))
        results = [ScanResult.from_dict(row) for row in rows]

        return results, total
    
    def get_latest_scan_result(self, symbol: str) -> Optional[ScanResult]:
        """获取最新的扫描结果"""
        sql = """
        SELECT * FROM scan_results 
        WHERE symbol = %s
        ORDER BY scan_time DESC
        LIMIT 1
        """
        
        row = self.db.fetch_one(sql, (symbol,))
        if row:
            return ScanResult.from_dict(row)
        return None

    def delete_old_scan_results(self, days: int = 30) -> int:
        """删除旧的扫描结果"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        sql = "DELETE FROM scan_results WHERE scan_time < %s"
        
        try:
            count = self.db.execute(sql, (cutoff_date,))
            logger.info(f"删除旧扫描结果: {count}条")
            return count
        except Exception as e:
            logger.error(f"删除旧扫描结果失败: {e}")
            raise
    
    # ==================== AI分析历史操作 ====================
    
    def save_ai_analysis(self, analysis: AIAnalysisHistory) -> int:
        """
        保存AI分析历史
        
        Args:
            analysis: AI分析历史对象
            
        Returns:
            插入的记录ID
        """
        sql = """
        INSERT INTO ai_analysis_history 
        (user_id, symbol, market, price, 
         gemma_decision, gemma_confidence, gemma_analysis,
         llama_decision, llama_confidence, llama_analysis,
         deepseek_decision, deepseek_confidence, deepseek_analysis,
         final_decision, final_confidence, indicators, analysis_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        params = (
            int(analysis.user_id or 1),
            analysis.symbol,
            analysis.market,
            analysis.price,
            _trim_text(analysis.gemma_decision, 20),
            analysis.gemma_confidence,
            _trim_text(analysis.gemma_analysis, 12000),
            _trim_text(analysis.llama_decision, 20),
            analysis.llama_confidence,
            _trim_text(analysis.llama_analysis, 12000),
            _trim_text(analysis.deepseek_decision, 20),
            analysis.deepseek_confidence,
            _trim_text(analysis.deepseek_analysis, 12000),
            _trim_text(analysis.final_decision, 20),
            analysis.final_confidence,
            json.dumps(analysis.indicators) if analysis.indicators else None,
            analysis.analysis_time or datetime.now()
        )
        
        try:
            result_id = self.db.execute(sql, params)
            logger.info(f"AI分析历史已保存: {analysis.symbol}, ID: {result_id}")
            return result_id
        except Exception as e:
            logger.error(f"保存AI分析历史失败: {e}")
            raise
    
    def get_ai_analysis_history(self,
                               user_id: Optional[int] = None,
                               symbol: Optional[str] = None,
                               market: Optional[str] = None,
                               start_time: Optional[datetime] = None,
                               end_time: Optional[datetime] = None,
                               final_decision: Optional[str] = None,
                               limit: int = 100,
                               offset: int = 0) -> Tuple[List[AIAnalysisHistory], int]:
        """
        查询AI分析历史
        
        Returns:
            (结果列表, 总数)
        """
        where_conditions = []
        params = []

        if user_id is not None:
            where_conditions.append("user_id = %s")
            params.append(user_id)
        
        if symbol:
            where_conditions.append("symbol = %s")
            params.append(symbol)
        
        if market:
            where_conditions.append("market = %s")
            params.append(market)
        
        if start_time:
            where_conditions.append("analysis_time >= %s")
            params.append(start_time)
        
        if end_time:
            where_conditions.append("analysis_time <= %s")
            params.append(end_time)
        
        if final_decision:
            where_conditions.append("final_decision = %s")
            params.append(final_decision)
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        # 查询总数
        count_sql = f"SELECT COUNT(*) as total FROM ai_analysis_history WHERE {where_clause}"
        total_result = self.db.fetch_one(count_sql, params)
        total = total_result['total'] if total_result else 0

        # 查询数据
        sql = f"""
        SELECT * FROM ai_analysis_history 
        WHERE {where_clause}
        ORDER BY analysis_time DESC
        LIMIT %s OFFSET %s
        """
        params.extend([limit, offset])

        rows = self.db.query_all(sql, tuple(params))
        results = [AIAnalysisHistory.from_dict(row) for row in rows]

        return results, total

    def get_latest_ai_analysis(self, symbol: str, user_id: Optional[int] = None) -> Optional[AIAnalysisHistory]:
        """获取最新的AI分析"""
        sql = """
        SELECT * FROM ai_analysis_history 
        WHERE symbol = %s
        ORDER BY analysis_time DESC
        LIMIT 1
        """

        params = [symbol]
        if user_id is not None:
            sql = """
            SELECT * FROM ai_analysis_history
            WHERE symbol = %s AND user_id = %s
            ORDER BY analysis_time DESC
            LIMIT 1
            """
            params.append(user_id)

        row = self.db.fetch_one(sql, tuple(params))
        if row:
            return AIAnalysisHistory.from_dict(row)
        return None
    
    def get_analysis_statistics(self, 
                               user_id: Optional[int] = None,
                               symbol: Optional[str] = None,
                               days: int = 30) -> Dict[str, Any]:
        """
        获取分析统计
        
        Args:
            symbol: 股票代码（可选）
            days: 统计天数
            
        Returns:
            统计信息
        """
        start_date = datetime.now() - timedelta(days=days)
        
        where_clause = "analysis_time >= %s"
        params = [start_date]

        if user_id is not None:
            where_clause += " AND user_id = %s"
            params.append(user_id)
        
        if symbol:
            where_clause += " AND symbol = %s"
            params.append(symbol)
        
        sql = f"""
        SELECT 
            final_decision,
            COUNT(*) as count,
            AVG(final_confidence) as avg_confidence
        FROM ai_analysis_history
        WHERE {where_clause}
        GROUP BY final_decision
        """
        
        rows = self.db.query_all(sql, tuple(params))
        
        return {
            'period_days': days,
            'symbol': symbol or 'all',
            'decision_distribution': {row['final_decision']: {
                'count': row['count'],
                'avg_confidence': float(row['avg_confidence']) if row['avg_confidence'] else 0
            } for row in rows}
        }
    
    def delete_old_ai_analysis(self, days: int = 90) -> int:
        """删除旧的AI分析历史"""
        cutoff_date = datetime.now() - timedelta(days=days)
        
        sql = "DELETE FROM ai_analysis_history WHERE analysis_time < %s"
        
        try:
            count = self.db.execute(sql, (cutoff_date,))
            logger.info(f"删除旧AI分析历史: {count}条")
            return count
        except Exception as e:
            logger.error(f"删除旧AI分析历史失败: {e}")
            raise


# 全局实例
_persistence_manager = None

def get_persistence_manager() -> DataPersistenceManager:
    """获取全局数据持久化管理器"""
    global _persistence_manager
    if _persistence_manager is None:
        _persistence_manager = DataPersistenceManager()
    return _persistence_manager
