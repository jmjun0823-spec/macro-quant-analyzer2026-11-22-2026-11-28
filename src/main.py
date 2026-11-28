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

    for mod_name, fn_names, ctx_key in [
        ("src.config_loader", ["load_config", "get_config", "read_config"], "config"),
        ("src.data_loader", ["load_all_data", "load_market_data", "load_data", "fetch_all_data"], "data"),
    ]:
        try:
            mod = importlib.import_module(mod_name)
            for name in fn_names:
                fn = getattr(mod, name
