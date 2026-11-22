import pandas as pd
from scipy import stats


def _empty_thanksgiving_result(lookback_days: int) -> dict:
    return {
        "sample_period": None,
        "lookback_days": lookback_days,
        "tg_week_avg_vol_change_pct": None,
        "tg_week_median_vol_change_pct": None,
        "black_friday_avg_vol_change_pct": None,
        "tg_week_win_rate_pct": None,
        "tg_week_avg_return_pct": None,
        "tg_daily_volatility_pct": None,
        "normal_daily_volatility_pct": None,
        "volume_drop_t_stat": None,
        "volume_drop_p_value": None,
        "yearly_series": {
            "years": [],
            "vol_change_pct": [],
            "week_return_pct": [],
        },
    }


def get_thanksgiving_dates(years) -> pd.DatetimeIndex:
    """각 연도의 미국 추수감사절(11월 네 번째 목요일) 날짜 계산"""
    tg_dates = []
    for y in sorted(set(int(y) for y in years)):
        nov_days = pd.date_range(start=f"{y}-11-01", end=f"{y}-11-30", freq="D")
        thursdays = nov_days[nov_days.dayofweek == 3]
        if len(thursdays) >= 4:
            tg_dates.append(thursdays[3])
    return pd.DatetimeIndex(tg_dates)


def analyze_thanksgiving_anomaly(sp500_df: pd.DataFrame, lookback_days: int = 20) -> dict:
    """
    [가설 2] 추수감사절 주간(월~금) 및 블랙프라이데이의 거래량 급감(-30~40%)
    및 수익률/변동성 계절성 통계 검증
    """
    if sp500_df is None or sp500_df.empty:
        return _empty_thanksgiving_result(lookback_days)

    required_cols = {"Close", "Volume", "Return"}
    if not required_cols.issubset(sp500_df.columns):
        return _empty_thanksgiving_result(lookback_days)

    df = sp500_df.copy()
    df = df[df["Volume"] > 0].dropna(subset=["Close", "Volume", "Return"])
    if len(df) <= lookback_days:
        return _empty_thanksgiving_result(lookback_days)

    df["Year"] = df.index.year
    df["Vol_MA"] = df["Volume"].rolling(window=lookback_days).mean().shift(1)
    df["Vol_Change_Pct"] = (df["Volume"] / df["Vol_MA"]) - 1.0
    df = df.dropna(subset=["Vol_MA", "Vol_Change_Pct"])

    if df.empty:
        return _empty_thanksgiving_result(lookback_days)

    tg_dates = get_thanksgiving_dates(df["Year"].unique())
    tg_week_mask = pd.Series(False, index=df.index)
    bf_friday_mask = pd.Series(False, index=df.index)

    for tg in tg_dates:
        week_start = tg - pd.Timedelta(days=3)
        week_end = tg + pd.Timedelta(days=1)
        tg_week_mask |= (df.index >= week_start) & (df.index <= week_end)
        bf_friday_mask |= (df.index == week_end)

    tg_df = df[tg_week_mask]
    normal_df = df[~tg_week_mask]
    bf_df = df[bf_friday_mask]

    if tg_df.empty or normal_df.empty:
        return _empty_thanksgiving_result(lookback_days)

    yearly_vol_drop = tg_df.groupby("Year")["Vol_Change_Pct"].mean()
    yearly_week_ret = tg_df.groupby("Year")["Return"].sum()

    t_stat, p_val = stats.ttest_ind(
        tg_df["Vol_Change_Pct"],
        normal_df["Vol_Change_Pct"],
        equal_var=False,
    )

    return {
        "sample_period": f"{df.index.min().year} ~ {df.index.max().year} ({len(tg_dates)}개년)",
        "lookback_days": lookback_days,
        "tg_week_avg_vol_change_pct": round(float(yearly_vol_drop.mean() * 100), 2),
        "tg_week_median_vol_change_pct": round(float(yearly_vol_drop.median() * 100), 2),
        "black_friday_avg_vol_change_pct": round(float(bf_df["Vol_Change_Pct"].mean() * 100), 2) if not bf_df.empty else None,
        "tg_week_win_rate_pct": round(float((yearly_week_ret > 0).mean() * 100), 2),
        "tg_week_avg_return_pct": round(float(yearly_week_ret.mean() * 100), 2),
        "tg_daily_volatility_pct": round(float(tg_df["Return"].std() * 100), 3),
        "normal_daily_volatility_pct": round(float(normal_df["Return"].std() * 100), 3),
        "volume_drop_t_stat": round(float(t_stat), 2),
        "volume_drop_p_value": float(f"{p_val:.4e}"),
        "yearly_series": {
            "years": [int(y) for y in yearly_vol_drop.index],
            "vol_change_pct": [round(float(v * 100), 2) for v in yearly_vol_drop.values],
            "week_return_pct": [round(float(r * 100), 2) for r in yearly_week_ret.reindex(yearly_vol_drop.index).fillna(0.0).values],
        },
    }
