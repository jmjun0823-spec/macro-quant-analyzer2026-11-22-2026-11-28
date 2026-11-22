import json
from src.config_loader import load_config, OUTPUT_DIR
from src.data_loader import fetch_global_data, fetch_krx_etf_data
from src.analyzer_thanksgiving import analyze_thanksgiving_anomaly
from src.analyzer_year_end import analyze_year_end_rotation
from src.analyzer_macro_fx import analyze_macro_and_fx_sensitivity
from src.quant_allocation import simulate_tactical_allocation
from src.visualization import generate_charts


def _build_markdown_summary(report: dict) -> str:
    m = report["1_Macro_Rates_and_FX_Sensitivity"]
    t = report["2_Thanksgiving_Calendar_Anomaly"]
    y = report["3_YearEnd_BookClosing_and_Dividend_Rotation"]
    q = report["4_Quant_Risk_and_Allocation"]

    lines = [
        "# 11월 4주차 매크로 및 계절성 정량 검증 리포트",
        "",
        "## 1. 한·미 통화정책 및 환율·금리 민감도",
        f"- 분석 기간: {m['analysis_period']} (n={m['obs_count']})",
        f"- DXY → 원/달러 환율 Beta: {m['dxy_to_usdkrw_beta']} (R²={m['dxy_to_usdkrw_r2']}, p={m['dxy_to_usdkrw_p_value']})",
        f"- 미 10년물 금리 변화(%p) → 나스닥 Beta: {m['us10y_to_nasdaq_beta']} / SOX Beta: {m['us10y_to_sox_beta']}",
        f"- KOSPI 연환산 수익률: 환율 상단 압력 구간 {m['fx_upper_pressure_kospi_ann_ret_pct']}% vs 안정/하락 구간 {m['fx_lower_stable_kospi_ann_ret_pct']}%",
        f"- 환율 고점권 하락 반전({m['fx_peak_reversal_events']}회) 이후 5일 평균: KOSPI {m['fx_peak_reversal_5d_kospi_avg_pct']}% / SOX {m['fx_peak_reversal_5d_sox_avg_pct']}%",
        "",
        "## 2. 추수감사절 주간 캘린더 아노말리 (S&P 500)",
        f"- 표본 기간: {t['sample_period']}",
        f"- 추수감사절 주간 평균 거래량 변화율: {t['tg_week_avg_vol_change_pct']}% (블랙프라이데이: {t['black_friday_avg_vol_change_pct']}%)",
        f"- 거래량 차이 Welch t-stat: {t['volume_drop_t_stat']} (p={t['volume_drop_p_value']})",
        f"- 추수감사절 주간 평균 수익률: {t['tg_week_avg_return_pct']}% (승률 {t['tg_week_win_rate_pct']}%)",
        "",
        "## 3. 연말 북클로징 및 수급 로테이션",
        f"- 지수 분석 기간({y['window']}): {y['index_period']} | 평균 KOSPI {y['avg_kospi_ret_pct']}% vs KOSDAQ {y['avg_kosdaq_ret_pct']}% (스프레드 {y['avg_kospi_minus_kosdaq_pct']}%p, KOSPI 우위 승률 {y['kospi_outperform_win_rate_pct']}%, p={y['index_spread_p_value']})",
    ]
    if "highdiv_alpha_pct" in y:
        lines.append(
            f"- 스타일 ETF({y['etf_period']}): 고배당 {y['avg_highdiv_ret_pct']}% vs 코스닥150 {y['avg_kosdaq150_ret_pct']}% (고배당 알파 {y['highdiv_alpha_pct']}%p, 승률 {y['highdiv_outperform_win_rate_pct']}%, p={y['etf_spread_p_value']})"
        )
    lines.extend([
        "",
        "## 4. 리스크 및 전술적 비중 시뮬레이션",
        f"- 벤치마크(70/30): 연수익 {q['benchmark_risk_70_30']['ann_return_pct']}%, 변동성 {q['benchmark_risk_70_30']['ann_volatility_pct']}%, Vol Drag {q['benchmark_risk_70_30']['ann_volatility_drag_pct']}%, 95% CVaR {q['benchmark_risk_70_30']['daily_cvar_95_pct']}%",
        f"- 환율 국면 전술 배분: 연수익 {q['tactical_fx_regime']['ann_return_pct']}%, 변동성 {q['tactical_fx_regime']['ann_volatility_pct']}%, Vol Drag {q['tactical_fx_regime']['ann_volatility_drag_pct']}%, 95% CVaR {q['tactical_fx_regime']['daily_cvar_95_pct']}%",
    ])
    return "\n".join(lines)


def main():
    cfg = load_config()
    params = cfg["parameters"]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/5] 데이터 수집 중...")
    global_data = fetch_global_data(cfg)
    krx_etf_data = fetch_krx_etf_data(cfg)

    print("[2/5] 추수감사절 캘린더 아노말리 검증 중...")
    tg_results = analyze_thanksgiving_anomaly(
        global_data["SP500"],
        lookback_days=int(params["volume_lookback_days"]),
    )

    print("[3/5] 연말 북클로징 & 대형/고배당 vs 중소형/코스닥 로테이션 검증 중...")
    ye_results = analyze_year_end_rotation(
        global_data["KOSPI"],
        global_data["KOSDAQ"],
        krx_etf_data,
        start_mmdd=params["year_end_start_mmdd"],
        end_mmdd=params["year_end_end_mmdd"],
    )

    print("[4/5] 매크로 금리·환율·외국인 프록시 민감도 및 전술 배분 검증 중...")
    macro_results = analyze_macro_and_fx_sensitivity(global_data, params)
    alloc_results = simulate_tactical_allocation(global_data, params)

    print("[5/5] 리포트 및 시각화 차트 생성 중...")
    charts = generate_charts(tg_results, ye_results, OUTPUT_DIR)

    full_report = {
        "1_Macro_Rates_and_FX_Sensitivity": macro_results,
        "2_Thanksgiving_Calendar_Anomaly": tg_results,
        "3_YearEnd_BookClosing_and_Dividend_Rotation": ye_results,
        "4_Quant_Risk_and_Allocation": alloc_results,
        "generated_charts": charts,
    }

    with open(OUTPUT_DIR / "verification_results.json", "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2, ensure_ascii=False)

    md_text = _build_markdown_summary(full_report)
    with open(OUTPUT_DIR / "verification_report.md", "w", encoding="utf-8") as f:
        f.write(md_text)

    print(md_text)
    print(f"\n저장 완료: {OUTPUT_DIR / 'verification_results.json'}, {OUTPUT_DIR / 'verification_report.md'}")


if __name__ == "__main__":
    main()
