import importlib
import json
from pathlib import Path
from typing import Any, Dict, List

from src.checkpoint_evaluator import evaluate_checkpoints, format_checkpoint_evaluation_md


def _format_num(val: Any, decimals: int = 2, suffix: str = "") -> str:
    if val is None:
        return "미집계"
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(val)


def _run_analyzers_if_available() -> Dict[str, Any]:
    results: Dict[str, Any] = {}
    candidate_modules = [
        "src.analyzers",
        "src.macro_analyzer",
        "src.thanksgiving_analyzer",
        "src.yearend_analyzer",
        "src.risk_analyzer",
    ]
    for mod_name in candidate_modules:
        try:
            mod = importlib.import_module(mod_name)
        except ModuleNotFoundError:
            continue
        for fn_name in ["run_all", "run_analysis", "analyze"]:
            fn = getattr(mod, fn_name, None)
            if callable(fn):
                out = fn()
                if isinstance(out, dict):
                    results.update(out)
                break
    return results


def build_report_markdown(results: Dict[str, Any]) -> str:
    macro = results.get("1_Macro_Rates_and_FX_Sensitivity", {})
    tg = results.get("2_Thanksgiving_Calendar_Anomaly", {})
    ye = results.get("3_YearEnd_BookClosing_and_Dividend_Rotation", {})
    risk = results.get("4_Quant_Risk_and_Allocation", {})
    ext = results.get("5_All_Report_Items_and_Checkpoints", {})
    ckpt_eval = results.get("6_Checkpoint_Event_Evaluation", {})

    bench = risk.get("benchmark_risk_70_30", {})
    tactical = risk.get("tactical_fx_regime", {})
    proxies = ext.get("2_bfcm_consumption_proxies", {})
    pending_items = ext.get("5_checkpoints_and_pending_items", [])

    lines: List[str] = [
        "# 11월 4주차 매크로 및 계절성 정량 검증 리포트",
        "",
        "## 1. 한·미 통화정책 및 환율·금리 민감도",
        f"- 분석 기간: {macro.get('analysis_period', '2003-12-01 ~ 2026-11-27')} (n={macro.get('obs_count', 0)})",
        f"- DXY → 원/달러 환율 Beta: {_format_num(macro.get('dxy_to_usdkrw_beta'), 4)} (R²={_format_num(macro.get('dxy_to_usdkrw_r2'), 4)}, p={macro.get('dxy_to_usdkrw_p_value')})",
        f"- 미 10년물 금리 변화(%p) → 나스닥 Beta: {_format_num(macro.get('us10y_to_nasdaq_beta'), 4)} / SOX Beta: {_format_num(macro.get('us10y_to_sox_beta'), 4)}",
        f"- KOSPI 연환산 수익률: 환율 상단 압력 구간 {_format_num(macro.get('fx_upper_pressure_kospi_ann_ret_pct'), 2, '%')} vs 안정/하락 구간 {_format_num(macro.get('fx_lower_stable_kospi_ann_ret_pct'), 2, '%')}",
        f"- 환율 고점권 하락 반전({macro.get('fx_peak_reversal_events', 0)}회) 이후 5일 평균: KOSPI {_format_num(macro.get('fx_peak_reversal_5d_kospi_avg_pct'), 2, '%')} / SOX {_format_num(macro.get('fx_peak_reversal_5d_sox_avg_pct'), 2, '%')}",
        "",
        "## 2. 추수감사절 주간 캘린더 아노말리 (S&P 500)",
        f"- 표본 기간: {tg.get('sample_period', '1950 ~ 2026 (77개년)')}",
        f"- 추수감사절 주간 평균 거래량 변화율: {_format_num(tg.get('tg_week_avg_vol_change_pct'), 2, '%')} (블랙프라이데이: {_format_num(tg.get('black_friday_avg_vol_change_pct'), 2, '%')})",
        f"- 거래량 차이 Welch t-stat: {_format_num(tg.get('volume_drop_t_stat'), 2)} (p={tg.get('volume_drop_p_value')})",
        f"- 추수감사절 주간 평균 수익률: {_format_num(tg.get('tg_week_avg_return_pct'), 2, '%')} (승률 {_format_num(tg.get('tg_week_win_rate_pct'), 2, '%')})",
        "",
        "## 3. 연말 북클로징 및 수급 로테이션",
        f"- 지수 분석 기간({ye.get('window', '11-20 ~ 12-26')}): {ye.get('index_period', '2000 ~ 2026')} | 평균 KOSPI {_format_num(ye.get('avg_kospi_ret_pct'), 2, '%')} vs KOSDAQ {_format_num(ye.get('avg_kosdaq_ret_pct'), 2, '%')} (스프레드 {_format_num(ye.get('avg_kospi_minus_kosdaq_pct'), 2, '%p')}, KOSPI 우위 승률 {_format_num(ye.get('kospi_outperform_win_rate_pct'), 2, '%')}, p={ye.get('index_spread_p_value')})",
        f"- 스타일 ETF({ye.get('etf_period', '2015 ~ 2026')}): 고배당 {_format_num(ye.get('avg_highdiv_ret_pct'), 2, '%')} vs 코스닥150 {_format_num(ye.get('avg_kosdaq150_ret_pct'), 2, '%')} (고배당 알파 {_format_num(ye.get('highdiv_alpha_pct'), 2, '%p')}, 승률 {_format_num(ye.get('highdiv_outperform_win_rate_pct'), 2, '%')}, p={ye.get('etf_spread_p_value')})",
        "",
        "## 4. 리스크 및 전술적 비중 시뮬레이션",
        f"- 벤치마크(70/30): 연수익 {_format_num(bench.get('ann_return_pct'), 2, '%')}, 변동성 {_format_num(bench.get('ann_volatility_pct'), 2, '%')}, Vol Drag {_format_num(bench.get('ann_volatility_drag_pct'), 2, '%')}, 95% CVaR {_format_num(bench.get('daily_cvar_95_pct'), 2, '%')}",
        f"- 환율 국면 전술 배분: 연수익 {_format_num(tactical.get('ann_return_pct'), 2, '%')}, 변동성 {_format_num(tactical.get('ann_volatility_pct'), 2, '%')}, Vol Drag {_format_num(tactical.get('ann_volatility_drag_pct'), 2, '%')}, 95% CVaR {_format_num(tactical.get('daily_cvar_95_pct'), 2, '%')}",
        "",
        "## 5. 확장 프록시 및 체크포인트",
        f"- 소비/물류 프록시: XRT 연환산 {_format_num(proxies.get('retail_xrt_ann_ret_pct'), 2, '%')} (BFCM 구간 평균 {_format_num(proxies.get('xrt_bfcm_window_avg_ret_pct'), 2, '%')}), IYT 연환산 {_format_num(proxies.get('transport_logistics_iyt_ann_ret_pct'), 2, '%')}",
    ]

    for item in pending_items:
        lines.append(
            f"- [{item.get('status', 'pending')}] {item.get('item', '')} → {item.get('check_criteria', '')}"
        )

    lines.append("")
    lines.extend(format_checkpoint_evaluation_md(ckpt_eval))
    return "\n".join(lines) + "\n"


def save_outputs(
    results: Dict[str, Any],
    output_dir: Path = Path("output"),
    report_path: Path = Path("verification_report.md"),
    results_path: Path = Path("verification_results.json"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    results["6_Checkpoint_Event_Evaluation"] = evaluate_checkpoints()

    results_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    report_path.write_text(
        build_report_markdown(results),
        encoding="utf-8",
    )


def main() -> None:
    existing_results_path = Path("verification_results.json")
    base_results: Dict[str, Any] = {}
    if existing_results_path.exists():
        loaded = json.loads(existing_results_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            base_results = loaded

    computed = _run_analyzers_if_available()
    if computed:
        base_results.update(computed)

    save_outputs(base_results)


if __name__ == "__main__":
    main()
