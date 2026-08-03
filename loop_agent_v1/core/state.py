import json
import os
from datetime import date

STATE_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "state.json")


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _today_key() -> str:
    return str(date.today())


def _ensure_today(state: dict) -> dict:
    key = _today_key()
    if key not in state:
        state[key] = {
            "conversations": {},
            "apply_count": 0,
            "meta": {
                "heartbeat_count": 0,
                "action_count": 0,
                "success_count": 0,
                "fail_count": 0,
            }
        }
    return state


def update_conversation_state(action: dict, result: dict):
    state = load_state()
    state = _ensure_today(state)
    today = state[_today_key()]
    company = action.get("target", {}).get("company", "__unknown__")
    conv = today["conversations"].setdefault(company, {
        "stage": "new",
        "priority": "medium",
        "messages": [],
        "reply_count": 0,
        "last_action_id": None,
        "verified": False,
    })
    if result.get("status") == "success":
        conv["verified"] = True
        conv["last_action_id"] = action.get("id")
        conv["stage"] = _next_stage(conv["stage"], action.get("type"))
    today["meta"]["action_count"] += 1
    if result.get("status") == "success":
        today["meta"]["success_count"] += 1
    else:
        today["meta"]["fail_count"] += 1
    save_state(state)


def increment_heartbeat():
    state = load_state()
    state = _ensure_today(state)
    today = state[_today_key()]
    today["meta"]["heartbeat_count"] = today["meta"].get("heartbeat_count", 0) + 1
    save_state(state)


def _next_stage(current: str, action_type: str) -> str:
    transitions = {
        "new": {"switch_conversation": "read", "reply_hr": "replied"},
        "read": {"reply_hr": "replied"},
        "replied": {"check_followup": "hr_replied"},
        "hr_replied": {"reply_hr": "replied"},
    }
    stage_map = transitions.get(current, {})
    return stage_map.get(action_type, current)
