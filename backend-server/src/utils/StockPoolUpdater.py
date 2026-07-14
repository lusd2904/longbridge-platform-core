#!/usr/bin/env python3
"""
股票池更新工具类
从large_cap_stocks表中获取股票，使用长桥SDK更新详细信息
"""

import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.longbridge import build_quote_context
from utils.DbUtil import DbUtil


class StockPoolUpdater:
    """股票池更新工具类"""

    def __init__(self):
        """初始化长桥客户端"""
        self.qc = build_quote_context()
        self.delay = 0.1

    def get_stocks_from_db(self):
        """从数据库中获取股票列表"""
        try:
            stocks = DbUtil.query_all("SELECT symbol FROM large_cap_stocks")
            return [stock[0] for stock in stocks]
        except Exception as e:
            print(f"❌ 从数据库获取股票失败: {e}")
            return []

    def get_stock_details(self, symbol):
        """获取单只股票的详细信息"""
        try:
            time.sleep(self.delay)

            static_info = self.qc.static_info([symbol])
            if not static_info or len(static_info) == 0:
                return None

            info = static_info[0]

            quote = self.qc.quote([symbol])
            current_price = None
            volume = None

            if quote and len(quote) > 0:
                stock_quote = quote[0]
                current_price = stock_quote.last_done
                volume = stock_quote.volume

            market_cap = None
            if current_price and info.total_shares:
                market_cap = float(current_price) * int(info.total_shares)

            pe_ratio = None
            if current_price and info.eps_ttm and info.eps_ttm > 0:
                pe_ratio = float(current_price) / float(info.eps_ttm)

            pb_ratio = None
            if current_price and info.bps and info.bps > 0:
                pb_ratio = float(current_price) / float(info.bps)

            return {
                "symbol": symbol,
                "company_name": info.name_en,
                "market": info.exchange,
                "market_cap": market_cap,
                "pe_ratio": pe_ratio,
                "pb_ratio": pb_ratio,
                "dividend_yield": info.dividend_yield,
                "eps": info.eps_ttm,
                "volume": volume,
            }
        except Exception as e:
            print(f"  {symbol} 获取失败: {e}")
            return None

    def get_stock_details_with_retry(self, symbol, max_retries=3):
        """获取单只股票的详细信息（带重试）"""
        retry_count = 0
        delay = 0.2

        while retry_count < max_retries:
            try:
                time.sleep(delay)

                static_info = self.qc.static_info([symbol])
                if not static_info or len(static_info) == 0:
                    return None

                info = static_info[0]

                quote = self.qc.quote([symbol])
                current_price = None
                volume = None

                if quote and len(quote) > 0:
                    stock_quote = quote[0]
                    current_price = stock_quote.last_done
                    volume = stock_quote.volume

                market_cap = None
                if current_price and info.total_shares:
                    market_cap = float(current_price) * int(info.total_shares)

                pe_ratio = None
                if current_price and info.eps_ttm and info.eps_ttm > 0:
                    pe_ratio = float(current_price) / float(info.eps_ttm)

                pb_ratio = None
                if current_price and info.bps and info.bps > 0:
                    pb_ratio = float(current_price) / float(info.bps)

                return {
                    "symbol": symbol,
                    "company_name": info.name_en,
                    "market": info.exchange,
                    "market_cap": market_cap,
                    "pe_ratio": pe_ratio,
                    "pb_ratio": pb_ratio,
                    "dividend_yield": info.dividend_yield,
                    "eps": info.eps_ttm,
                    "volume": volume,
                }

            except Exception as e:
                error_msg = str(e)
                retry_count += 1

                if "301606" in error_msg:
                    delay *= 2
                    print(f"  {symbol} 速率限制，等待 {delay:.1f} 秒后重试 ({retry_count}/{max_retries})")
                    time.sleep(delay)
                elif "301600" in error_msg:
                    return None
                elif retry_count < max_retries:
                    print(f"  {symbol} 错误: {e}，重试 ({retry_count}/{max_retries})")
                    time.sleep(delay)
                else:
                    print(f"  {symbol} 获取失败: {e}")
                    return None

        return None

    def update_stock(self, stock_details):
        """更新单只股票信息到数据库"""
        if not stock_details:
            return False

        try:
            update_sql = """
            UPDATE large_cap_stocks 
            SET company_name = %s, market = %s, market_cap = %s, 
                pe_ratio = %s, pb_ratio = %s, dividend_yield = %s, 
                eps = %s, volume = %s
            WHERE symbol = %s
            """
            params = (
                stock_details["company_name"],
                stock_details["market"],
                stock_details["market_cap"],
                stock_details["pe_ratio"],
                stock_details["pb_ratio"],
                stock_details["dividend_yield"],
                stock_details["eps"],
                stock_details["volume"],
                stock_details["symbol"],
            )
            DbUtil.execute_sql(update_sql, params)
            return True
        except Exception as e:
            print(f"  更新 {stock_details['symbol']} 失败: {e}")
            return False

    def update_all_stocks(self):
        """更新所有股票信息"""
        print("🚀 开始更新股票池...\n")

        print("📊 正在获取股票列表...")
        stocks = self.get_stocks_from_db()
        total = len(stocks)
        print(f"✅ 共 {total} 只股票\n")

        success_count = 0
        fail_count = 0

        for i, symbol in enumerate(stocks, 1):
            print(f"[{i}/{total}] {symbol}...", end=" ")

            details = self.get_stock_details_with_retry(symbol)

            if details:
                if self.update_stock(details):
                    print("✅ 更新成功")
                    success_count += 1
                else:
                    print("❌ 更新失败")
                    fail_count += 1
            else:
                print("❌ 获取失败")
                fail_count += 1

            if i % 50 == 0:
                print(f"\n📊 进度: 已处理 {i}/{total} 只股票")
                print(f"  成功: {success_count}, 失败: {fail_count}")
                time.sleep(2)

        print(f"\n{'='*60}")
        print("✅ 更新完成！")
        print(f"{'='*60}")
        print(f"📊 成功: {success_count} 只股票")
        print(f"📊 失败: {fail_count} 只股票")
        print(f"📊 成功率: {success_count/total*100:.1f}%")

        return {"success": success_count, "failed": fail_count, "total": total}

    def write_to_stocks_file(self, stocks=None):
        """将股票列表写入stocks.txt文件"""
        if stocks is None:
            stocks = self.get_stocks_from_db()

        try:
            with open("stocks.txt", "w", encoding="utf-8") as f:
                f.write("# 股票池\n")
                for stock in stocks:
                    f.write(f"{stock}\n")
            print(f"✅ 成功写入 {len(stocks)} 只股票到 stocks.txt")
        except Exception as e:
            print(f"❌ 写入 stocks.txt 失败: {e}")

    def update_and_write(self):
        """更新股票池并写入文件"""
        print("🚀 开始更新股票池并写入文件...\n")

        result = self.update_all_stocks()

        print("\n📁 正在写入stocks.txt文件...")
        self.write_to_stocks_file()

        return result

    def close(self):
        """关闭连接"""
        if hasattr(self.qc, "close"):
            self.qc.close()
