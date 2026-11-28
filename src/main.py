import importlib
import inspect
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.checkpoint_evaluator import evaluate_checkpoints, format_checkpoint_evaluation_md
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


def _call_with_supported_kwargs(fn: Callable[..., Any], available_kwargs: Dict[str, Any]) -> Any:
    sig = inspect.signature(fn)
    params = sig.parameters
    accepts_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
    if accepts_var_kw:
        return fn(**available_kwargs)
    filtered = {k: v for k, v in available_kwargs.items() if k in params}
    return fn(**filtered)


def _load_config_and_data() -> Dict[str, Any]:
    context: Dict[str, Any] = {
        "root_dir": ROOT_DIR,
        "output_dir": OUTPUT_DIR,
        "data_dir": DATA_DIR,
        "config_dir": CONFIG_DIR,
    }

    try:
        cfg_mod = importlib.import_module("src.config_loader")
        for fn_name in ["load_config", "get_config", "read_config"]:
            fn = getattr(cfg_mod, fn_name, None)
            if callable(fn):
                cfg = _call_with_supported_kwargs(fn, context)
                if cfg is not None:
                    context["config"] = cfg
                break
    except Exception as exc:
        print(f"[Warn] config_loader skipped: {exc}")

    try:
        dl_mod = importlib.import_module("src.data_loader")
        for fn_name in ["load_all_data", "load_market_data", "load_data", "fetch_all_data"]:
            fn = getattr(dl_mod, fn_name, None)
            if callable(fn):
                data = _call_with_supported_kwargs(fn, context)
                if data is not None:
                    context["data"] = data
                break
    except Exception as exc:
        print(f"[Warn] data_loader skipped: {exc}")

    return context


def _find_and_run_callable(
    mod: Any,
    preferred_names: List[str],
    fallback_prefix: str,
    context: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    candidates: List[Callable[..., Any]] = []
    for name in preferred_names:
        fn = getattr(mod, name, None)
        if callable(fn):
            candidates.append(fn)

    if not candidates:
        for attr_name in dir(mod):
            if attr_name.startswith("_"):
                continue
            if fallback_prefix in attr_name:
                fn = getattr(mod, attr_name, None)
                if callable(fn):
                    candidates.append(fn)

    for fn in candidates:
        try:
            out = _call_with_supported_kwargs(fn, context)
            if isinstance(out, dict) and out:
                return out
        except Exception as exc:
            print(f"[Warn] {mod.__name__}.{fn.__name__} failed: {exc}")
    return None


def run_all_analyzers() -> Dict[str, Any]:
    context = _load_config_and_data()
    aggregated: Dict[str, Any] = {}

    specs = [
        (
            "src.analyzer_macro_fx",
            ["analyze_macro_and_fx_sensitivity", "analyze_macro_fx", "run_analysis", "analyze"],
            "macro",
            "1_Macro_Rates_and_FX_Sensitivity",
        ),
        (
            "src.analyzer_thanksgiving",
            ["analyze_thanksgiving_anomaly", "analyze_thanksgiving", "run_analysis", "analyze"],
            "thanksgiving",
            "2_Thanksgiving_Calendar_Anomaly",
        ),
        (
            "src.analyzer_year_end",
            ["analyze_year_end_rotation", "analyze_year_end", "run_analysis", "analyze"],
            "year_end",
            "3_YearEnd_BookClosing_and_Dividend_Rotation",
        ),
        (
            "src.quant_allocation",
            ["analyze_quant_risk_and_allocation", "run_quant_allocation", "run_analysis", "analyze"],
            "risk",
            "4_Quant_Risk_and_Allocation",
        ),
        (
            "src.analyzer_all_items",
            ["derive_all_report_items", "analyze_all_items", "run_analysis", "analyze"],
            "item",
            "5_All_Report_Items_and_Checkpoints",
        ),
    ]

    for mod_name, fn_names, prefix, key in specs:
        try:
            mod = importlib.import_module(mod_name)
        except Exception as exc:
            print(f"[Warn] {mod_name} import skipped: {exc}")
            continue

        out = _find_and_run_callable(mod, fn_names, prefix, context)
        if out:
            if key in out and isinstance(out[key], dict):
                aggregated[key] = out[key]
            elif any(k.startswith(("1_", "2_", "3_", "4_", "5_")) for k in out):
                aggregated.update(out)
            else:
                aggregated[key] = out
            context["results"] = aggregated

    return aggregated


def _merge_preserving_series(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing)
    for k, v in incoming.items():
        if v is None and k in merged and merged[k] is not None:
            continue
        if isinstance(v, dict) and not v and k in merged and isinstance(merged[k], dict) and merged[k]:
            continue
        merged[k] = v
    return merged


def _build_charts_safely(results: Dict[str, Any], output_dir: Path) -> List[str]:
    tg_results = results.get("2_Thanksgiving_Calendar_Anomaly", {})
    ye_results = results.get("3_YearEnd_BookClosing_and_Dividend_Rotation", {})

    has_tg = bool(
        isinstance(tg_results, dict)
        and tg_results.get("yearly_series", {}).get("years")
        and tg_results.get("tg_week_avg_vol_change_pct") is not None
    )
    has_ye = bool(
        isinstance(ye_results, dict)
        and ye_results.get("yearly_index_series", {}).get("years")
    )

    if not has_tg and not has_ye:
        print("[Warn] No chart series found in 2_Thanksgiving_Calendar_Anomaly or 3_YearEnd_BookClosing_and_Dividend_Rotation")
        return []

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

    base_results: Dict[str, Any] = {}
    for candidate in [OUTPUT_DIR / "verification_results.json", ROOT_DIR / "verification_results.json"]:
        if candidate.exists():
            try:
                loaded = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    base_results = loaded
                    break
            except json.JSONDecodeError:
                pass

    computed = run_all_analyzers()
    for k, v in computed.items():
        if isinstance(v, dict) and v:
            prev = base_results.get(k)
            base_results[k] = _merge_preserving_series(prev, v) if isinstance(prev, dict) else v

    save_outputs(base_results, output_dir=OUTPUT_DIR)
    print(f"[Done] Saved outputs to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
