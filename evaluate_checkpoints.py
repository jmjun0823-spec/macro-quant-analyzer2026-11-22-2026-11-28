import json
from pathlib import Path
from typing import Any, Dict, List


def evaluate_single_checkpoint(key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if key == "us_gdp_and_core_pce":
        pce = payload.get("core_pce_mom_pct")
        gdp = payload.get("q3_gdp_revision_pct")
        if pce is None and gdp is None:
            return {"key": key, "status": "pending", "signal": "PENDING", "note": "11/25 GDP/Core PCE 수치 미입력"}
        if pce is not None and pce <= 0.2:
            signal = "DOVISH_STABLE"
            note = f"Core PCE MoM {pce}% (<= +0.2%): 금리·환율 안정 우호"
        elif pce is not None and pce >= 0.3:
            signal = "HAWKISH_FX_USD_PRESSURE"
            note = f"Core PCE MoM {pce}% (>= +0.3%): 매파·달러/환율 상방 압력 주의"
        else:
            signal = "NEUTRAL_MIXED"
            note = f"Core PCE MoM {pce}%, Q3 GDP 수정치 {gdp}%: 혼합 시그널"
        return {"key": key, "status": "evaluated", "signal": signal, "note": note}

    if key == "bok_mpb_and_rates":
        rate = payload.get("base_rate_pct")
        g_down = payload.get("growth_2027_downgraded")
        i_down = payload.get("inflation_2027_downgraded")
        spread = payload.get("ktb_3y_10y_spread_bp")
        if all(v is None for v in [rate, g_down, i_down, spread]):
            return {"key": key, "status": "pending", "signal": "PENDING", "note": "11/26 한은 금통위·금리 수치 미입력"}
        dovish_tilt = bool(g_down) or bool(i_down)
        signal = "GROWTH_DOWN_EASING_BIAS" if dovish_tilt else "HOLD_OR_TIGHT_BIAS"
        note = f"기준금리 {rate}%, 27년 성장/물가 하향({g_down}/{i_down}), 3Y-10Y 스프레드 {spread}bp"
        return {"key": key, "status": "evaluated", "signal": signal, "note": note}

    if key == "bfcm_and_kr_trade":
        bfcm = payload.get("nrf_adobe_bfcm_online_sales_growth_pct")
        semi = payload.get("kr_nov_1_20_semi_export_growth_pct")
        bal = payload.get("kr_nov_1_20_trade_balance_usd_b")
        if all(v is None for v in [bfcm, semi, bal]):
            return {"key": key, "status": "pending", "signal": "PENDING", "note": "BFCM 소비 및 11/1~20 수출입 수치 미입력"}
        positive = ((bfcm or 0) > 0) and ((semi or 0) > 0)
        signal = "DEMAND_SEMI_RECOVERY" if positive else "SELECTIVE_MOMENTUM"
        note = f"BFCM 성장 {bfcm}%, 11/1~20 반도체 수출 {semi}%, 무역수지 ${bal}B"
        return {"key": key, "status": "evaluated", "signal": signal, "note": note}

    if key == "flows_and_etf_dislocation":
        book = payload.get("institutional_book_closing_flow_krw_b")
        div_arb = payload.get("dividend_arbitrage_flow_krw_b")
        fut = payload.get("foreign_kospi200_futures_cum_net_buy_krw_b")
        spread_pct = payload.get("us_holiday_early_close_etf_spread_pct")
        prem_pct = payload.get("us_holiday_early_close_etf_premium_discount_pct")
        if all(v is None for v in [book, div_arb, fut, spread_pct, prem_pct]):
            return {"key": key, "status": "pending", "signal": "PENDING", "note": "수급 원장 및 미 휴장·조기폐장 ETF 괴리율 미입력"}
        high_dislocation = abs(prem_pct or 0.0) >= 0.5 or (spread_pct or 0.0) >= 0.3
        signal = "ETF_SLIPPAGE_CAUTION" if high_dislocation else "FLOW_ALIGNED"
        note = (
            f"북클로징 {book}B, 배당차익 {div_arb}B, 외인선물 누적 {fut}B, "
            f"ETF 스프레드 {spread_pct}% / 괴리율 {prem_pct}%"
        )
        return {"key": key, "status": "evaluated", "signal": signal, "note": note}

    return {"key": key, "status": "pending", "signal": "PENDING", "note": "정의되지 않은 체크포인트"}


def run_checkpoint_evaluation(
    input_path: Path = Path("data/checkpoints_input.json"),
    results_path: Path = Path("verification_results.json"),
    report_path: Path = Path("verification_report.md"),
) -> Dict[str, Any]:
    raw_input = json.loads(input_path.read_text(encoding="utf-8"))
    items: Dict[str, Any] = raw_input.get("items", {})

    evaluations: List[Dict[str, Any]] = [
        evaluate_single_checkpoint(k, v) for k, v in items.items()
    ]
    all_evaluated = len(evaluations) > 0 and all(e["status"] == "evaluated" for e in evaluations)

    results = json.loads(results_path.read_text(encoding="utf-8"))
    results["6_Checkpoint_Event_Evaluation"] = {
        "status": "evaluated" if all_evaluated else "partial_or_pending",
        "checkpoint_window": raw_input.get("checkpoint_window", "2026-11-25..2026-11-27"),
        "evaluations": evaluations,
    }
    results_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")

    md_lines = [
        "",
        "## 6. 발표·원장 입력값 자동 판정 결과",
        f"- 상태: `{results['6_Checkpoint_Event_Evaluation']['status']}`",
    ]
    for ev in evaluations:
        md_lines.append(f"- **{ev['key']}** (`{ev['signal']}`): {ev['note']}")

    report_text = report_path.read_text(encoding="utf-8")
    marker = "## 6. 발표·원장 입력값 자동 판정"
    if marker in report_text:
        report_text = report_text.split(marker)[0].rstrip() + "\n" + "\n".join(md_lines) + "\n"
    else:
        report_text = report_text.rstrip() + "\n" + "\n".join(md_lines) + "\n"
    report_path.write_text(report_text, encoding="utf-8")

    return results["6_Checkpoint_Event_Evaluation"]


if __name__ == "__main__":
    out = run_checkpoint_evaluation()
    print(json.dumps(out, indent=2, ensure_ascii=False))
