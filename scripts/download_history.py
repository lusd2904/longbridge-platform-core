import yfinance as yf
import pandas as pd
import os
import logging
from datetime import datetime

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 中线核心股票池 (Nasdaq 100 科技核心 + 价值蓝筹)
WATCHLIST = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA", 
    "JPM", "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD",
    "BAC", "XOM", "CVX", "ABBV", "LLY", "PEP", "KO", "MRK"
]

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'historical')

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path)

def download_historical_data(symbols: list, period: str = "10y", interval: str = "1d"):
    """
    使用 yfinance 批量下载历史日线数据。
    自动包含前复权价格 (Adj Close)，解决分红拆股导致的技术指标失真问题。
    """
    ensure_dir(DATA_DIR)
    
    logger.info(f"开始批量拉取 {len(symbols)} 只股票的 {period} 历史数据...")
    
    failed_symbols = []
    
    for symbol in symbols:
        try:
            logger.info(f"正在下载 {symbol} ...")
            ticker = yf.Ticker(symbol)
            # 拉取历史数据
            df = ticker.history(period=period, interval=interval)
            
            if df.empty:
                logger.warning(f"{symbol} 数据为空，跳过。")
                failed_symbols.append(symbol)
                continue
            
            # yfinance 的 history 默认返回的就是经过分红和拆股复权的开高低收数据
            # 我们将其格式化为策略引擎能直接使用的小写列名
            df = df.reset_index()
            df.columns = [col.lower() for col in df.columns]
            
            # 确保时间戳列存在并设为索引
            if 'date' in df.columns:
                df['timestamp'] = pd.to_datetime(df['date']).dt.tz_localize(None)
                df.set_index('timestamp', inplace=True)
                df.drop(columns=['date'], inplace=True)
            elif 'datetime' in df.columns:
                df['timestamp'] = pd.to_datetime(df['datetime']).dt.tz_localize(None)
                df.set_index('timestamp', inplace=True)
                df.drop(columns=['datetime'], inplace=True)
            
            # 仅保留 OHLCV 核心字段
            cols_to_keep = ['open', 'high', 'low', 'close', 'volume']
            df = df[[c for c in cols_to_keep if c in df.columns]]
            
            # 保存到本地 CSV
            file_path = os.path.join(DATA_DIR, f"{symbol}_daily.csv")
            df.to_csv(file_path)
            logger.info(f"[成功] {symbol} 数据已保存 -> {file_path} (共 {len(df)} 条)")
            
        except Exception as e:
            logger.error(f"[失败] 下载 {symbol} 发生错误: {str(e)}")
            failed_symbols.append(symbol)
            
    if failed_symbols:
        logger.warning(f"下载结束。以下股票获取失败: {failed_symbols}")
    else:
        logger.info("🎉 下载结束。所有股票历史数据获取成功！")
        logger.info(f"数据存放目录: {DATA_DIR}")

if __name__ == "__main__":
    download_historical_data(WATCHLIST, period="10y")
