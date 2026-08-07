"""V3 护栏层 —— 硬安全红线,不掺业务决策。

apply 前的 4 道护栏按固定顺序执行,任一道不过即拒:
1. 每日上限(50)
2. 跨日去重(同一 job_id 不重复投)
3. 验证码/风控检测(检测到即停,绝不重试)
4. 公司合格性复核(规模>=50、非外包、非404下架)
"""
import sys
import os

V3_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(V3_ROOT, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import history as hist


def check_before_apply(session, job_id: str) -> dict:
    """投递前护栏检查。返回 {"ok": True} 或 {"ok": False, "reason": str}。"""
    if hist.reached_daily_limit():
        return {"ok": False, "reason": f"limit|今日已到上限 {hist.today_count()}/{hist.MAX_APPLY_PER_DAY},停止投递"}
    if hist.already_applied(job_id):
        return {"ok": False, "reason": f"duplicate|岗位 {job_id} 已投过,跳过"}
    if _check_captcha():
        return {"ok": False, "reason": "captcha|检测到验证码/风控,立即停止投递"}

    eligible, reason = session.check_company_eligible(job_id)
    if not eligible:
        if reason and "下架" in reason:
            return {"ok": False, "reason": f"dead|公司不合格不投: {reason}"}
        return {"ok": False, "reason": f"company|公司不合格不投: {reason}"}
    return {"ok": True}


def _check_captcha() -> bool:
    import json
    import urllib.request
    try:
        tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=3).read())
        for t in tabs:
            if "captcha" in t.get("url", "") or "gtimg" in t.get("url", ""):
                return True
    except Exception:
        pass
    return False


def _close_stale_job_tabs(session) -> int:
    """清理 BOSS 岗位列表页堆积的旧 tab,只保留当前活动的搜索 tab。"""
    import json
    import urllib.request
    keep_ws = None
    try:
        keep_ws = getattr(session, "_search_tab_ws", None)
    except Exception:
        pass
    try:
        tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=3).read())
    except Exception:
        return 0

    closed = 0
    for t in tabs:
        if (t.get("type") == "page"
                and "web/geek/jobs" in (t.get("url") or "")
                and (t.get("webSocketDebuggerUrl") or "") != (keep_ws or "")):
            try:
                session.browser.close_tab(t["id"])
                closed += 1
            except Exception:
                pass
    return closed
