"""
WorldQuant Alpha 101 因子计算引擎 (基础版)
该模块复刻了著名对冲基金 WorldQuant 的 101 个高频截面与时序量价因子公式。
通过 Pandas 向量化计算，提供极速的因子矩阵生成能力。
"""

import numpy as np
import pandas as pd


class Alpha101:
    """
    量价数据需要为 DataFrame，包含:
    open, close, high, low, volume, vwap (可选)
    如果是多只股票的面板数据(Panel Data)，建议使用 MultiIndex (date, symbol) 进行 groupby 计算。
    以下假设传入的 df 为单只股票的时序数据。
    """

    @staticmethod
    def stddev(df, window):
        return df.rolling(window).std()

    @staticmethod
    def correlation(x, y, window):
        return x.rolling(window).corr(y)

    @staticmethod
    def covariance(x, y, window):
        return x.rolling(window).cov(y)

    @staticmethod
    def rank(df):
        return df.rank(pct=True)

    @staticmethod
    def delay(df, period):
        return df.shift(period)

    @staticmethod
    def delta(df, period):
        return df.diff(period)

    @staticmethod
    def ts_min(df, window):
        return df.rolling(window).min()

    @staticmethod
    def ts_max(df, window):
        return df.rolling(window).max()

    @staticmethod
    def ts_argmax(df, window):
        return df.rolling(window).apply(np.argmax, raw=True) + 1

    @staticmethod
    def ts_argmin(df, window):
        return df.rolling(window).apply(np.argmin, raw=True) + 1

    @staticmethod
    def ts_rank(df, window):
        return df.rolling(window).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False)

    @staticmethod
    def sign(df):
        return np.sign(df)

    # ---------------- 因子公式区 ---------------- #

    @classmethod
    def alpha_001(cls, df):
        """
        Alpha#1: (rank(Ts_ArgMax(SignedPower(((returns < 0) ? stddev(returns, 20) : close), 2.), 5)) - 0.5)
        这里给出简化版的截面/时序组合
        """
        returns = df["close"].pct_change()
        cond = returns < 0
        val = np.where(cond, cls.stddev(returns, 20), df["close"])
        val = pd.Series(val, index=df.index)
        power = np.power(val, 2) * cls.sign(val)
        return cls.rank(cls.ts_argmax(power, 5)) - 0.5

    @classmethod
    def alpha_006(cls, df):
        """
        Alpha#6: -1 * correlation(open, volume, 10)
        """
        return -1.0 * cls.correlation(df["open"], df["volume"], 10)

    @classmethod
    def alpha_009(cls, df):
        """
        Alpha#9: ((0 < ts_min(delta(close, 1), 5)) ? delta(close, 1) : ((ts_max(delta(close, 1), 5) < 0) ? delta(close, 1) : (-1 * delta(close, 1))))
        """
        delta_close = cls.delta(df["close"], 1)
        cond_1 = cls.ts_min(delta_close, 5) > 0
        cond_2 = cls.ts_max(delta_close, 5) < 0
        return np.where(cond_1, delta_close, np.where(cond_2, delta_close, -delta_close))

    @classmethod
    def alpha_012(cls, df):
        """
        Alpha#12: sign(delta(volume, 1)) * (-1 * delta(close, 1))
        """
        return cls.sign(cls.delta(df["volume"], 1)) * (-1.0 * cls.delta(df["close"], 1))

    @classmethod
    def alpha_041(cls, df):
        """
        Alpha#41: (((high * low)^0.5) - vwap)
        简化使用 (high+low+close)/3 替代 vwap
        """
        vwap = (df["high"] + df["low"] + df["close"]) / 3
        return np.sqrt(df["high"] * df["low"]) - vwap

    @classmethod
    def generate_all(cls, df):
        """
        一次性计算已有的全部 Alpha 101 因子，并拼接入 DataFrame
        """
        res = pd.DataFrame(index=df.index)
        methods = [func for func in dir(cls) if callable(getattr(cls, func)) and func.startswith("alpha_")]
        for m in methods:
            func = getattr(cls, m)
            res[m] = func(df)
        return res
