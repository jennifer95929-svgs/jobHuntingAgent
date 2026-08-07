"""V3 聊天工具 —— check_messages。"""
import os
import sys

V3_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.normpath(os.path.join(V3_ROOT, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _session():
    from browser.boss_session import BossSession
    global _s
    if _s is None:
        _s = BossSession()
    return _s


_s = None


def check_messages() -> dict:
    """检测未读 HR 消息数。"""
    return {"count": _session().check_chat_notifications()}
