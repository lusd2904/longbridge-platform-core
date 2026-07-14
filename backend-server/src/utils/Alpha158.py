"""
Microsoft Qlib Alpha 158 核心时序衍生算法 (基础版)
该模块实现了微软亚洲研究院(MSRA)提出的经典 AI 训练特征集 Alpha 158 算法框架。
通过基础的日线价格，按多维度(长中短)时间窗口衍生出超过 158 个时序截面特征。
"""

import numpy as np
import pandas as pd


class Alpha158:
    """
    量价数据需要为 DataFrame，包含:
    open, close, high, low, volume, vwap
    窗口值 (Windows) 通常为 [5, 10, 20, 30, 60] 代表一周、半月、一月、两月、一季
    """

    WINDOWS = [5, 10, 20, 30, 60]

    @staticmethod
    def _roc(df_col, window):
        """变动率 Return Over Window"""
        return df_col.pct_change(window)

    @staticmethod
    def _ma(df_col, window):
        """简单均线 Moving Average"""
        return df_col.rolling(window).mean()

    @staticmethod
    def _std(df_col, window):
        """标准差 Volatility"""
        return df_col.rolling(window).std()

    @staticmethod
    def _beta(series_y, series_x, window):
        """回归系数 Beta"""
        cov = series_y.rolling(window).cov(series_x)
        var = series_x.rolling(window).var()
        return cov / var

    @staticmethod
    def _rsq(series_y, series_x, window):
        """回归拟合度 R-Square"""
        corr = series_y.rolling(window).corr(series_x)
        return corr**2

    @staticmethod
    def _resi(series_y, series_x, window):
        """回归残差 Residual"""
        beta = Alpha158._beta(series_y, series_x, window)
        alpha = series_y.rolling(window).mean() - beta * series_x.rolling(window).mean()
        return series_y - (beta * series_x + alpha)

    @staticmethod
    def _max(df_col, window):
        """区间最高 High over Window"""
        return df_col.rolling(window).max()

    @staticmethod
    def _min(df_col, window):
        """区间最低 Low over Window"""
        return df_col.rolling(window).min()

    @staticmethod
    def _qtl(df_col, window, q):
        """区间分位数 Quantile"""
        return df_col.rolling(window).quantile(q)

    @classmethod
    def generate_all(cls, df):
        """
        全量衍生 Alpha 158 特征矩阵。
        它会将原始几列数据扩充出上百个维度，适合于 LightGBM, XGBoost 等树模型的直接训练。
        """
        features = pd.DataFrame(index=df.index)

        # 1. 基础 K 线特征 (KBAR) - 描述日内振幅、实体长度
        features["KMID"] = (df["close"] - df["open"]) / df["open"]
        features["KLEN"] = (df["high"] - df["low"]) / df["open"]
        features["KMID2"] = (df["close"] - df["open"]) / (df["high"] - df["low"] + 1e-12)
        features["KUP"] = (df["high"] - np.maximum(df["open"], df["close"])) / df["open"]
        features["KDOWN"] = (np.minimum(df["open"], df["close"]) - df["low"]) / df["open"]

        # 针对每个窗口周期生成衍生指标
        for w in cls.WINDOWS:
            # 2. 动量特征 (ROC)
            features[f"ROC{w}"] = cls._roc(df["close"], w)

            # 3. 价格与均线的偏离度 (MA Ratio)
            features[f"MA{w}"] = cls._ma(df["close"], w)
            features[f"VMA{w}"] = cls._ma(df["volume"], w)

            # (均线交叉偏离)
            if f"MA{w}" in features:
                features[f"PRICE_TO_MA{w}"] = df["close"] / features[f"MA{w}"]

            # 4. 波动率与风险特征 (STD)
            features[f"STD{w}"] = cls._std(df["close"], w)

            # 5. 区间极值与位置特征 (MAX/MIN Range)
            max_p = cls._max(df["high"], w)
            min_p = cls._min(df["low"], w)
            features[f"MAX{w}"] = max_p
            features[f"MIN{w}"] = min_p
            features[f"QTLU{w}"] = cls._qtl(df["close"], w, 0.8)
            features[f"QTLD{w}"] = cls._qtl(df["close"], w, 0.2)

            # 当前价在区间中的相对位置
            features[f"RSV{w}"] = (df["close"] - min_p) / (max_p - min_p + 1e-12)

            # 6. 量价相关性 (CORR)
            features[f"CORR{w}"] = df["close"].rolling(w).corr(df["volume"])

            # 7. 量价协方差 (COV)
            features[f"COV{w}"] = df["close"].rolling(w).cov(df["volume"])

            # 8. (如果存在市场基准或 VWAP) 可以拓展 BETA, RSQ 等
            # 这里默认 df 包含 vwap
            if "vwap" in df.columns:
                features[f"BETA{w}"] = cls._beta(df["close"], df["vwap"], w)
                features[f"RESI{w}"] = cls._resi(df["close"], df["vwap"], w)

        return features
