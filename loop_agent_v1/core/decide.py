from datetime import date as _date

from core.state import load_state

MAX_APPLY_PER_DAY = 50


def _today_apply_count() -> int:
    import json, os
    path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "history.json")
    try:
        with open(path) as f:
            h = json.load(f)
            return len(h.get(str(_date.today()), {}).get("applied", []))
    except:
        return 0


def build_plan(badge: int, is_tick: bool) -> list:
    actions = []

    if badge > 0:
        actions.append({
            "id": "check_unread",
            "type": "scan_conversations",
            "target": {},
            "priority": "high",
            "reason": f"检测到 {badge} 条未读消息"
        })

    if is_tick:
        state = load_state()
        today = state.get(str(_date.today()), {})
        conversations = today.get("conversations", {})

        for company, conv in conversations.items():
            if conv.get("stage") == "replied" and conv.get("verified"):
                actions.append({
                    "id": f"followup_{company}",
                    "type": "check_followup",
                    "target": {"company": company},
                    "priority": "low",
                    "reason": f"定时检查 {company} 是否有新回复"
                })

        applied = _today_apply_count()
        if applied < MAX_APPLY_PER_DAY:
            actions.append({
                "id": "daily_apply",
                "type": "apply_jobs",
                "target": {},
                "priority": "medium",
                "reason": f"今日已投 {applied}/{MAX_APPLY_PER_DAY}"
            })

    return actions
