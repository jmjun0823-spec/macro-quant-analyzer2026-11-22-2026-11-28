import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pytest

from src.analyzer_thanksgiving import get_thanksgiving_dates, analyze_thanksgiving_anomaly
from src.analyzer_year_end import analyze_year_end_rotation
from src.analyzer_macro_fx import analyze_macro_and_fx_sensitivity
from src.quant_allocation import simulate_tactical_allocation


def test_thanksgiving_dates_known_years():
    dates = get_thanksgiving_dates([2024, 2025, 2026])
    assert [str(d.date()) for d in dates] == ["2024-11-28", "2025-11-27", "2026-11-26"]


def test_thanksgiving_fixed_volume_drop_exact_calculation():
    dates = pd.bdate_range("2026-10-20", "2026-12-04")
    n = len(dates)
    close = np.linspace(100.0, 100.0 + n - 1, n)
    volume = np.full(n, 1000.0)

    tg_week_mask = (dates >= pd.Timestamp("2026-11-23")) & (dates <= pd.Timestamp("2026-11-27"))
    volume[tg_week_mask] = 500.0

    df = pd.DataFrame(
        {
            "Close": close,
            "Volume": volume,
            "Return": pd.Series(close, index=dates).pct_change().fillna(0.0),
        },
        index=dates,
    )

    out = analyze_thanksgiving_anomaly(df, lookback_days=20)
    assert out["tg_week_avg_vol_change_pct"] == pytest.approx(-50.0, abs=1e-6)
    assert out["volume_drop_t_stat"] < 0


def test_empty_dataframe_handling():
    empty_df = pd.DataFrame(columns=["Close", "Volume", "Return"])
    tg_out = analyze_thanksgiving_anomaly(empty_df, lookback_days=5)
    assert tg_out["yearly_series"]["years"] == []
    assert tg_out["tg_week_avg_vol_change_pct"] is None

    ye_out = analyze_year_end_rotation(empty_df, empty_df, pd.DataFrame())
    assert ye_out["avg_kospi_ret_pct"] is None

    macro_out = analyze_macro_and_fx_sensitivity({}, {"fx_ma_window": 20})
    assert macro_out["obs_count"] == 0


def test_year_end_holiday_gap_and_fixed_spread():
    raw_dates = pd.to_datetime([
        "2025-11-18", "2025-11-19", "2025-11-20", "2025-11-24",
        "2025-12-01", "2025-12-10", "2025-12-18", "2025-12-26",
    ])
    kospi_vals = [190.0, 195.0, 200.0, 202.0, 205.0, 210.0, 215.0, 220.0]
    kosdaq_vals = [105.0, 102.0, 100.0, 99.0, 98.0, 97.0, 96.0, 95.0]

    kospi_df = pd.DataFrame({"Close": kospi_vals}, index=raw_dates)
    kosdaq_df = pd.DataFrame({"Close": kosdaq_vals}, index=raw_dates)

    out = analyze_year_end_rotation(kospi_df, kosdaq_df, pd.DataFrame(), start_mmdd="11-20", end_mmdd="12-26")
    assert out["avg_kospi_ret_pct"] == pytest.approx(10.0, abs=1e-6)
    assert out["avg_kosdaq_ret_pct"] == pytest.approx(-5.0, abs=1e-6)
    assert out["avg_kospi_minus_kosdaq_pct"] == pytest.approx(15.0, abs=1e-6)


def test_signal_lag_prevents_lookahead_bias():
    dates = pd.bdate_range("2025-01-01", periods=25)
    fx = np.array([1000.0] * 20 + [1200.0] * 5)

    kospi_ret = np.zeros(25)
    sox_ret = np.zeros(25)
    kospi_ret[20] = 0.10
    sox_ret[20] = 0.10
    kospi_ret[21] = 0.10
    sox_ret[21] = 0.10

    data = {
        "KOSPI": pd.DataFrame({"Return": kospi_ret}, index=dates),
        "SOX": pd.DataFrame({"Return": sox_ret}, index=dates),
        "USDKRW": pd.DataFrame({"Close": fx}, index=dates),
    }
    params = {
        "fx_ma_window": 20,
        "high_fx_weight": 0.4,
        "low_fx_weight": 0.9,
        "trading_days_per_year": 252,
        "random_seed": 42,
    }

    res = simulate_tactical_allocation(data, params)
    assert res["tactical_fx_regime"]["ann_volatility_pct"] is not None
    assert res["tactical_fx_regime"]["ann_volatility_pct"] > 0
