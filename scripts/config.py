"""Load config.json + state.json. Edit thresholds here via config.json, not code."""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
STATE_PATH = os.path.join(ROOT, "state.json")


def load_config():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"seen_ids": []}
    try:
        with open(STATE_PATH, encoding="utf-8") as f:
            data = json.load(f)
            if "seen_ids" not in data:
                return {"seen_ids": []}
            return data
    except Exception:
        return {"seen_ids": []}


def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
