import pandas as pd
import statsmodels.api as sm


def _pair_stats(ret_a: pd.Series, ret_b: pd.Series):
    pair = pd.DataFrame({"a": ret_a, "b": ret_b}).dropna()
    if len(pair) < 10:
        return {"obs": int(len(pair)), "corr": None, "beta_b_on_a": None, "p_value": None}
    corr = float(pair["a"].corr(pair["b"]))
    X = sm.add_constant(pair["b"])
    model = sm.OLS(pair["a"], X).fit()
    return {
        "obs": int(len(pair)),
        "corr": round(corr, 3),
        "beta_b_on_a": round(float(model.params["b"]), 4),
        "p_value": float(f"{model.pvalues['b']:.4e}"),
    }


def _window_return(series: pd.Series, year: int, start_mmdd: str = "11-20", end_mmdd: str = "12-26"):
    if series is None or series.empty:
        return None
    sub = series.loc[f"{year}-{start_mmdd}":f"{year}-{end_mmdd}"].dropna()
    if len(sub) < 2:
        return None
    return float((sub.iloc[-1] / sub.iloc[0]) - 1.0)


def derive_all_report_items(global_data: dict, krx_etf_data: pd.DataFrame, params: dict) -> dict:
    """리포트 본문의 매크로·소비/물류·연말 섹터·외국인 프록시 및 체크포인트 항목 도출"""
    ann = float(params.get("trading_days_per_year", 252))
    start_mmdd = params.get("year_end_start_mmdd", "11-20")
    end_mmdd = params.get("year_end_end_mmdd", "12-26")

    kospi_ret = global_data.get("KOSPI", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    nasdaq_ret = global_data.get("NASDAQ", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    sox_ret = global_data.get("SOX", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    us10y_diff = global_data.get("US10Y", pd.DataFrame()).get("Close", pd.Series(dtype=float)).diff()
    dxy_ret = global_data.get("DXY", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    usdkrw_ret = global_data.get("USDKRW", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    ewy_ret = global_data.get("EWY", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    xrt_ret = global_data.get("XRT", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    iyt_ret = global_data.get("IYT", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    tlt_ret = global_data.get("TLT", pd.DataFrame()).get("Return", pd.Series(dtype=float))
    hyg_ret = global_data.get("HYG", pd.DataFrame()).get("Return", pd.Series(dtype=float))

    policy_rates_fx = {
        "us10y_to_nasdaq": _pair_stats(nasdaq_ret, us10y_diff),
        "us10y_to_sox": _pair_stats(sox_ret, us10y_diff),
        "dxy_to_usdkrw": _pair_stats(usdkrw_ret, dxy_ret),
        "usdkrw_to_kospi": _pair_stats(kospi_ret, usdkrw_ret),
        "tlt_bond_proxy_ann_ret_pct": round(float(tlt_ret.dropna().mean() * ann * 100), 2) if not tlt_ret.dropna().empty else None,
        "hyg_credit_proxy_ann_ret_pct": round(float(hyg_ret.dropna().mean() * ann * 100), 2) if not hyg_ret.dropna().empty else None,
    }

    bfcm_consumption_proxies = {
        "retail_xrt_ann_ret_pct": round(float(xrt_ret.dropna().mean() * ann * 100), 2) if not xrt_ret.dropna().empty else None,
        "transport_logistics_iyt_ann_ret_pct": round(float(iyt_ret.dropna().mean() * ann * 100), 2) if not iyt_ret.dropna().empty else None,
    }
    if not xrt_ret.dropna().empty:
        years = sorted(xrt_ret.dropna().index.year.unique())
        bfcm_rets = [r for y in years if (r := _window_return(xrt_ret.add(1.0).cumprod(), y, "11-22", "12-05")) is not None]
        bfcm_consumption_proxies["xrt_bfcm_window_avg_ret_pct"] = round(float(sum(bfcm_rets) / len(bfcm_rets) * 100), 2) if bfcm_rets else None

    year_end_sectors = {}
    if krx_etf_data is not None and not krx_etf_data.empty:
        for col in krx_etf_data.columns:
            s = krx_etf_data[col].dropna()
            vals = []
            for y in sorted(s.index.year.unique()):
                r = _window_return(s, y, start_mmdd, end_mmdd)
                if r is not None:
                    vals.append(r)
            year_end_sectors[f"{col}_window_avg_ret_pct"] = round(float(sum(vals) / len(vals) * 100), 2) if vals else None

    foreign_fx_proxies = {
        "ewy_to_kospi": _pair_stats(kospi_ret, ewy_ret),
        "sox_to_kospi": _pair_stats(kospi_ret, sox_ret),
    }

    checkpoints_and_pending_items = [
        {
            "item": "미국 3분기 GDP 수정치 및 10월 개인소비지출(PCE) 물가(11/25)",
            "status": "scheduled_event_or_external_macro",
            "check_criteria": "Core PCE MoM +0.2% 이하(완화·안정) vs +0.3% 이상(매파·달러/환율 상방)",
        },
        {
            "item": "한국은행 금융통화위원회 기준금리·수정 경제전망·3개월 포워드 가이던스(11/26)",
            "status": "scheduled_event_or_external_macro",
            "check_criteria": "2027년 성장률·물가 전망 하향 여부 및 국고채 3년-10년 스프레드 변화",
        },
        {
            "item": "NRF·Adobe BFCM 온라인 소비 및 한국 11/1~20 품목별 수출입 잠정치",
            "status": "external_agency_data_required",
            "check_criteria": "반도체 단가·물량 회복세 및 북미 연말 소비·물류·K-뷰티/음식료 수요 확인",
        },
        {
            "item": "기관 북클로징 자금·배당 차익거래·외국인 KOSPI 200 선물 누적 순매수·ETF LP 괴리율",
            "status": "exchange_ledger_or_intraday_required",
            "check_criteria": "11/26~27 미 증시 휴장/조기폐장 시 국내 상장 미 지수 ETF 호가 스프레드·괴리율 점검",
        },
    ]

    return {
        "1_policy_rates_fx": policy_rates_fx,
        "2_bfcm_consumption_proxies": bfcm_consumption_proxies,
        "3_year_end_sectors": year_end_sectors,
        "4_foreign_fx_proxies": foreign_fx_proxies,
        "5_checkpoints_and_pending_items": checkpoints_and_pending_items,
    }
