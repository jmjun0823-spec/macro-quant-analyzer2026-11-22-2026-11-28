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
