import json
from pathlib import Path
from datetime import datetime

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "config.json"
OUTPUT_DIR = ROOT_DIR / "output"


def load_config(config_path: Path = CONFIG_PATH) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["end_date"] = datetime.today().strftime("%Y-%m-%d")
    return cfg
