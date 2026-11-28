import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from src.checkpoint_evaluator import evaluate_checkpoints, format_checkpoint_evaluation_md
from src.config_loader import load_config
from src.data_loader import fetch_global_data, fetch_krx_etf_data
from src.visualization import generate_charts


ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT_DIR / "output"
DATA_DIR = ROOT_DIR / "data"
CONFIG_DIR = ROOT_DIR / "config"


def _format_num(val: Any, decimals: int = 2, suffix: str = "") -> str:
    if val is None:
        return "미집계"
    try:
        return f"{float(val):.{decimals}f}{suffix}"
    except (TypeError, ValueError):
        return str(val)


def _format_p_val(val: Any) -> str:
    if val is None:
        return "미집계"
    try:
        fval = float(val)
        return f"{fval:.4e}" if fval < 1e-3 else f"{fval:.4f}"
    except (TypeError, ValueError):
        return str(val)


def _empty_ohlcv() -> pd.DataFrame:
    return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume", "Return", "Log_Return"])


def _build_context() -> Dict[str, Any]:
    cfg = load_config()
    global_data = fetch_global_data(cfg)
    krx_etf_data = fetch_krx_etf_data(cfg)

    def _df(key: str) -> pd.DataFrame:
        val = global_data.get(key)
        return val if isinstance(val, pd.DataFrame) else _empty_ohlcv()

    context: Dict[str, Any] = {
        "root_dir": ROOT_DIR,
        "output_dir": OUTPUT_DIR,
        "data_dir": DATA_DIR,
        "config_dir": CONFIG_DIR,
        "cfg": cfg,
        "config": cfg,
        "params": cfg,
        "global_data": global_data,
        "data_store": global_data,
        "krx_etf_data": krx_etf_data,
        "etf_df": krx_etf_data,
        "etf_data": krx_etf_data,
        "data": {
            "global_data": global_data,
            "krx_etf_data": krx_etf_data,
        },
        # 개별 DataFrame 인자 매핑 (analyzer_year_end, analyzer_macro_fx, analyzer_thanksgiving, quant_allocation 대응)
        "kospi_df": _df("KOSPI"),
        "kosdaq_df": _df("KOSDAQ"),
        "sp500_df": _df("SP500"),
        "nasdaq_df": _df("NASDAQ"),
        "sox_df": _df("SOX"),
        "dxy_df": _df("DXY"),
        "usdkrw_df": _df("USDKRW"),
        "us10y_df": _df("US10Y"),
        "ewy_df": _df("EWY"),
        "tlt_df": _df("TLT"),
        "hyg_df": _df("HYG"),
        "xrt_df": _df("XRT"),
        "iyt_df": _df("IYT"),
        # config 내 주요 파라미터 인자 매핑
        "start_mmdd": cfg.get("year_end_start_mmdd", "11-20"),
        "end_mmdd": cfg.get("year_end_end_mmdd", "12-26"),
        "lookback_days": cfg.get("thanksgiving_lookback_days", 20),
        "trading_days_per_year": cfg.get("trading_days_per_year", 252),
    }

    for k, v in cfg.items():
        if k not in context:
            context[k] = v

    return context


def _call_with_supported_kwargs(fn: Callable[..., Any], available_kwargs: Dict[str, Any]) -> Any:
    sig = inspect.signature(fn)
    params = sig.parameters
    accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    if accepts_var_kw:
        return fn(**available_kwargs)

    call_kwargs: Dict[str, Any] = {}
    aliases: Dict[str, List[str]] = {
        "cfg": ["cfg", "config", "params"],
        "config": ["config", "cfg", "params"],
        "params": ["params", "cfg", "config"],
        "global_data": ["global_data", "data_store", "data"],
        "data_store": ["data_store", "global_data", "data"],
        "krx_etf_data": ["krx_etf_data", "etf_df", "etf_data"],
        "etf_df": ["etf_df", "krx_etf_data", "etf_data"],
        "etf_data": ["etf_data", "krx_etf_data", "etf_df"],
        "spx_df": ["sp500_df"],
        "sp500": ["sp500_df"],
        "kospi": ["kospi_df"],
        "kosdaq": ["kosdaq_df"],
        "nasdaq": ["nasdaq_df"],
        "sox": ["sox_df"],
        "dxy": ["dxy_df"],
        "usdkrw": ["usdkrw_df"],
        "us10y": ["us10y_df"],
        "ewy": ["ewy_df"],
    }

    for param_name, param in params.items():
        if param_name in available_kwargs:
            call_kwargs[param_name] = available_kwargs[param_name]
            continue
        matched = False
        for cand in aliases.get(param_name, []):
            if cand in available_kwargs and available_kwargs[cand] is not None:
                call_kwargs[param_name] = available_kwargs[cand]
                matched = True
                break
        if not matched and param.default is inspect.Parameter.empty:
            raise TypeError(f"Missing required parameter: {param_name}")

    return fn(**call_kwargs)


