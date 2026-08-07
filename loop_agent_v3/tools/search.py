"""V3 搜索类工具 —— search_jobs / scan_page / page_text / screenshot。"""
import os
import sys

V3_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.normpath(os.path.join(V3_ROOT, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from guards import _close_stale_job_tabs

MAX_JOBS_RETURN = 8   # 单次返回给模型的最多岗位数,防 context 膨胀


def _session():
    from browser.boss_session import BossSession
    global _s
    if _s is None:
        _s = BossSession()
    return _s


_s = None


def search_jobs(keyword: str, city: str) -> dict:
    """按关键词+城市在 BOSS 打开搜索页,并清理旧的搜索 tab。"""
    s = _session()
    ok = s.search_jobs(keyword, city)
    _close_stale_job_tabs(s)
    return {"ok": ok, "keyword": keyword, "city": city}


def scan_page() -> dict:
    """提取当前搜索页岗位列表(截断 MAX_JOBS_RETURN 条),并解码 PUA 加密薪资。"""
    s = _session()
    # 进程内 session 可能还没有 _search_tab_ws(如 CLI 跨进程测试):
    # 自动找回当前打开的 BOSS 搜索 tab
    if not getattr(s, "_search_tab_ws", None):
        s._search_tab_ws = _find_search_tab_ws()
    jobs = s.extract_job_list()
    decoded = _decode_salaries()
    if decoded:
        for j, sal in zip(jobs, decoded):
            if j.get("salary"):
                j["salary"] = sal
    jobs = jobs[:MAX_JOBS_RETURN]
    return {"jobs": jobs}


def _find_search_tab_ws():
    """找到当前打开的 BOSS 岗位搜索 tab 的 websocket url。"""
    import json
    import urllib.request
    try:
        tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=3).read())
        for t in tabs:
            if t.get("type") == "page" and "web/geek/jobs" in (t.get("url") or ""):
                return t.get("webSocketDebuggerUrl")
    except Exception:
        pass
    return None


def _decode_salaries() -> list:
    """解码 BOSS 加密薪资: 固定映射优先, 字体解析兜底。"""
    try:
        from salary_decode import decode_salaries_from_page
        return decode_salaries_from_page()
    except Exception:
        return []


def page_text() -> dict:
    """读取当前页文本内容(截断给模型看)。"""
    s = _session()
    text = s.get_page_text() or ""
    return {"text": text[:2000]}


def screenshot() -> dict:
    path = os.path.join(V3_ROOT, "data", "shot.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _session().screenshot(path)
    return {"path": path}
