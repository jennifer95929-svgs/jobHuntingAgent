import json
import time
import os
import random
import threading
import urllib.request
from datetime import date
from concurrent.futures import ThreadPoolExecutor, TimeoutError

PROJECT_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))

from config import SEARCH_KEYWORDS, CITIES, MAX_APPLY_PER_DAY
from pipeline.filter import batch_filter


import signal

def _call_with_timeout(fn, timeout: int = 15):
    deadline = time.time() + timeout
    t = threading.Thread(target=lambda: setattr(_call_with_timeout, '_result', fn()), daemon=True)
    _call_with_timeout._result = None
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        raise TimeoutError(f"超时 {timeout}s")
    r = _call_with_timeout._result
    if isinstance(r, Exception):
        raise r
    return r


def _check_captcha() -> bool:
    try:
        tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=3).read())
        for t in tabs:
            if "captcha" in t.get("url", "") or "gtimg" in t.get("url", ""):
                return True
    except Exception:
        pass
    return False


def _close_stale_tabs(boss_session):
    try:
        tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=3).read())
        boss_ids = set()
        for t in tabs:
            if t.get("type") == "page" and "zhipin" in t.get("url", ""):
                boss_ids.add(t["id"])
        import asyncio, websockets
        from browser.agent_browser_cli import CDPClient
        browser_ws = json.loads(urllib.request.urlopen(
            "http://localhost:9222/json/version", timeout=3).read()
        )["webSocketDebuggerUrl"]
        async def close_all():
            async with websockets.connect(browser_ws, close_timeout=5) as ws:
                c = CDPClient(""); c._ws = ws
                for tid in boss_ids:
                    await c.send("Target.closeTarget", {"targetId": tid})
        keep_ids = set()
        if boss_session._search_tab_ws:
            for t in tabs:
                if t.get("webSocketDebuggerUrl") == boss_session._search_tab_ws:
                    keep_ids.add(t["id"])
        async def close_except():
            async with websockets.connect(browser_ws, close_timeout=5) as ws:
                c = CDPClient(""); c._ws = ws
                for tid in boss_ids:
                    if tid not in keep_ids:
                        await c.send("Target.closeTarget", {"targetId": tid})
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(close_except())
        finally:
            loop.close()
    except Exception:
        pass

_search_state = {"keyword_idx": 0, "city_idx": 0, "page": 0}


def _reset_search():
    _search_state["keyword_idx"] = 0
    _search_state["city_idx"] = 0
    _search_state["page"] = 0


def _load_history():
    path = os.path.join(PROJECT_ROOT, "data", "history.json")
    today = str(date.today())
    try:
        with open(path) as f:
            h = json.load(f)
            h.setdefault(today, {"applied": [], "chats": []})
            return h
    except (json.JSONDecodeError, IOError):
        return {today: {"applied": [], "chats": []}}