def _is_empty_result(out: Dict[str, Any]) -> bool:
    if not out:
        return True
    if out.get("obs_count") == 0 and all(
        v is None for k, v in out.items() if k not in {"analysis_period", "obs_count", "fx_peak_reversal_events"}
    ):
        return True
    return False


def _run_module_best_dict(
    mod: Any,
    preferred_names: List[str],
    context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    seen_ids = set()
    ordered_fns: List[Callable[..., Any]] = []

    for name in preferred_names:
        fn = getattr(mod, name, None)
        if callable(fn) and id(fn) not in seen_ids:
            seen_ids.add(id(fn))
            ordered_fns.append(fn)

    for attr_name in dir(mod):
        if attr_name.startswith("_"):
            continue
        fn = getattr(mod, attr_name, None)
        if callable(fn) and getattr(fn, "__module__", "") == mod.__name__ and id(fn) not in seen_ids:
            seen_ids.add(id(fn))
            ordered_fns.append(fn)

    for fn in ordered_fns:
        try:
            out = _call_with_supported_kwargs(fn, context)
            if isinstance(out, dict) and not _is_empty_result(out):
                print(f"[Analyzer] {mod.__name__}.{fn.__name__} -> keys={list(out.keys())}")
                return out
        except Exception as exc:
            print(f"[Warn] {mod.__name__}.{fn.__name__} skipped: {exc}")

    return None


def _normalize_all_items_bucket(aggregated: Dict[str, Any], out: Dict[str, Any]) -> None:
    sub_keys = [
        "1_policy_rates_fx",
        "2_bfcm_consumption_proxies",
        "3_year_end_sectors",
        "4_foreign_fx_proxies",
        "5_checkpoints_and_pending_items",
    ]
    bucket = dict(aggregated.get("5_All_Report_Items_and_Checkpoints", {}))
    if isinstance(out.get("5_All_Report_Items_and_Checkpoints"), dict):
        bucket.update(out["5_All_Report_Items_and_Checkpoints"])
    for sk in sub_keys:
        if sk in out:
            bucket[sk] = out[sk]
            aggregated[sk] = out[sk]
    if bucket:
        aggregated["5_All_Report_Items_and_Checkpoints"] = bucket


def run_all_analyzers() -> Dict[str, Any]:
    context = _build_context()
    aggregated: Dict[str, Any] = {}

    specs = [
        (
            "src.analyzer_macro_fx",
            ["analyze_macro_and_fx_sensitivity", "analyze_macro_fx", "run_macro_fx", "run_analysis", "analyze"],
            "1_Macro_Rates_and_FX_Sensitivity",
        ),
        (
            "src.analyzer_thanksgiving",
            ["analyze_thanksgiving_anomaly", "analyze_thanksgiving", "run_thanksgiving", "run_analysis", "analyze"],
            "2_Thanksgiving_Calendar_Anomaly",
        ),
        (
            "src.analyzer_year_end",
            ["analyze_year_end_rotation", "analyze_year_end", "run_year_end", "run_analysis", "analyze"],
            "3_YearEnd_BookClosing_and_Dividend_Rotation",
        ),
        (
            "src.quant_allocation",
            ["analyze_quant_risk_and_allocation", "run_quant_allocation", "run_analysis", "analyze"],
            "4_Quant_Risk_and_Allocation",
        ),
        (
            "src.analyzer_all_items",
            ["derive_all_report_items", "analyze_all_items", "run_all_items", "run_analysis", "analyze"],
            "5_All_Report_Items_and_Checkpoints",
        ),
    ]

    for mod_name, fn_names, key in specs:
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:
            print(f"[Warn] {mod_name} import skipped: {exc}")
            continue

        out = _run_module_best_dict(mod, fn_names, context)
        if not out:
            continue

        if key == "5_All_Report_Items_and_Checkpoints":
            _normalize_all_items_bucket(aggregated, out)
        elif key in out and isinstance(out[key], dict):
            aggregated[key] = out[key]
        elif any(k.startswith(("1_", "2_", "3_", "4_", "5_")) for k in out):
            aggregated.update(out)
        else:
            aggregated[key] = out

        context["results"] = aggregated

    return aggregated


def _build_charts_safely(results: Dict[str, Any], output_dir: Path) -> List[str]:
    tg_results = results.get("2_Thanksgiving_Calendar_Anomaly", {})
    ye_results = results.get("3_YearEnd_BookClosing_and_Dividend_Rotation", {})

    try:
        generated = generate_charts(tg_results, ye_results, output_dir)
        paths = [str(p) for p in (generated or []) if Path(p).exists()]
        if not paths:
            paths = sorted(str(p) for p in output_dir.glob("*.png"))
        print(f"[Charts] Generated {len(paths)} PNG file(s): {paths}")
        return paths
    except Exception as exc:
        print(f"[Warn] generate_charts failed: {exc}")
        return sorted(str(p) for p in output_dir.glob("*.png"))


def build_report_markdown(results: Dict[str, Any]) -> str:
    macro = results.get("1_Macro_Rates_and_FX_Sensitivity", {})
    tg = results.get("2_Thanksgiving_Calendar_Anomaly", {})
    ye = results.get("3_YearEnd_BookClosing_and_Dividend_Rotation", {})
    risk = results.get("4_Quant_Risk_and_Allocation", {})
    ext = results.get("5_All_Report_Items_and_Checkpoints", {})
    if not ext and "2_bfcm_consumption_proxies" in results:
        ext = results
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
        f"- DXY → 원/달러 환율 Beta: {_format_num(macro.get('dxy_to_usdkrw_beta'), 4)} (R²={_format_num(macro.get('dxy_to_usdkrw_r2'), 4)}, p={_format_p_val(macro.get('dxy_to_usdkrw_p_value'))})",
        f"- 미 10년물 금리 변화(%p) → 나스닥 Beta: {_format_num(macro.get('us10y_to_nasdaq_beta'), 4)} / SOX Beta: {_format_num(macro.get('us10y_to_sox_beta'), 4)}",
        f"- KOSPI 연환산 수익률: 환율 상단 압력 구간 {_format_num(macro.get('fx_upper_pressure_kospi_ann_ret_pct'), 2, '%')} vs 안정/하락 구간 {_format_num(macro.get('fx_lower_stable_kospi_ann_ret_pct'), 2, '%')}",
        f"- 환율 고점권 하락 반전({macro.get('fx_peak_reversal_events', 0)}회) 이후 5일 평균: KOSPI {_format_num(macro.get('fx_peak_reversal_5d_kospi_avg_pct'), 2, '%')} / SOX {_format_num(macro.get('fx_peak_reversal_5d_sox_avg_pct'), 2, '%')}",
        "",
        "## 2. 추수감사절 주간 캘린더 아노말리 (S&P 500)",
        f"- 표본 기간: {tg.get('sample_period', '1950 ~ 2026 (77개년)')}",
        f"- 추수감사절 주간 평균 거래량 변화율: {_format_num(tg.get('tg_week_avg_vol_change_pct'), 2, '%')} (블랙프라이데이: {_format_num(tg.get('black_friday_avg_vol_change_pct'), 2, '%')})",
        f"- 거래량 차이 Welch t-stat: {_format_num(tg.get('volume_drop_t_stat'), 2)} (p={_format_p_val(tg.get('volume_drop_p_value'))})",
        f"- 추수감사절 주간 평균 수익률: {_format_num(tg.get('tg_week_avg_return_pct'), 2, '%')} (승률 {_format_num(tg.get('tg_week_win_rate_pct'), 2, '%')})",
        "",
        "## 3. 연말 북클로징 및 수급 로테이션",
        f"- 지수 분석 기간({ye.get('window', '11-20 ~ 12-26')}): {ye.get('index_period', '2000 ~ 2026')} | 평균 KOSPI {_format_num(ye.get('avg_kospi_ret_pct'), 2, '%')} vs KOSDAQ {_format_num(ye.get('avg_kosdaq_ret_pct'), 2, '%')} (스프레드 {_format_num(ye.get('avg_kospi_minus_kosdaq_pct'), 2, '%p')}, KOSPI 우위 승률 {_format_num(ye.get('kospi_outperform_win_rate_pct'), 2, '%')}, p={_format_p_val(ye.get('index_spread_p_value'))})",
        f"- 스타일 ETF({ye.get('etf_period', '2015 ~ 2026')}): 고배당 {_format_num(ye.get('avg_highdiv_ret_pct'), 2, '%')} vs 코스닥150 {_format_num(ye.get('avg_kosdaq150_ret_pct'), 2, '%')} (고배당 알파 {_format_num(ye.get('highdiv_alpha_pct'), 2, '%p')}, 승률 {_format_num(ye.get('highdiv_outperform_win_rate_pct'), 2, '%')}, p={_format_p_val(ye.get('etf_spread_p_value'))})",
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
    output_dir: Path = OUTPUT_DIR,
) -> Dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)

    chart_paths = _build_charts_safely(results, output_dir)
    if chart_paths:
        results["generated_charts"] = chart_paths

    results["6_Checkpoint_Event_Evaluation"] = evaluate_checkpoints(DATA_DIR / "checkpoints_input.json")

    report_md = build_report_markdown(results)
    results_json_str = json.dumps(results, indent=2, ensure_ascii=False)

    (output_dir / "verification_results.json").write_text(results_json_str, encoding="utf-8")
    (output_dir / "verification_report.md").write_text(report_md, encoding="utf-8")
    (ROOT_DIR / "verification_report.md").write_text(report_md, encoding="utf-8")

    return results


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    computed = run_all_analyzers()
    save_outputs(computed, output_dir=OUTPUT_DIR)
    print(f"[Done] Saved outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
