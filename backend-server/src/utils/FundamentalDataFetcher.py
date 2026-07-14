import logging
import yfinance as yf
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class FundamentalDataFetcher:
    """基本面数据抓取与缓存类 (基于 OpenBB 核心数据源 yfinance)"""
    
    def __init__(self):
        self._cache = {}
        logger.info("FundamentalDataFetcher initialized with yfinance API.")

    def get_fundamentals(self, symbol: str) -> Dict[str, float]:
        """
        获取指定股票的基本面指标 (实盘数据)
        """
        if symbol in self._cache:
            return self._cache[symbol]

        default_data = {'pe': 999.0, 'pb': 99.0, 'roe': -9.9, 'market_cap': 0}
        
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            
            pe = info.get("trailingPE", info.get("forwardPE", default_data['pe']))
            pb = info.get("priceToBook", default_data['pb'])
            roe = info.get("returnOnEquity", default_data['roe'])
            market_cap = info.get("marketCap", default_data['market_cap'])
            
            # yfinance 的 ROE 返回的是小数（如 0.35），如果没有返回则维持默认负数
            real_data = {
                'pe': float(pe) if pe is not None else 999.0,
                'pb': float(pb) if pb is not None else 99.0,
                'roe': float(roe) if roe is not None else -9.9,
                'market_cap': float(market_cap) if market_cap is not None else 0.0
            }
            
            self._cache[symbol] = real_data
            logger.info(f"成功拉取 {symbol} 真实财务数据: {real_data}")
            return real_data
            
        except Exception as e:
            logger.error(f"拉取 {symbol} 基本面数据失败: {str(e)}")
            return default_data

    def filter_universe(self, symbols: list, min_roe: float = 0.05, max_pe: float = 50.0) -> list:
        """
        根据基本面条件过滤股票池 (防雷机制)
        """
        good_stocks = []
        for sym in symbols:
            f = self.get_fundamentals(sym)
            if f['roe'] >= min_roe and f['pe'] <= max_pe:
                good_stocks.append(sym)
            else:
                logger.info(f"股票 {sym} 被基本面过滤排除 (ROE: {f['roe']:.2f}, PE: {f['pe']:.2f})")
                
        return good_stocks

fundamental_fetcher = FundamentalDataFetcher()