def _save_history(h: dict):
    path = os.path.join(PROJECT_ROOT, "data", "history.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)


def _today_count() -> int:
    h = _load_history()
    today = str(date.today())
    return len(h.get(today, {}).get("applied", []))


def _already_applied(h: dict, job_id: str) -> bool:
    today = str(date.today())
    for a in h.get(today, {}).get("applied", []):
        if a.get("id") == job_id:
            return True
    return False


def _next_page(boss_session):
    ws = boss_session._search_tab_ws
    if not ws:
        return
    js = """
    (() => {
        const nextBtn = document.querySelector('.page-next, .next, a:has(.icon-arrow-right), [class*="next"]');
        if (nextBtn) { nextBtn.click(); return true; }
        return false;
    })()
    """
    boss_session.browser.evaluate_in_tab(ws, js)


def _browse_and_pick(boss_session, jobs: list):
    if not jobs:
        return None
    return jobs[0]


def try_apply(boss_session) -> dict:
    result = {"applied": 0, "total": 0, "done": False}

    count = _today_count()
    print(f"  [apply] 今日已投: {count}/{MAX_APPLY_PER_DAY}", flush=True)
    if count >= MAX_APPLY_PER_DAY:
        result["done"] = True
        return result

    if _check_captcha():
        print(f"  [apply] ⚠️ 检测到验证码，跳过本轮", flush=True)
        result["done"] = True
        return result

    ks = _search_state["keyword_idx"]
    cs = _search_state["city_idx"]
    pg = _search_state["page"]

    if ks >= len(SEARCH_KEYWORDS):
        _reset_search()
        result["done"] = True
        return result

    keyword = SEARCH_KEYWORDS[ks]
    city = CITIES[cs]
    history = _load_history()

    print(f"  [apply] 搜索: {keyword} @ {city} (kw={ks} city={cs} pg={pg})", flush=True)

    if pg == 0:
        print(f"  [apply] 清理旧tab...", flush=True)
        _close_stale_tabs(boss_session)
        print(f"  [apply] search_jobs 开始...", flush=True)
        ok = boss_session.search_jobs(keyword, city)
        print(f"  [apply] search_jobs 结果: {ok}", flush=True)
        time.sleep(2)

    applied_in_round = 0
    pages_checked = 0

    for _ in range(3):
        pages_checked += 1
        count = _today_count()
        if count >= MAX_APPLY_PER_DAY:
            print(f"  [apply] 已达上限 {count}", flush=True)
            break

        jobs = boss_session.extract_job_list()
        print(f"  [apply] 第{_+1}页: {len(jobs)} 个岗位", flush=True)
        if not jobs:
            print(f"  [apply] 无岗位，跳出", flush=True)
            break

        before = len(jobs)
        jobs = [j for j in jobs if j.get("id") and not _already_applied(history, j["id"])]
        skipped = before - len(jobs)
        if skipped:
            print(f"  [apply] 过滤已投: {skipped} 个", flush=True)

        if not jobs:
            print(f"  [apply] 本页无新岗位，翻页", flush=True)
            _next_page(boss_session)
            _search_state["page"] += 1
            continue

        try:
            filtered = _call_with_timeout(lambda: batch_filter(jobs), timeout=20)
            if filtered:
                jobs = filtered
                print(f"  [apply] LLM过滤后: {len(jobs)} 个", flush=True)
            else:
                print(f"  [apply] LLM过滤无结果，使用全部岗位", flush=True)
        except TimeoutError:
            print(f"  [apply] LLM过滤超时，使用全部岗位", flush=True)
        except Exception as e:
            print(f"  [apply] LLM过滤失败: {e}，使用全部岗位", flush=True)

        if not jobs:
            _next_page(boss_session)
            _search_state["page"] += 1
            continue

        eligible = []
        for job in jobs[:5]:
            jid = job["id"]
            ok, reason = boss_session.check_company_eligible(jid)
            print(f"  [apply] 公司验证 {job.get('company','')[:15]}: {ok} {reason}", flush=True)
            if ok:
                eligible.append(job)

        if not eligible:
            print(f"  [apply] 无可投公司，翻页", flush=True)
            _next_page(boss_session)
            _search_state["page"] += 1
            continue

        pick = _browse_and_pick(boss_session, eligible)
        if not pick:
            print(f"  [apply] 浏览未选中，翻页", flush=True)
            _next_page(boss_session)
            _search_state["page"] += 1
            continue

        job_id = pick["id"]
        title = pick.get("title", "")
        company = pick.get("company", "")
        print(f"  [apply] 投递: {title} @ {company}", flush=True)

        try:
            ok = boss_session.click_apply(job_id, job_title=title, company=company)
            print(f"  [apply] click_apply: {ok}", flush=True)
        except Exception as e:
            print(f"  [apply] click_apply异常: {e}", flush=True)
            ok = False

        if ok:
            today = str(date.today())
            history.setdefault(today, {"applied": [], "chats": []})
            history[today]["applied"].append({
                "id": job_id, "keyword": keyword, "city": city,
                "page": pg + 1, "time": time.strftime("%H:%M:%S"),
                "company": company, "title": title,
            })
            _save_history(history)
            applied_in_round += 1
            print(f"  [apply] ✅ 投递成功 ({_today_count()}/{MAX_APPLY_PER_DAY})", flush=True)

        _next_page(boss_session)
        _search_state["page"] += 1

    _search_state["city_idx"] += 1
    if _search_state["city_idx"] >= len(CITIES):
        _search_state["city_idx"] = 0
        _search_state["keyword_idx"] += 1
    _search_state["page"] = 0

    result["applied"] = applied_in_round
    result["total"] = _today_count()
    print(f"  [apply] 本轮结果: {result}", flush=True)
    return result
