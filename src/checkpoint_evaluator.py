import json
from pathlib import Path
from typing import Any, Dict, List


def _default_pending_result(reason: str = "입력값 대기 중") -> Dict[str, Any]:
    return {
        "status": "pending_values",
        "evaluations": [],
        "summary": reason,
    }


def load_checkpoints_payload(input_path: Path) -> Dict[str, Any]:
    if not input_path.exists():
        return {}
    raw = input_path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _eval_us_gdp_and_core_pce(item: Dict[str, Any]) -> Dict[str, Any]:
    gdp = item.get("q3_gdp_revision_pct")
    core_pce = item.get("core_pce_mom_pct")
    if gdp is None and core_pce is None:
        return {
            "checkpoint": "us_gdp_and_core_pce",
            "status": "pending",
            "signal": "PENDING",
            "value": {"q3_gdp_revision_pct": gdp, "core_pce_mom_pct": core_pce},
            "reason": "미국 3분기 GDP 수정치 및 10월 Core PCE MoM 미입력",
        }

    if core_pce is not None and float(core_pce) <= 0.2:
        signal = "DOVISH_STABLE"
        reason = f"Core PCE MoM {core_pce}% (<= +0.2%): 완화·안정 시그널"
    elif core_pce is not None and float(core_pce) >= 0.3:
        signal = "HAWKISH_FX_USD_PRESSURE"
        reason = f"Core PCE MoM {core_pce}% (>= +0.3%): 매파·달러/환율 상방 압력"
    else:
        signal = "NEUTRAL"
        reason = f"Core PCE MoM {core_pce}% (중간 구간)"

    if gdp is not None:
        reason += f" | Q3 GDP 수정치 연율 {gdp}%"

    return {
        "checkpoint": "us_gdp_and_core_pce",
        "status": "evaluated",
        "signal": signal,
        "value": {"q3_gdp_revision_pct": gdp, "core_pce_mom_pct": core_pce},
        "reason": reason,
    }


def _eval_bok_mpb_and_rates(item: Dict[str, Any]) -> Dict[str, Any]:
    base_rate = item.get("base_rate_pct")
    g_down = item.get("growth_2027_downgraded")
    i_down = item.get("inflation_2027_downgraded")
    fwd = item.get("forward_guidance_3m")
    spread = item.get("ktb_3y_10y_spread_bp")

    if all(v is None for v in [base_rate, g_down, i_down, fwd, spread]):
        return {
            "checkpoint": "bok_mpb_and_rates",
            "status": "pending",
            "signal": "PENDING",
            "value": item,
            "reason": "한은 금통위 기준금리·2027년 전망 하향 여부·포워드 가이던스·3Y-10Y 스프레드 미입력",
        }

    if bool(g_down) or bool(i_down):
        signal = "GROWTH_INFLATION_DOWNGRADE_BIAS"
    else:
        signal = "HOLD_OR_HAWKISH_GUIDANCE"

    reason = (
        f"기준금리 {base_rate}%, 2027년 성장/물가 하향({g_down}/{i_down}), "
        f"3M 가이던스({fwd}), 국고채 3Y-10Y 스프레드 {spread}bp"
    )
    return {
        "checkpoint": "bok_mpb_and_rates",
        "status": "evaluated",
        "signal": signal,
        "value": {
            "base_rate_pct": base_rate,
            "growth_2027_downgraded": g_down,
            "inflation_2027_downgraded": i_down,
            "forward_guidance_3m": fwd,
            "ktb_3y_10y_spread_bp": spread,
        },
        "reason": reason,
    }


def _eval_bfcm_and_kr_trade(item: Dict[str, Any]) -> Dict[str, Any]:
    bfcm = item.get("nrf_adobe_bfcm_online_sales_growth_pct")
    semi = item.get("kr_nov_1_20_semi_export_growth_pct")
    balance = item.get("kr_nov_1_20_trade_balance_usd_b")

    if all(v is None for v in [bfcm, semi, balance]):
        return {
            "checkpoint": "bfcm_and_kr_trade",
            "status": "pending",
            "signal": "PENDING",
            "value": item,
            "reason": "BFCM 온라인 소비 및 한국 11/1~20 수출입 잠정치 미입력",
        }

    is_positive = ((bfcm is not None and float(bfcm) > 0) or (semi is not None and float(semi) > 0))
    signal = "SUPPORTIVE_DEMAND_AND_EXPORTS" if is_positive else "CAUTIOUS_MOMENTUM"
    reason = (
        f"BFCM 온라인 성장 {bfcm}%, 11/1~20 반도체 수출 {semi}%, "
        f"무역수지 ${balance}B"
    )
    return {
        "checkpoint": "bfcm_and_kr_trade",
        "status": "evaluated",
        "signal": signal,
        "value": {
            "nrf_adobe_bfcm_online_sales_growth_pct": bfcm,
            "kr_nov_1_20_semi_export_growth_pct": semi,
            "kr_nov_1_20_trade_balance_usd_b": balance,
        },
        "reason": reason,
    }


