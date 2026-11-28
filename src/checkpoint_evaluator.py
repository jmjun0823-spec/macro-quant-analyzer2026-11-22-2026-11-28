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


def _extract_items(payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload.get("items"), dict) and payload["items"]:
        return payload["items"]
    reserved = {"checkpoint_window", "status", "items", "evaluations"}
    return {k: v for k, v in payload.items() if k not in reserved and isinstance(v, dict)}


def _eval_us_macro(key: str, item: Dict[str, Any]) -> Dict[str, Any]:
    gdp = item.get("q3_gdp_revision_pct")
    if gdp is None:
        gdp = item.get("gdp_q3_rev_yoy_pct")
    core_pce = item.get("core_pce_mom_pct")

    if gdp is None and core_pce is None:
        return {
            "checkpoint": key,
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
        reason += f" | Q3 GDP 수정치 {gdp}%"

    return {
        "checkpoint": key,
        "status": "evaluated",
        "signal": signal,
        "value": {"q3_gdp_revision_pct": gdp, "core_pce_mom_pct": core_pce},
        "reason": reason,
    }


def _eval_bok_mpb(key: str, item: Dict[str, Any]) -> Dict[str, Any]:
    base_rate = item.get("base_rate_pct")
    g_down = item.get("growth_2027_downgraded")
    if g_down is None:
        g_down = item.get("gdp_2027_forecast_revised_down")
    i_down = item.get("inflation_2027_downgraded")
    fwd = item.get("forward_guidance_3m")
    spread = item.get("ktb_3y_10y_spread_bp")

    if all(v is None for v in [base_rate, g_down, i_down, fwd, spread]):
        return {
            "checkpoint": key,
            "status": "pending",
            "signal": "PENDING",
            "value": item,
            "reason": "한은 금통위 기준금리·2027년 전망 하향 여부·포워드 가이던스·3Y-10Y 스프레드 미입력",
        }

    signal = "GROWTH_INFLATION_DOWNGRADE_BIAS" if (bool(g_down) or bool(i_down)) else "HOLD_OR_HAWKISH_GUIDANCE"
    reason = (
        f"기준금리 {base_rate}%, 2027년 성장/물가 하향({g_down}/{i_down}), "
        f"3M 가이던스({fwd}), 국고채 3Y-10Y 스프레드 {spread}bp"
    )
    return {
        "checkpoint": key,
        "status": "evaluated",
        "signal": signal,
        "value": item,
        "reason": reason,
    }


def _eval_bfcm_trade(key: str, item: Dict[str, Any]) -> Dict[str, Any]:
    bfcm = item.get("nrf_adobe_bfcm_online_sales_growth_pct")
    semi = item.get("kr_nov_1_20_semi_export_growth_pct")
    balance = item.get("kr_nov_1_20_trade_balance_usd_b")

    if all(v is None for v in [bfcm, semi, balance]):
        return {
            "checkpoint": key,
            "status": "pending",
            "signal": "PENDING",
            "value": item,
            "reason": "BFCM 온라인 소비 및 한국 11/1~20 수출입 잠정치 미입력",
        }

    is_positive = (bfcm is not None and float(bfcm) > 0) or (semi is not None and float(semi) > 0)
    signal = "SUPPORTIVE_DEMAND_AND_EXPORTS" if is_positive else "CAUTIOUS_MOMENTUM"
    reason = f"BFCM 온라인 성장 {bfcm}%, 11/1~20 반도체 수출 {semi}%, 무역수지 ${balance}B"
    return {
        "checkpoint": key,
        "status": "evaluated",
        "signal": signal,
        "value": item,
        "reason": reason,
    }


def _eval_flows_etf(key: str, item: Dict[str, Any]) -> Dict[str, Any]:
    book = item.get("institutional_book_closing_flow_krw_b")
    div_arb = item.get("dividend_arbitrage_flow_krw_b")
    fut = item.get("foreign_kospi200_futures_cum_net_buy_krw_b")
    spread_pct = item.get("us_holiday_early_close_etf_spread_pct")
    if spread_pct is None:
        spread_pct = item.get("us_etf_max_spread_pct")
    prem_pct = item.get("us_holiday_early_close_etf_premium_discount_pct")
    if prem_pct is None:
        prem_pct = item.get("us_etf_max_disparity_pct")

    if all(v is None for v in [book, div_arb, fut, spread_pct, prem_pct]):
        return {
            "checkpoint": key,
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
        "checkpoint": key,
        "status": "evaluated",
        "signal": signal,
        "value": item,
        "reason": reason,
    }


def _pick_key(items: Dict[str, Any], aliases: List[str], default_key: str) -> str:
    for name in aliases:
        if name in items and isinstance(items[name], dict):
            return name
    return default_key


def evaluate_checkpoints(input_path: Path = Path("data/checkpoints_input.json")) -> Dict[str, Any]:
    payload = load_checkpoints_payload(Path(input_path))
    if not payload:
        return _default_pending_result("checkpoints_input.json이 비어 있거나 유효하지 않음")

    items = _extract_items(payload)
    if not items:
        return _default_pending_result("체크포인트 입력 항목이 비어 있음")

    us_key = _pick_key(items, ["us_gdp_and_core_pce", "us_macro_1125"], "us_macro_1125")
    bok_key = _pick_key(items, ["bok_mpb_and_rates", "bok_mpb_1126"], "bok_mpb_1126")
    bfcm_key = _pick_key(items, ["bfcm_and_kr_trade", "bfcm_kr_trade"], "bfcm_kr_trade")
    flows_key = _pick_key(items, ["flows_and_etf_dislocation", "flows_and_etf_lp"], "flows_and_etf_lp")

    evaluations: List[Dict[str, Any]] = [
        _eval_us_macro(us_key, items.get(us_key, {})),
        _eval_bok_mpb(bok_key, items.get(bok_key, {})),
        _eval_bfcm_trade(bfcm_key, items.get(bfcm_key, {})),
        _eval_flows_etf(flows_key, items.get(flows_key, {})),
    ]

    evaluated_count = sum(1 for e in evaluations if e["status"] == "evaluated")
    if evaluated_count == 0:
        overall_status = "pending_values"
    else:
        overall_status = "evaluated_with_provided_inputs"

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
