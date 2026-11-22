import json
from pathlib import Path


def evaluate_checkpoints(input_path: Path) -> dict:
    """11/25~27 매크로·금통위·소비·수출입·수급·ETF LP 수치가 입력되면 시나리오 및 대응 신호를 자동 판정"""
    if not input_path.exists():
        return {"status": "template_ready_awaiting_inputs", "evaluations": []}

    with open(input_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    evaluations = []

    us_macro = payload.get("us_macro_1125", {})
    pce = us_macro.get("core_pce_mom_pct")
    if pce is not None:
        if pce <= 0.2:
            regime = "완화/안정 시나리오: 미 10년물 금리 하향 안정 → 나스닥·국내 반도체/성장주 반등 우호"
        elif pce >= 0.3:
            regime = "매파/상방 압력 시나리오: DXY 강세·원/달러 상방 압력 확대 → 외국인 현·선물 수급 경계"
        else:
            regime = "중립 구간(0.2%~0.3% 사이): 세부 항목 및 금리 반응 추가 확인"
        evaluations.append({
            "checkpoint": "11/25 미국 10월 Core PCE MoM (%)",
            "value": pce,
            "signal": regime,
        })

    gdp = us_macro.get("gdp_q3_rev_saar_pct")
    if gdp is not None:
        evaluations.append({
            "checkpoint": "11/25 미국 3분기 GDP 수정치 (연율 %)",
            "value": gdp,
            "signal": "성장 탄력 양호" if gdp >= 2.5 else "성장 둔화 경계",
        })

    bok = payload.get("bok_mpb_1126", {})
    if bok.get("gdp_2027_forecast_revised_down") is not None:
        if bok["gdp_2027_forecast_revised_down"]:
            tone = "성장 전망 하향 + 비둘기파 시그널: 채권 금리 하락 우호적이나 단기 원화 약세·환율 상승 부담 양면 구간"
        else:
            tone = "성장 전망 유지/상향: 급격한 완화 기대 제한·금리/환율 변동폭 점검"
        evaluations.append({
            "checkpoint": "11/26 한은 금통위 수정 경제전망 및 가이던스",
            "value": {
                "base_rate_action": bok.get("base_rate_action"),
                "gdp_2027_revised_down": bok.get("gdp_2027_forecast_revised_down"),
                "forward_guidance_tone": bok.get("forward_guidance_tone"),
                "ktb_3y_10y_spread_bp_change": bok.get("ktb_3y_10y_spread_bp_change"),
            },
            "signal": tone,
        })

    trade = payload.get("bfcm_and_trade", {})
    if trade.get("kr_export_nov_1_20_yoy_pct") is not None or trade.get("nrf_adobe_growth_vs_forecast") is not None:
        evaluations.append({
            "checkpoint": "BFCM 소비 및 한국 11/1~20 수출입 잠정치",
            "value": trade,
            "signal": "실적·수출·소비 검증 섹터(반도체/소비재/물류) 선별 대응 조건 점검 완료",
        })

    flows = payload.get("flows_and_etf_lp", {})
    spread = flows.get("us_etf_max_spread_pct")
    disparity = flows.get("us_etf_max_disparity_pct")
    if spread is not None or disparity is not None:
        lp_signal = "국내 상장 미국 지수 ETF 장중 LP 호가 스프레드/괴리율 확대 유의 — 시장가 지양·지정가 주문 권장"
        evaluations.append({
            "checkpoint": "11/26~27 미 증시 휴장/조기폐장 ETF LP 유동성 점검",
            "value": {"max_spread_pct": spread, "max_disparity_pct": disparity},
            "signal": lp_signal,
        })

    return {
        "status": "evaluated_with_provided_inputs" if evaluations else "pending_values",
        "evaluations": evaluations,
    }