def _eval_flows_and_etf_dislocation(item: Dict[str, Any]) -> Dict[str, Any]:
    book = item.get("institutional_book_closing_flow_krw_b")
    div_arb = item.get("dividend_arbitrage_flow_krw_b")
    fut = item.get("foreign_kospi200_futures_cum_net_buy_krw_b")
    spread_pct = item.get("us_holiday_early_close_etf_spread_pct")
    prem_pct = item.get("us_holiday_early_close_etf_premium_discount_pct")

    if all(v is None for v in [book, div_arb, fut, spread_pct, prem_pct]):
        return {
            "checkpoint": "flows_and_etf_dislocation",
            "status": "pending",
            "signal": "PENDING",
            "value": item,
            "reason": "기관 북클로징·배당 차익거래·외인 선물·휴장/조기폐장 ETF 스프레드 및 괴리율 미입력",
        }

    has_dislocation = (
        (prem_pct is not None and abs(float(prem_pct)) >= 0.5)
        or (spread_pct is not None and float(spread_pct) >= 0.3)
    )
    signal = "ETF_DISLOCATION_ALERT" if has_dislocation else "FLOW_AND_ETF_NORMAL"
    reason = (
        f"기관 북클로징 {book}B, 배당차익 {div_arb}B, 외인선물 누적 {fut}B, "
        f"ETF 스프레드 {spread_pct}% / 괴리율 {prem_pct}%"
    )
    return {
        "checkpoint": "flows_and_etf_dislocation",
        "status": "evaluated",
        "signal": signal,
        "value": {
            "institutional_book_closing_flow_krw_b": book,
            "dividend_arbitrage_flow_krw_b": div_arb,
            "foreign_kospi200_futures_cum_net_buy_krw_b": fut,
            "us_holiday_early_close_etf_spread_pct": spread_pct,
            "us_holiday_early_close_etf_premium_discount_pct": prem_pct,
        },
        "reason": reason,
    }


def evaluate_checkpoints(input_path: Path = Path("data/checkpoints_input.json")) -> Dict[str, Any]:
    payload = load_checkpoints_payload(Path(input_path))
    if not payload:
        return _default_pending_result("checkpoints_input.json이 비어 있거나 유효하지 않음")

    items = payload.get("items")
    if not isinstance(items, dict) or not items:
        return _default_pending_result("items 객체가 비어 있음")

    evaluators = {
        "us_gdp_and_core_pce": _eval_us_gdp_and_core_pce,
        "bok_mpb_and_rates": _eval_bok_mpb_and_rates,
        "bfcm_and_kr_trade": _eval_bfcm_and_kr_trade,
        "flows_and_etf_dislocation": _eval_flows_and_etf_dislocation,
    }

    evaluations: List[Dict[str, Any]] = []
    for key, item_data in items.items():
        if not isinstance(item_data, dict):
            continue
        fn = evaluators.get(key)
        if fn is not None:
            evaluations.append(fn(item_data))

    evaluated_count = sum(1 for e in evaluations if e["status"] == "evaluated")
    if evaluated_count == 0:
        overall_status = "pending_values"
    elif evaluated_count == len(evaluations):
        overall_status = "evaluated"
    else:
        overall_status = "partial_evaluated"

    return {
        "status": overall_status,
        "checkpoint_window": payload.get("checkpoint_window", "2026-11-25..2026-11-27"),
        "evaluated_count": evaluated_count,
        "total_count": len(evaluations),
        "evaluations": evaluations,
    }


if __name__ == "__main__":
    result = evaluate_checkpoints()
    print(json.dumps(result, indent=2, ensure_ascii=False))
