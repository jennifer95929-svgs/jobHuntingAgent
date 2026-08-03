"""V2 上下文 —— 用真实浏览器(CDP→真实 Chrome)打包现状给模型。零业务判断。"""
import json
import os

LOOP_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(LOOP_ROOT, ".."))
DATA_DIR = os.path.join(LOOP_ROOT, "data")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
TRACE_FILE = os.path.join(DATA_DIR, "trace.jsonl")

import sys
sys.path.insert(0, PROJECT_ROOT)


def capture() -> dict:
    """打包当前浏览器现状 + 会话状态。模型据此决定下一步。"""
    from browser.boss_session import BossSession
    s = BossSession()
    return {
        "url": current_url(s),
        "current_text": current_page_preview(s),   # 当前页文本摘要,让模型"看得见"
        "badge": unread_badge(s),
        "state": load_state(),
    }


def current_url(session=None) -> str:
    import urllib.request
    try:
        tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=3).read())
        for t in tabs:
            if t.get("type") == "page" and "zhipin" in (t.get("url") or ""):
                return t["url"]
        for t in tabs:
            if t.get("type") == "page":
                return t.get("url", "")
    except Exception:
        pass
    return ""


def current_page_preview(session=None, limit: int = 2000) -> str:
    """当前 BOSS 页文本,截断给模型看(控制 input 体积)。"""
    try:
        from browser.boss_session import BossSession
        s = session or BossSession()
        text = s.get_page_text() or ""
        return text[:limit]
    except Exception as e:
        return f"(读取页面失败: {e})"


def unread_badge(session=None) -> int:
    try:
        from browser.boss_session import BossSession
        s = session or BossSession()
        return s.check_chat_notifications()
    except Exception:
        return 0


def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {}
    with open(STATE_FILE, encoding="utf-8") as f:
        return json.load(f)


def save_trace(state: dict, call: dict, result: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRACE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"state": state, "call": call, "result": result}, ensure_ascii=False) + "\n")
