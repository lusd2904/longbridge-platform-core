"""Characterization (golden-master) tests for the technical-indicator layer.

These indicators (RSI/MACD/BOLL/ATR/EMA/SMA/KDJ/OBV/ROC/CCI/support-resistance)
feed the audited watchlist scan -> AI analysis -> paper-trade pipeline via
``core.analysis.IndicatorSnapshotService`` and ``core.account.StockScanner``.
Until now they had no regression coverage.

The point of these tests is NOT to assert the indicators are "correct" in an
absolute sense -- it is to lock their *current* numeric behaviour so any future
change (e.g. swapping in a third-party quant library such as pandas-ta/TA-Lib)
is forced to prove, value by value, exactly how the outputs drift before it can
land. The golden values below were captured from the live implementation on the
deterministic series built in ``_series()``.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend-server" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from utils.IndicatorUtil import IndicatorUtil  # noqa: E402
from utils.IndicatorUtilEnhanced import IndicatorUtilEnhanced as Enhanced  # noqa: E402

# Tolerance: golden values are rounded to 6 dp, so anything tighter than the
# rounding step still catches a genuine algorithmic drift.
TOL = 5e-6


def _series(n: int = 120):
    """Deterministic OHLCV series -- no RNG, identical on every machine."""
    prices, highs, lows, volumes = [], [], [], []
    for i in range(n):
        base = 100 + 10 * math.sin(i / 9.0) + i * 0.15
        prices.append(round(base, 4))
        highs.append(round(base + 1.5 + 0.5 * math.cos(i / 5.0), 4))
        lows.append(round(base - 1.5 - 0.5 * math.sin(i / 7.0), 4))
        volumes.append(1000 + (i * 37 % 500))
    return prices, highs, lows, volumes


@pytest.fixture(scope="module")
def data():
    return _series()


def test_rsi_golden(data):
    prices, *_ = data
    assert IndicatorUtil.calculate_rsi(prices) == pytest.approx(88.968223, abs=TOL)


def test_boll_golden(data):
    prices, *_ = data
    mid, upper, lower = IndicatorUtil.calculate_boll(prices)
    assert mid == pytest.approx(113.28465, abs=TOL)
    assert upper == pytest.approx(125.515339, abs=TOL)
    assert lower == pytest.approx(101.053961, abs=TOL)
    # Structural invariant the downstream code relies on.
    assert lower <= mid <= upper


def test_macd_golden(data):
    prices, *_ = data
    diff, dea, hist = IndicatorUtil.calculate_macd(prices)
    assert diff == pytest.approx(3.504154, abs=TOL)
    assert dea == pytest.approx(2.08684, abs=TOL)
    assert hist == pytest.approx(2.834627, abs=TOL)


def test_enhanced_golden(data):
    prices, highs, lows, volumes = data
    assert Enhanced.calculate_atr(prices, highs, lows) == pytest.approx(2.831548, abs=TOL)
    assert Enhanced.calculate_ema(prices, 12) == pytest.approx(118.046526, abs=TOL)
    assert Enhanced.calculate_ema(prices, 26) == pytest.approx(114.542647, abs=TOL)
    assert Enhanced.calculate_sma(prices, 20) == pytest.approx(113.28465, abs=TOL)
    assert Enhanced.calculate_sma(prices, 60) == pytest.approx(113.709053, abs=TOL)
    k, d, j = Enhanced.calculate_kdj(prices, highs, lows)
    assert (k, d, j) == pytest.approx((98.290509, 99.036063, 96.799402), abs=TOL)
    assert Enhanced.calculate_obv(prices, volumes) == pytest.approx(17844.0, abs=TOL)
    assert Enhanced.calculate_roc(prices) == pytest.approx(12.904337, abs=TOL)
    assert Enhanced.calculate_cci(prices, highs, lows) == pytest.approx(133.213973, abs=TOL)


def test_macd_seed_is_stable_on_long_history(data):
    """The EMA-seed choice in calculate_macd is known to only matter for short
    series; on the 520-760 bar histories the platform actually loads it is
    numerically inert. Lock that property so a future refactor that "fixes" the
    seed cannot silently shift the values the platform consumes."""
    prices, *_ = data

    def sma_seeded_macd(px, fast=12, slow=26, signal=9):
        import numpy as np

        def ema(x, n):
            x = np.asarray(x, float)
            k = 2 / (n + 1)
            out = np.empty_like(x)
            out[: n - 1] = np.nan
            out[n - 1] = x[:n].mean()
            for i in range(n, len(x)):
                out[i] = (x[i] - out[i - 1]) * k + out[i - 1]
            return out

        s = np.asarray(px, float)
        dif = ema(s, fast) - ema(s, slow)
        valid = dif[~np.isnan(dif)]
        dea = ema(valid, signal)
        return float(dif[-1]), float(dea[-1])

    cur_diff, cur_dea, _ = IndicatorUtil.calculate_macd(prices)
    ref_diff, ref_dea = sma_seeded_macd(prices)
    # 120 bars already drives the seed difference well under 0.01 in DIF.
    assert cur_diff == pytest.approx(ref_diff, abs=0.01)
    assert cur_dea == pytest.approx(ref_dea, abs=0.01)


def test_insufficient_data_returns_neutral_defaults():
    short = [10.0, 11.0, 10.5]
    assert IndicatorUtil.calculate_rsi(short) == 50.0
    mid, upper, lower = IndicatorUtil.calculate_boll(short)
    assert mid == upper == lower == short[-1]
    diff, dea, hist = IndicatorUtil.calculate_macd(short)
    assert all(isinstance(v, float) for v in (diff, dea, hist))


def test_support_resistance_current_behaviour(data):
    """Locks the *current* frequency-cluster support/resistance output. NOTE:
    this implementation can return support > resistance because it derives the
    levels from price-frequency, not price magnitude -- captured here as-is so
    the behaviour is visible and protected, not silently changed."""
    prices, *_ = data
    support, resistance = Enhanced.calculate_support_resistance(prices)
    assert support == pytest.approx(123.95, abs=TOL)
    assert resistance == pytest.approx(105.07, abs=TOL)
