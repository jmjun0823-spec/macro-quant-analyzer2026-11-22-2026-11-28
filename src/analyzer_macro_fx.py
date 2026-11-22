import pandas as pd
import statsmodels.api as sm


def _safe_ols_beta(y: pd.Series, x: pd.Series):
    pair = pd.DataFrame({"y": y, "x": x}).dropna()
    if len(pair) < 5:
        return None, None, None
    X = sm.add_constant(pair["x"])
    model = sm.OLS(pair["y"], X).fit()
    param_name = pair["x"].name if pair["x"].name in model.params.index else "x"
    return round(float(model.params[param_name]), 4), round(float(model.rsquared), 4), float(f"{model.pvalues[param_name]:.4e}")


def analyze_macro_and_fx_sensitivity(data: dict, params: dict) -> dict:
    """
    [가설 1 & 4]
    휴장일 불일치로 인한 과도한 교집합 손실을 줄이기 위해
    개별 쌍(pair) 회귀와 국면별 분석을 필요한 컬럼 기준으로 분리 수행[cite: 1, 3]
    """
    dxy_ret = data.get("DXY", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    usdkrw_ret = data.get("USDKRW", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    usdkrw_close = data.get("USDKRW", pd.DataFrame()).get("Close", pd.Series(dtype=float))
    us10y_diff = data.get("US10Y", pd.DataFrame()).get("Close", pd.Series(dtype=float)).diff()
    nasdaq_ret = data.get("NASDAQ", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    sox_ret = data.get("SOX", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    kospi_ret = data.get("KOSPI", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    ewy_ret = data.get("EWY", pd.DataFrame()).get("Return", pd.Series(dtype=float))

    dxy_beta, dxy_r2, dxy_p = _safe_ols_beta(usdkrw_ret, dxy_ret)
    nq_beta, _, _ = _safe_ols_beta(nasdaq_ret, us10y_diff)
    sox_beta, _, _ = _safe_ols_beta(sox_ret, us10y_diff)

    fx_ma_win = int(params.get("fx_ma_window", 20))
    q_win = int(params.get("fx_quantile_window", 252))
    q_hi = float(params.get("fx_high_quantile", 0.80))
    rev_days = int(params.get("fx_reversal_days", 5))
    rev_th = float(params.get("fx_reversal_threshold", -0.005))
    ann_factor = float(params.get("trading_days_per_year", 252))

    kr_fx_df = pd.DataFrame({
        "KOSPI": kospi_ret,
        "SOX": sox_ret,
        "EWY": ewy_ret,
        "USDKRW_Ret": usdkrw_ret,
        "USDKRW_Close": usdkrw_close,
    }).dropna(subset=["KOSPI", "USDKRW_Close"])

    analysis_period = None
    obs_count = int(len(kr_fx_df))
    kospi_usdkrw_corr = None
    ewy_kospi_corr = None
    upper_ann_ret = None
    lower_ann_ret = None
    peak_rev_count = 0
    peak_rev_5d_kospi = None
    peak_rev_5d_sox = None
    peak_rev_5d_ewy = None

    if not kr_fx_df.empty:
        analysis_period = f"{kr_fx_df.index.min().strftime('%Y-%m-%d')} ~ {kr_fx_df.index.max().strftime('%Y-%m-%d')}"
        pair_corr = kr_fx_df[["KOSPI", "USDKRW_Ret"]].dropna()
        if len(pair_corr) >= 2:
            kospi_usdkrw_corr = round(float(pair_corr["KOSPI"].corr(pair_corr["USDKRW_Ret"])), 3)

        pair_ewy = kr_fx_df[["EWY", "KOSPI"]].dropna()
        if len(pair_ewy) >= 2:
            ewy_kospi_corr = round(float(pair_ewy["EWY"].corr(pair_ewy["KOSPI"])), 3)

        kr_fx_df["FX_MA"] = kr_fx_df["USDKRW_Close"].rolling(fx_ma_win).mean()
        kr_fx_df["FX_Upper_Pressure"] = kr_fx_df["USDKRW_Close"] > kr_fx_df["FX_MA"]

        fx_hi_level = kr_fx_df["USDKRW_Close"].rolling(q_win).quantile(q_hi)
        fx_nd_chg = kr_fx_df["USDKRW_Close"].pct_change(rev_days)
        kr_fx_df["FX_Peak_Reversal"] = (
            (kr_fx_df["USDKRW_Close"].shift(rev_days) >= fx_hi_level.shift(rev_days))
            & (fx_nd_chg < rev_th)
        )

        valid_regime = kr_fx_df.dropna(subset=["FX_MA"])
        upper_regime = valid_regime[valid_regime["FX_Upper_Pressure"]]
        lower_regime = valid_regime[~valid_regime["FX_Upper_Pressure"]]
        peak_rev_regime = kr_fx_df[kr_fx_df["FX_Peak_Reversal"].fillna(False)]

        if not upper_regime.empty:
            upper_ann_ret = round(float(upper_regime["KOSPI"].mean() * ann_factor * 100), 2)
        if not lower_regime.empty:
            lower_ann_ret = round(float(lower_regime["KOSPI"].mean() * ann_factor * 100), 2)

        peak_rev_count = int(len(peak_rev_regime))
        if peak_rev_count > 0:
            peak_rev_5d_kospi = round(float(peak_rev_regime["KOSPI"].mean() * rev_days * 100), 2)
            sox_sub = peak_rev_regime["SOX"].dropna()
            ewy_sub = peak_rev_regime["EWY"].dropna()
            if not sox_sub.empty:
                peak_rev_5d_sox = round(float(sox_sub.mean() * rev_days * 100), 2)
            if not ewy_sub.empty:
                peak_rev_5d_ewy = round(float(ewy_sub.mean() * rev_days * 100), 2)

    return {
        "analysis_period": analysis_period,
        "obs_count": obs_count,
        "dxy_to_usdkrw_beta": dxy_beta,
        "dxy_to_usdkrw_r2": dxy_r2,
        "dxy_to_usdkrw_p_value": dxy_p,
        "us10y_to_nasdaq_beta": nq_beta,
        "us10y_to_sox_beta": sox_beta,
        "kospi_usdkrw_daily_corr": kospi_usdkrw_corr,
        "ewy_kospi_daily_corr": ewy_kospi_corr,
        "fx_upper_pressure_kospi_ann_ret_pct": upper_ann_ret,
        "fx_lower_stable_kospi_ann_ret_pct": lower_ann_ret,
        "fx_peak_reversal_events": peak_rev_count,
        "fx_peak_reversal_5d_kospi_avg_pct": peak_rev_5d_kospi,
        "fx_peak_reversal_5d_sox_avg_pct": peak_rev_5d_sox,
        "fx_peak_reversal_5d_ewy_avg_pct": peak_rev_5d_ewy,
    }
