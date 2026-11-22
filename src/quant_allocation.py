import numpy as np
import pandas as pd


def compute_risk_and_volatility_drag(returns: pd.Series, ann_factor: float = 252.0) -> dict:
    """
    수익률 시계열의 연환산 수익률, 변동성, Volatility Drag(0.5 * sigma^2),
    95% Historical VaR 및 CVaR(Expected Shortfall) 계산
    """
    r = returns.dropna()
    if r.empty:
        return {
            "ann_return_pct": None,
            "ann_volatility_pct": None,
            "ann_volatility_drag_pct": None,
            "daily_var_95_pct": None,
            "daily_cvar_95_pct": None,
        }
    ann_ret = float(r.mean() * ann_factor)
    ann_vol = float(r.std(ddof=1) * np.sqrt(ann_factor)) if len(r) > 1 else 0.0
    vol_drag = float(0.5 * (ann_vol ** 2))
    var_95 = float(np.percentile(r, 5))
    tail = r[r <= var_95]
    cvar_95 = float(tail.mean()) if len(tail) > 0 else var_95

    return {
        "ann_return_pct": round(ann_ret * 100, 2),
        "ann_volatility_pct": round(ann_vol * 100, 2),
        "ann_volatility_drag_pct": round(vol_drag * 100, 2),
        "daily_var_95_pct": round(var_95 * 100, 2),
        "daily_cvar_95_pct": round(cvar_95 * 100, 2),
    }


def simulate_tactical_allocation(data: dict, params: dict) -> dict:
    """
    환율 상단 압력 vs 하락 반전/안정 국면에 따른 전술적 비중 배분 시뮬레이션
    전일 종가 기준 시그널을 익일 수익률에 반영(shift(1))하여 룩어헤드 방지[cite: 3]
    """
    seed = int(params.get("random_seed", 42))
    rng = np.random.default_rng(seed)
    _ = rng.normal(0, 1, 10)

    ann_factor = float(params.get("trading_days_per_year", 252))
    fx_ma_win = int(params.get("fx_ma_window", 20))
    high_fx_w = float(params.get("high_fx_weight", 0.4))
    low_fx_w = float(params.get("low_fx_weight", 0.9))

    kospi_ret = data.get("KOSPI", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    sox_ret = data.get("SOX", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    usdkrw_close = data.get("USDKRW", pd.DataFrame()).get("Close", pd.Series(dtype=float))

    # KOSPI는 필수, SOX가 비어 있으면 KOSPI 100%로 대체해 휴장일/결측 손실 최소화[cite: 3]
    df = pd.DataFrame({
        "KOSPI": kospi_ret,
        "SOX": sox_ret.reindex(kospi_ret.index),
        "USDKRW": usdkrw_close.reindex(kospi_ret.index),
    }).dropna(subset=["KOSPI", "USDKRW"])

    if df.empty:
        empty_metrics = compute_risk_and_volatility_drag(pd.Series(dtype=float), ann_factor)
        return {
            "benchmark_risk_70_30": empty_metrics,
            "tactical_fx_regime": empty_metrics,
        }

    df["Risk_Asset"] = np.where(
        df["SOX"].notna(),
        0.7 * df["KOSPI"] + 0.3 * df["SOX"].fillna(0.0),
        df["KOSPI"],
    )
    df["FX_MA"] = df["USDKRW"].rolling(fx_ma_win).mean()

    raw_weight = pd.Series(
        np.where(df["USDKRW"] > df["FX_MA"], high_fx_w, low_fx_w),
        index=df.index,
    )
    # 전일 종가 기준 확정 시그널만 당일 수익률에 곱함 (첫 관측치 및 MA 미형성 구간 제외)[cite: 3]
    effective_weight = raw_weight.shift(1)
    valid_mask = df["FX_MA"].notna() & effective_weight.notna()

    bench_series = df.loc[valid_mask, "Risk_Asset"]
    tactical_series = effective_weight.loc[valid_mask] * bench_series

    return {
        "benchmark_risk_70_30": compute_risk_and_volatility_drag(bench_series, ann_factor),
        "tactical_fx_regime": compute_risk_and_volatility_drag(tactical_series, ann_factor),
    }
