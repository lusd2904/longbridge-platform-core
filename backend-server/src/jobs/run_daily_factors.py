"""
量化大模型特征批处理作业 (Cron Job)
由 Linux Crontab 定时触发，针对不同市场的收盘时间错峰运行。
计算 Alpha 101 和 Alpha 158 因子，提取 Alphalens 验证过的 Top 5 因子存入高速缓存表。
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime

import pandas as pd

# 允许脚本作为独立模块运行
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.Alpha101 import Alpha101
from utils.Alpha158 import Alpha158
from utils.DbUtil import DbUtil
from utils.KLineDataFetcher import KLineDataFetcher

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("FactorBatchJob")

# 经过 Alphalens 提纯验证的 Top 5 黄金因子
# 实际生产中这些字段会每周被 Alphalens 质检脚本自动更新
TOP_5_GOLDEN_FACTORS = [
    "Alpha_012",  # 量价背离因子
    "ROC20",  # 20日动量
    "VMA10",  # 10日量能均线
    "QTLU20",  # 20日极值分布
    "BETA10",  # 10日大盘回归系数
]


def ensure_schema():
    """建立毫秒级特征缓存表"""
    DbUtil.execute_sql("""
        CREATE TABLE IF NOT EXISTS quant_factors_daily (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            symbol VARCHAR(32) NOT NULL,
            market VARCHAR(10) NOT NULL,
            trade_date DATE NOT NULL,
            golden_factors_json JSON DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uniq_sym_date (symbol, trade_date),
            INDEX idx_symbol_date (symbol, trade_date DESC)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """)


def process_symbol(symbol: str, market: str, trade_date: str):
    """拉取股票数据并提取特征写入库"""
    logger.info(f"正在计算 [{symbol}] 的 400+ 因子矩阵...")

    try:
        # 获取基础 K 线
        df = KLineDataFetcher.fetch_kline(symbol, period="daily")
        if df is None or df.empty or len(df) < 60:
            logger.warning(f"{symbol} 数据过少，跳过计算。")
            return

        # 安全处理缺失的列（比如无 vwap 时用典型价格替代）
        if "vwap" not in df.columns:
            df["vwap"] = (df["high"] + df["low"] + df["close"]) / 3

        # 第一级引擎：130+ 基础技术因子
        # IndicatorUtilEnhanced.generate_all_indicators(df)

        # 第二级引擎：158 个时序衍生交叉
        features_158 = Alpha158.generate_all(df)

        # 第三级引擎：101 个高频截面因子
        features_101 = Alpha101.generate_all(df)

        # 拼接为一个巨大的特征库 (内存级)
        combined_features = pd.concat([features_158, features_101], axis=1)

        # [核心] Alphalens 降维提纯：只提取经过验证的 Top 5 因子
        latest_row = combined_features.iloc[-1]

        # 构造注入给 AI 的特征 JSON
        golden_dict = {}
        for factor in TOP_5_GOLDEN_FACTORS:
            if factor in latest_row:
                val = latest_row[factor]
                # 简单规避 inf, nan
                if pd.isna(val) or val == float("inf") or val == float("-inf"):
                    golden_dict[factor] = 0.0
                else:
                    golden_dict[factor] = round(float(val), 4)

        factors_json = json.dumps(golden_dict)

        # 写入数据库供 Web 端秒开查询
        sql = """
            INSERT INTO quant_factors_daily (symbol, market, trade_date, golden_factors_json)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE 
            golden_factors_json = VALUES(golden_factors_json),
            updated_at = CURRENT_TIMESTAMP
        """
        DbUtil.execute_sql(sql, (symbol, market, trade_date, factors_json))
        logger.info(f"{symbol} 提纯成功并入库 -> {factors_json}")

    except Exception as e:
        logger.error(f"处理 {symbol} 失败: {e}")


def run_job(market: str):
    logger.info(f"====== 开始启动 {market} 收盘因子批处理任务 ======")
    ensure_schema()

    # 模拟获取当前市场的所有标的池（实际应从数据库查询目标池）
    symbols_pool = []
    if market == "US":
        symbols_pool = ["AAPL", "TSLA", "MSFT"]
    elif market == "HK":
        symbols_pool = ["00700", "03690"]
    elif market == "CN":
        symbols_pool = ["600519", "000858"]

    today_str = datetime.now().strftime("%Y-%m-%d")

    for sym in symbols_pool:
        process_symbol(sym, market, today_str)

    logger.info(f"====== {market} 因子批处理任务完成 ======")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="量化因子离线批处理脚本")
    parser.add_argument("--market", type=str, required=True, choices=["US", "HK", "CN"], help="目标市场")
    args = parser.parse_args()

    run_job(args.market)
