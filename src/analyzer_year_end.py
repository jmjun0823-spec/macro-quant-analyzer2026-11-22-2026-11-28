import pandas as pd
from scipy import stats


def _compute_window_spreads(
    series_a: pd.Series,
    series_b: pd.Series,
    start_mmdd: str = "11-20",
    end_mmdd: str = "12-26",
    min_obs: int = 2,
) -> pd.DataFrame:
    """
    매년 [start_mmdd ~ end_mmdd] 구간 수익률 및 스프레드(A - B) 계산
    (휴장일 공백으로 실제 거래일 수가 적어도 시작/종료 관측치가 있으면 min_obs=2로 계산)
    """
    if series_a is None or series_b is None or series_a.empty or series_b.empty:
        return pd.DataFrame(columns=["Year", "Ret_A", "Ret_B", "Spread_A_minus_B"])

    pair = pd.DataFrame({"A": series_a, "B": series_b}).dropna()
    if pair.empty:
        return pd.DataFrame(columns=["Year", "Ret_A", "Ret_B", "Spread_A_minus_B"])

    rows = []
    for y in sorted(pair.index.year.unique()):
        sub = pair.loc[f"{y}-{start_mmdd}":f"{y}-{end_mmdd}"]
        if len(sub) >= min_obs:
            ret_a = (sub["A"].iloc[-1] / sub["A"].iloc[0]) - 1.0
            ret_b = (sub["B"].iloc[-1] / sub["B"].iloc[0]) - 1.0
            rows.append({
                "Year": int(y),
                "Ret_A": float(ret_a),
                "Ret_B": float(ret_b),
                "Spread_A_minus_B": float(ret_a - ret_b),
            })
    return pd.DataFrame(rows)


def analyze_year_end_rotation(
    kospi_df: pd.DataFrame,
    kosdaq_df: pd.DataFrame,
    etf_df: pd.DataFrame,
    start_mmdd: str = "11-20",
    end_mmdd: str = "12-26",
) -> dict:
    """
    [가설 3] 11월 말~12월 배당락 직전 구간:
    북클로징·배당 차익거래 수혜(대형주/고배당주) vs 대주주 양도세·베타 축소 매물(코스닥/중소형주) 검증[cite: 1]
    """
    kospi_close = kospi_df["Close"] if (kospi_df is not None and "Close" in kospi_df.columns) else pd.Series(dtype=float)
    kosdaq_close = kosdaq_df["Close"] if (kosdaq_df is not None and "Close" in kosdaq_df.columns) else pd.Series(dtype=float)

    res_idx = _compute_window_spreads(kospi_close, kosdaq_close, start_mmdd, end_mmdd)

    idx_summary = {
        "window": f"{start_mmdd} ~ {end_mmdd}",
        "index_period": None,
        "avg_kospi_ret_pct": None,
        "avg_kosdaq_ret_pct": None,
        "avg_kospi_minus_kosdaq_pct": None,
        "kospi_outperform_win_rate_pct": None,
        "index_spread_t_stat": None,
        "index_spread_p_value": None,
    }
    if not res_idx.empty:
        t_stat_idx, p_val_idx = stats.ttest_1samp(res_idx["Spread_A_minus_B"], 0.0)
        idx_summary.update({
            "index_period": f"{res_idx['Year'].min()} ~ {res_idx['Year'].max()}",
            "avg_kospi_ret_pct": round(float(res_idx["Ret_A"].mean() * 100), 2),
            "avg_kosdaq_ret_pct": round(float(res_idx["Ret_B"].mean() * 100), 2),
            "avg_kospi_minus_kosdaq_pct": round(float(res_idx["Spread_A_minus_B"].mean() * 100), 2),
            "kospi_outperform_win_rate_pct": round(float((res_idx["Spread_A_minus_B"] > 0).mean() * 100), 2),
            "index_spread_t_stat": round(float(t_stat_idx), 2),
            "index_spread_p_value": round(float(p_val_idx), 4),
        })

    etf_summary = {}
    res_etf = pd.DataFrame()
    if etf_df is not None and not etf_df.empty and {"ARIRANG_HIGHDIV", "KODEX_KOSDAQ150"}.issubset(etf_df.columns):
        res_etf = _compute_window_spreads(
            etf_df["ARIRANG_HIGHDIV"],
            etf_df["KODEX_KOSDAQ150"],
            start_mmdd,
            end_mmdd,
        )
        if not res_etf.empty:
            t_stat_etf, p_val_etf = stats.ttest_1samp(res_etf["Spread_A_minus_B"], 0.0)
            etf_summary = {
                "etf_period": f"{res_etf['Year'].min()} ~ {res_etf['Year'].max()}",
                "avg_highdiv_ret_pct": round(float(res_etf["Ret_A"].mean() * 100), 2),
                "avg_kosdaq150_ret_pct": round(float(res_etf["Ret_B"].mean() * 100), 2),
                "highdiv_alpha_pct": round(float(res_etf["Spread_A_minus_B"].mean() * 100), 2),
                "highdiv_outperform_win_rate_pct": round(float((res_etf["Spread_A_minus_B"] > 0).mean() * 100), 2),
                "etf_spread_t_stat": round(float(t_stat_etf), 2),
                "etf_spread_p_value": round(float(p_val_etf), 4),
            }

    return {
        **idx_summary,
        **etf_summary,
        "yearly_index_series": {
            "years": res_idx["Year"].tolist() if not res_idx.empty else [],
            "kospi_ret_pct": [round(float(x * 100), 2) for x in res_idx["Ret_A"]] if not res_idx.empty else [],
            "kosdaq_ret_pct": [round(float(x * 100), 2) for x in res_idx["Ret_B"]] if not res_idx.empty else [],
            "spread_pct": [round(float(x * 100), 2) for x in res_idx["Spread_A_minus_B"]] if not res_idx.empty else [],
        },
        "yearly_etf_series": {
            "years": res_etf["Year"].tolist(),
            "highdiv_ret_pct": [round(float(x * 100), 2) for x in res_etf["Ret_A"]],
            "kosdaq150_ret_pct": [round(float(x * 100), 2) for x in res_etf["Ret_B"]],
            "alpha_pct": [round(float(x * 100), 2) for x in res_etf["Spread_A_minus_B"]],
        } if not res_etf.empty else {},
    }
