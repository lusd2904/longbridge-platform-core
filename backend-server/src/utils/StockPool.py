import os

from utils.DbUtil import DbUtil


class StockPool:
    @staticmethod
    def get_us_pool():
        """
        获取美股标的：从large_cap_stocks和us_etf两个表获取
        """
        all_stocks = []

        # 从large_cap_stocks获取大盘股
        try:
            # 获取所有以.US结尾或market='US'的股票
            stocks = DbUtil.query_all("SELECT symbol FROM large_cap_stocks WHERE symbol LIKE '%.US' OR market = 'US'")
            large_cap = [stock[0] for stock in stocks]
            print(f"✅ 从large_cap_stocks获取到 {len(large_cap)} 只美股")
            all_stocks.extend(large_cap)
        except Exception as e:
            print(f"❌ 从large_cap_stocks获取失败: {e}")

        # 从us_etf获取ETF
        try:
            etfs = DbUtil.query_all("SELECT symbol FROM us_etf")
            etf_list = [etf[0] for etf in etfs]
            print(f"✅ 从us_etf获取到 {len(etf_list)} 只ETF")
            all_stocks.extend(etf_list)
        except Exception as e:
            print(f"❌ 从us_etf获取失败: {e}")

        # 去重
        all_stocks = list(set(all_stocks))

        if all_stocks:
            print(f"✅ 美股股票池共 {len(all_stocks)} 只")
            return all_stocks

        # 数据库无数据，从文本文件获取
        print("⚠️ 数据库中无美股数据，从stocks.txt获取")
        return StockPool._get_from_file()

    @staticmethod
    def get_cn_pool():
        """
        获取A股标的：从cn_stocks表获取
        """
        try:
            # 从cn_stocks表获取A股
            stocks = DbUtil.query_all("SELECT symbol FROM cn_stocks")
            cn_stocks = [stock[0] for stock in stocks]
            if cn_stocks:
                print(f"✅ 从cn_stocks获取到 {len(cn_stocks)} 只A股")
                return cn_stocks
        except Exception as e:
            print(f"❌ 从cn_stocks获取失败: {e}")

        # 如果cn_stocks表不存在或没有数据，从large_cap_stocks获取
        try:
            stocks = DbUtil.query_all("SELECT symbol FROM large_cap_stocks WHERE market = 'CN'")
            cn_stocks = [stock[0] for stock in stocks]
            if cn_stocks:
                print(f"✅ 从large_cap_stocks获取到 {len(cn_stocks)} 只A股")
                return cn_stocks
        except Exception as e:
            print(f"❌ 从large_cap_stocks获取A股失败: {e}")

        # 如果数据库没有数据，返回默认的A股列表
        print("⚠️ 数据库中无A股数据，返回默认列表")
        return [
            "300017.SZ",  # 网宿科技
            "301590.SZ",  # 优优绿能
        ]

    @staticmethod
    def get_stocks_from_db(market="US"):
        """
        从MySQL数据库中获取指定市场的股票（兼容旧接口）

        Args:
            market: 'US' 或 'CN'
        """
        if market == "US":
            return StockPool.get_us_pool()
        else:
            return StockPool.get_cn_pool()

    @staticmethod
    def get_all_stocks_from_db():
        """
        从MySQL数据库中获取所有股票（包括美股和A股）
        """
        all_stocks = []

        # 获取美股
        try:
            # 获取所有以.US结尾或market='US'的股票
            stocks = DbUtil.query_all(
                "SELECT symbol, company_name, market FROM large_cap_stocks WHERE symbol LIKE '%.US' OR market = 'US' ORDER BY symbol"
            )
            for stock in stocks:
                all_stocks.append({"symbol": stock[0], "name": stock[1], "market": stock[2] if stock[2] else "US"})
        except Exception as e:
            print(f"❌ 从large_cap_stocks获取美股失败: {e}")

        # 获取ETF
        try:
            # 先检查us_etf表的列结构
            etfs = DbUtil.query_all("SELECT symbol FROM us_etf ORDER BY symbol")
            for etf in etfs:
                all_stocks.append(
                    {
                        "symbol": etf[0],
                        "name": etf[0],  # ETF使用代码作为名称
                        "market": "US",
                    }
                )
        except Exception as e:
            print(f"❌ 从us_etf获取ETF失败: {e}")

        # 获取A股
        try:
            stocks = DbUtil.query_all("SELECT symbol, name, 'CN' as market FROM cn_stocks ORDER BY symbol")
            for stock in stocks:
                all_stocks.append({"symbol": stock[0], "name": stock[1], "market": stock[2]})
        except Exception:
            # 如果cn_stocks表不存在，从large_cap_stocks获取
            try:
                # 获取所有以.SZ或.SH结尾的股票
                stocks = DbUtil.query_all(
                    "SELECT symbol, company_name, market FROM large_cap_stocks WHERE symbol LIKE '%.SZ' OR symbol LIKE '%.SH' OR market = 'CN' ORDER BY symbol"
                )
                for stock in stocks:
                    all_stocks.append({"symbol": stock[0], "name": stock[1], "market": stock[2] if stock[2] else "CN"})
            except Exception as e2:
                print(f"❌ 获取A股失败: {e2}")

        return all_stocks

    @staticmethod
    def initialize_stock_pool(qc):
        """
        初始化股票池：确保数据库表存在
        """
        # 创建数据库表
        StockPool._create_stock_tables()

        # 初始化A股数据
        StockPool._init_cn_stocks()

        # 从数据库中获取美股列表
        stocks = StockPool.get_us_pool()

        # 如果数据库中有股票，写入到stocks.txt文件，以便当前系统使用
        if stocks:
            StockPool._write_to_stocks_file(stocks)
            print(f"✅ 从数据库中获取到 {len(stocks)} 只美股")
        else:
            print("⚠️ 数据库中没有美股数据")

        return stocks

    @staticmethod
    def _init_cn_stocks():
        """
        初始化A股股票数据
        """
        try:
            # 检查cn_stocks表是否存在
            try:
                existing = DbUtil.query_all("SELECT COUNT(*) FROM cn_stocks")
                if existing and existing[0][0] > 0:
                    print(f"✅ cn_stocks表中已有 {existing[0][0]} 只A股数据")
                    return
            except:
                # 表不存在，创建表
                pass

            # 检查large_cap_stocks中是否有A股数据
            existing = DbUtil.query_all("SELECT COUNT(*) FROM large_cap_stocks WHERE market = 'CN'")
            if existing and existing[0][0] > 0:
                print(f"✅ large_cap_stocks表中已有 {existing[0][0]} 只A股数据")
                return

            # 添加默认A股股票
            cn_stocks = [
                ("300017.SZ", "网宿科技", "CN"),
                ("301590.SZ", "优优绿能", "CN"),
            ]

            sql = """
            INSERT INTO large_cap_stocks (symbol, company_name, market) 
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE company_name = VALUES(company_name), market = VALUES(market)
            """

            for stock in cn_stocks:
                DbUtil.execute_sql(sql, stock)

            print(f"✅ 成功初始化 {len(cn_stocks)} 只A股数据")
        except Exception as e:
            print(f"❌ 初始化A股数据失败: {e}")

    @staticmethod
    def _create_stock_tables():
        """
        创建股票表
        """
        try:
            # 创建large_cap_stocks表
            sql = """
            CREATE TABLE IF NOT EXISTS large_cap_stocks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                company_name VARCHAR(100) DEFAULT NULL,
                market VARCHAR(10) DEFAULT 'US',
                market_cap DECIMAL(20,2) DEFAULT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
            DbUtil.execute_sql(sql)
            print("✅ 成功创建large_cap_stocks表")

            # 创建us_etf表
            sql = """
            CREATE TABLE IF NOT EXISTS us_etf (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(100) DEFAULT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
            DbUtil.execute_sql(sql)
            print("✅ 成功创建us_etf表")

            # 创建cn_stocks表
            sql = """
            CREATE TABLE IF NOT EXISTS cn_stocks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                symbol VARCHAR(20) NOT NULL UNIQUE,
                name VARCHAR(100) DEFAULT NULL,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
            """
            DbUtil.execute_sql(sql)
            print("✅ 成功创建cn_stocks表")

        except Exception as e:
            print(f"❌ 创建股票表失败: {e}")

    @staticmethod
    def get_stock_name(symbol):
        """
        获取股票名称
        """
        try:
            # 先从large_cap_stocks查找
            result = DbUtil.query_all("SELECT company_name FROM large_cap_stocks WHERE symbol = %s", (symbol,))
            if result and result[0][0]:
                return result[0][0]

            # 再从us_etf查找
            result = DbUtil.query_all("SELECT etf_name FROM us_etf WHERE symbol = %s", (symbol,))
            if result and result[0][0]:
                return result[0][0]

            # 再从cn_stocks查找
            result = DbUtil.query_all("SELECT name FROM cn_stocks WHERE symbol = %s", (symbol,))
            if result and result[0][0]:
                return result[0][0]

            return None
        except Exception as e:
            print(f"❌ 获取股票名称失败: {e}")
            return None

    @staticmethod
    def _get_from_file():
        """
        从文本文件获取股票列表
        """
        file_path = "stocks.txt"
        pool = []

        if not os.path.exists(file_path):
            print(f"❌ 错误：在 {os.getcwd()} 下未找到 {file_path}")
            return []

        try:
            with open(file_path, encoding="utf-8") as f:
                for line in f:
                    symbol = line.strip()
                    if symbol and not symbol.startswith("#"):
                        # 自动补全 .US 后缀（如果文件中没有的话）
                        if not symbol.endswith(".US"):
                            symbol = f"{symbol}.US"
                        pool.append(symbol.upper())
            print(f"✅ 从stocks.txt获取到 {len(pool)} 只美股")
            return pool
        except Exception as e:
            print(f"❌ 读取 stocks.txt 失败: {e}")
            return []

    @staticmethod
    def _write_to_stocks_file(stocks):
        """
        将股票列表写入到stocks.txt文件
        """
        try:
            with open("stocks.txt", "w", encoding="utf-8") as f:
                f.write("# 市值大于80亿的纳斯达克和纽交所股票\n")
                for stock in stocks:
                    f.write(f"{stock}\n")
            print(f"✅ 成功写入 {len(stocks)} 只股票到 stocks.txt")
        except Exception as e:
            print(f"❌ 写入 stocks.txt 失败: {e}")
