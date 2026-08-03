"""V2 投递历史 —— 读写真实 data/history.json,复用同一账号数据。

纯数据存取 + 去重 + 计数;不掺"投哪家"的决策(那归模型)。这些是硬安全护栏。
"""
import json
import os
import time
from datetime import date

LOOP_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(LOOP_ROOT, ".."))
HISTORY_FILE = os.path.join(PROJECT_ROOT, "data", "history.json")
MAX_APPLY_PER_DAY = 50


def _load() -> dict:
    today = str(date.today())
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            h = json.load(f)
            h.setdefault(today, {"applied": [], "chats": []})
            return h
    except (json.JSONDecodeError, IOError):
        return {today: {"applied": [], "chats": []}}


def _save(h: dict) -> None:
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)


def today_count() -> int:
    h = _load()
    return len(h.get(str(date.today()), {}).get("applied", []))


def already_applied(job_id: str) -> bool:
    h = _load()
    return any(a.get("id") == job_id for a in h.get(str(date.today()), {}).get("applied", []))


def reached_daily_limit() -> bool:
    return today_count() >= MAX_APPLY_PER_DAY


def record_apply(job_id: str, keyword: str = "", city: str = "", company: str = "", title: str = "") -> None:
    h = _load()
    today = str(date.today())
    h[today]["applied"].append({
        "id": job_id, "keyword": keyword, "city": city,
        "page": 1, "time": time.strftime("%H:%M:%S"),
        "company": company, "title": title,
    })
    _save(h)
