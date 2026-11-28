import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


def evaluate_checkpoint_item(key: str, data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {
            "key": key,
            "status": "pending",
            "signal": "PENDING",
            "summary": "입력 데이터 형식이 올바르지 않음",
        }

    if key == "us_gdp_and_core_pce":
        pce = data.get("core_pce_mom_pct")
        gdp = data.get("q3_gdp_revision_pct")
        if pce is None and gdp is None:
            return {
                "key": key,
                "status": "pending",
                "signal": "PENDING",
                "summary": "미국 3분기 GDP 수정치 및 10월 Core PCE MoM 미입력",
            }
        if pce is not None and pce <= 0.2:
            sig = "DOVISH_STABLE"
            desc = f"Core PCE MoM {pce}% (<= +0.2%): 완화·안정 시그널"
        elif pce is not None and pce >= 0.3:
            sig = "HAWKISH_FX_USD_PRESSURE"
            desc = f"Core PCE MoM {pce}% (>= +0.3%): 매파·달러/환율 상방 압력"
        else:
            sig = "NEUTRAL"
            desc = f"Core PCE MoM {pce}% (중간 구간)"
        if gdp is not None:
            desc += f" / Q3 GDP 수정치 {gdp}%"
        return {"key": key, "status": "evaluated", "signal": sig, "summary": desc}

    if key == "bok_mpb_and_rates":
        rate = data.get("base_rate_pct")
        g_down = data.get("growth_2027_downgraded")
        i_down = data.get("inflation_2027_downgraded")
        fwd = data.get("forward_guidance_3m")
        spread = data.get("ktb_3y_10y_spread_bp")
        if all(v is None for v in [rate, g_down, i_down, fwd, spread]):
            return {
                "key": key,
                "status": "pending",
                "signal": "PENDING",
                "summary": "한은 금통위 기준금리·수정전망·포워드 가이던스·3Y-10Y 스프레드 미입력",
            }
        sig = "DOVISH_GROWTH_DOWN" if (bool(g_down) or bool(i_down)) else "HOLD_OR_CAUTIOUS"
        desc = (
            f"기준금리 {rate}%, 2027년 성장/물가 하향({g_down}/{i_down}), "
            f"3개월 가이던스({fwd}), 국고채 3Y-10Y 스프레드 {spread}bp"
        )
        return {"key": key, "status": "evaluated", "signal": sig, "summary": desc}

    if key == "bfcm_and_kr_trade":
        bfcm = data.get("nrf_adobe_bfcm_online_sales_growth_pct")
        semi = data.get("kr_nov_1_20_semi_export_growth_pct")
        balance = data.get("kr_nov_1_20_trade_balance_usd_b")
        if all(v is None for v in [bfcm, semi, balance]):
            return {
                "key": key,
                "status": "pending",
                "signal": "PENDING",
                "summary": "NRF·Adobe BFCM 온라인 소비 및 한국 11/1~20 수출입 잠정치 미입력",
            }
        strong = (bfcm is not None and bfcm > 0) and (semi is not None and semi > 0)
        sig = "CONSUMPTION_SEMI_SUPPORTIVE" if strong else "MIXED_MOMENTUM"
        desc = f"BFCM 온라인 성장 {bfcm}%, 11/1~20 반도체 수출 {semi}%, 무역수지 ${balance}B"
        return {"key": key, "status": "evaluated", "signal": sig, "summary": desc}

    if key == "flows_and_etf_dislocation":
        book = data.get("institutional_book_closing_flow_krw_b")
        div_arb = data.get("dividend_arbitrage_flow_krw_b")
        fut = data.get("foreign_kospi200_futures_cum_net_buy_krw_b")
        spread_pct = data.get("us_holiday_early_close_etf_spread_pct")
        prem_pct = data.get("us_holiday_early_close_etf_premium_discount_pct")
        if all(v is None for v in [book, div_arb, fut, spread_pct, prem_pct]):
            return {
                "key": key,
                "status": "pending",
                "signal": "PENDING",
                "summary": "기관 북클로징·배당차익·외인선물 누적 순매수·휴장/조기폐장 ETF 괴리율 미입력",
            }
        dislocated = (abs(prem_pct or 0.0) >= 0.5) or ((spread_pct or 0.0) >= 0.3)
        sig = "ETF_DISLOCATION_CAUTION" if dislocated else "NORMAL_FLOW_EXECUTION"
        desc = (
            f"북클로징 {book}B, 배당차익 {div_arb}B, 외인선물 누적 {fut}B, "
            f"ETF 스프레드 {spread_pct}% / 괴리율 {prem_pct}%"
        )
        return {"key": key, "status": "evaluated", "signal": sig, "summary": desc}

    return {"key": key, "status": "pending", "signal": "PENDING", "summary": "미정의 항목"}


def run_checkpoint_evaluation(
    input_path: Path = Path("data/checkpoints_input.json"),
    results_path: Path = Path("output/verification_results.json"),
    report_path: Path = Path("output/verification_report.md"),
) -> Dict[str, Any]:
    input_obj = json.loads(input_path.read_text(encoding="utf-8"))
    items: Dict[str, Any] = input_obj.get("items", {})
    evaluations: List[Dict[str, Any]] = [
        evaluate_checkpoint_item(k, v) for k, v in items.items()
    ]
    all_done = len(evaluations) > 0 and all(e["status"] == "evaluated" for e in evaluations)

    results_obj = json.loads(results_path.read_text(encoding="utf-8"))
    results_obj["6_Checkpoint_Event_Evaluation"] = {
        "status": "evaluated" if all_done else "partial_or_pending",
        "checkpoint_window": input_obj.get("checkpoint_window", "2026-11-25..2026-11-27"),
        "evaluations": evaluations,
    }
    results_path.write_text(
        json.dumps(results_obj, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    section_lines = [
        "## 6. 발표·원장 입력값 자동 판정",
        f"- 판정 상태: `{results_obj['6_Checkpoint_Event_Evaluation']['status']}`",
    ]
    for ev in evaluations:
        section_lines.append(f"- **{ev['key']}** (`{ev['signal']}`): {ev['summary']}")

    report_str = report_path.read_text(encoding="utf-8")
    anchor = "## 6. 발표·원장 입력값 자동 판정"
    if anchor in report_str:
        head = report_str.split(anchor)[0].rstrip()
        updated_report = head + "\n\n" + "\n".join(section_lines) + "\n"
    else:
        updated_report = report_str.rstrip() + "\n\n" + "\n".join(section_lines) + "\n"
    report_path.write_text(updated_report, encoding="utf-8")

    return results_obj["6_Checkpoint_Event_Evaluation"]


def finalize_macro_report(
    output_dir: Path = Path("output"),
    checkpoint_input: Path = Path("data/checkpoints_input.json"),
) -> None:
    results_path = output_dir / "verification_results.json"
    report_path = output_dir / "verification_report.md"

    if checkpoint_input.exists() and results_path.exists() and report_path.exists():
        summary = run_checkpoint_evaluation(
            input_path=checkpoint_input,
            results_path=results_path,
            report_path=report_path,
        )
        print(f"[Checkpoint Evaluation] status={summary.get('status')}")
    else:
        print("[Checkpoint Evaluation] skipped (missing input or base report)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate 11/25~27 checkpoints into results & report")
    parser.add_argument("--input", type=Path, default=Path("data/checkpoints_input.json"))
    parser.add_argument("--results", type=Path, default=Path("output/verification_results.json"))
    parser.add_argument("--report", type=Path, default=Path("output/verification_report.md"))
    args = parser.parse_args()

    out = run_checkpoint_evaluation(
        input_path=args.input,
        results_path=args.results,
        report_path=args.report,
    )
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
