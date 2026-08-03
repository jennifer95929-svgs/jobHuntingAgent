"""V2 工具层 —— 真实浏览器原子操作(CDP→真实 Chrome)。只读联调,不含投递。

每个动作不掺业务判断;决策全由模型看 context 决定。apply 等写操作暂未接入(只读联调)。
"""
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

LOOP_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(LOOP_ROOT, ".."))
if LOOP_ROOT not in sys.path:
    sys.path.insert(0, LOOP_ROOT)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    handler: Callable[..., Any]


_session = None


def session():
    global _session
    if _session is None:
        from browser.boss_session import BossSession
        _session = BossSession()
    return _session


def _close_stale_job_tabs():
    """清理 BOSS 岗位列表页堆积的旧 tab,只保留当前活动的搜索 tab。

    只动 'web/geek/jobs' 搜索列表 tab,不动 /chat、详情、用户其它页面。
    谁开的谁关 —— 与 V1 共享层无涉。
    """
    import json
    import urllib.request
    keep_ws = None
    try:
        keep_ws = getattr(session(), "_search_tab_ws", None)
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
                session().browser.close_tab(t["id"])
                closed += 1
            except Exception:
                pass
    return closed


def search_jobs(keyword: str, city: str) -> dict:
    """按关键词+城市在 BOSS 打开搜索页,并清理旧的搜索 tab。"""
    ok = session().search_jobs(keyword, city)
    _close_stale_job_tabs()
    return {"ok": ok, "keyword": keyword, "city": city}


def scan_page() -> dict:
    """提取当前搜索页岗位列表,并用 canvas 解码器还原薪资(反爬字体,尽力而为)。"""
    jobs = session().extract_job_list()
    decoded_salaries = _decode_salaries()
    if decoded_salaries:
        for j, sal in zip(jobs, decoded_salaries):
            if j.get("salary"):
                j["salary"] = sal
    return {"jobs": jobs}


def _decode_salaries() -> list:
    """在页面内执行 canvas 字形识别,把 PUA 薪资数字还原为可读文本。"""
    try:
        from salary_decode import build_decoder_js
        from browser.agent_browser_cli import AgentBrowser
        b = AgentBrowser()
        tab = b._get_boss_tab()
        if not tab:
            return []
        ws = tab["webSocketDebuggerUrl"]
        import asyncio, websockets
        from browser.agent_browser_cli import CDPClient

        async def go():
            async with websockets.connect(ws, close_timeout=10) as w:
                c = CDPClient(""); c._ws = w
                raw = await c.evaluate(build_decoder_js())
                import json as _j
                try:
                    return _j.loads(raw).get("decoded", [])
                except (TypeError, ValueError):
                    return []
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(go())
        finally:
            loop.close()
    except Exception:
        return []


def inspect_company(job_id: str) -> dict:
    """打开岗位详情页,只读检查公司规模是否 >=50 且非外包。不投递。"""
    eligible, reason = session().check_company_eligible(job_id)
    return {"job_id": job_id, "eligible": eligible, "reason": reason}


def apply(job_id: str, job_title: str = "", company: str = "", greeting: str = "") -> dict:
    """投递指定岗位。含硬安全护栏:去重、每日上限、验证码检测、公司规模校验。

    此处的'投哪家'由模型决定(传入 job_id);护栏是安全红线,不是业务取舍。
    """
    import history as hist

    if hist.reached_daily_limit():
        return {"applied": False, "reason": f"今日已到上限 {hist.today_count()}/{hist.MAX_APPLY_PER_DAY},停止投递"}
    if hist.already_applied(job_id):
        return {"applied": False, "reason": f"岗位 {job_id} 今日已投过,跳过"}
    if _check_captcha():
        return {"applied": False, "reason": "检测到验证码/风控,立即停止投递"}

    # 投递前再验一次合格性(规模>=50、非外包),不合格不投
    eligible, reason = session().check_company_eligible(job_id)
    if not eligible:
        return {"applied": False, "reason": f"公司不合格不投: {reason}"}

    # 投递动作可能较慢/偶发卡死,用看门狗线程超时兜底,绝不让整个 loop 挂掉。
    # 不用 multiprocessing:避免 pickling 持有 websocket 的 session。
    import threading

    box = {}

    def _run():
        try:
            box["ok"] = session().click_apply(job_id, job_title=job_title, company=company, reply_fn=_hr_reply_gen)
        except BaseException as e:
            box["err"] = str(e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=45)  # 最多等 45s,避免投递卡死拖垮整个循环
    if t.is_alive():
        return {"applied": False, "reason": "投递看门狗超时(可能页面卡住)"}
    if "err" in box:
        return {"applied": False, "reason": f"投递异常: {box['err']}"}
    ok = box.get("ok", False)

    if ok:
        hist.record_apply(job_id, company=company, title=job_title)
        return {"applied": True, "job_id": job_id, "today": hist.today_count()}
    return {"applied": False, "reason": "点击投递未成功"}


def _hr_reply_gen(hr_msg: str):
    """HR 首次回复时的自动应答(轮换模板防内容风控)。"""
    templates = [
        f"您好,感谢回复。我看了贵司这个岗位,和我的AI产品经理背景比较匹配,想进一步了解下团队和业务方向。",
        f"您好,很高兴收到回复。我在大模型落地的端到端交付上有过完整项目经验,如果方便的话可以聊聊机会。",
    ]
    import random
    return random.choice(templates)


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


def check_messages() -> dict:
    """检测未读 HR 消息数。"""
    return {"count": session().check_chat_notifications()}


def page_text() -> dict:
    """读取当前页文本内容(给模型看)。"""
    return {"text": session().get_page_text() or ""}


def screenshot() -> dict:
    path = os.path.join(LOOP_ROOT, "data", "shot.png")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    session().screenshot(path)
    return {"path": path}


def wait(minutes: int) -> dict:
    import time
    time.sleep(minutes * 60)
    return {"waited_minutes": minutes}


def done() -> dict:
    return {"status": "done"}


TOOL_SPECS: list[ToolSpec] = [
    ToolSpec("search_jobs", "按关键词+城市打开 BOSS 搜索页", {
        "type": "object",
        "properties": {
            "keyword": {"type": "string", "description": "搜索关键词,如 AI产品经理"},
            "city": {"type": "string", "description": "城市,如 深圳"},
        },
        "required": ["keyword", "city"],
    }, search_jobs),
    ToolSpec("scan_page", "提取当前搜索页的岗位列表(标题/薪资/公司/ID)", {"type": "object", "properties": {}}, scan_page),
    ToolSpec("inspect_company", "打开岗位详情页,只读检查公司规模>=50且非外包,不投递", {
        "type": "object",
        "properties": {"job_id": {"type": "string"}},
        "required": ["job_id"],
    }, inspect_company),
    ToolSpec("apply", "投递指定岗位(含去重/每日上限/验证码护栏)。只对 inspect_company 确认合格的岗位投", {
        "type": "object",
        "properties": {
            "job_id": {"type": "string", "description": "要投的岗位ID(必须来自 scan_page 或已验证的岗位)"},
            "job_title": {"type": "string", "description": "岗位标题(可选,便于记录)"},
            "company": {"type": "string", "description": "公司名(可选,便于记录)"},
        },
        "required": ["job_id"],
    }, apply),
    ToolSpec("check_messages", "检测未读 HR 消息数", {"type": "object", "properties": {}}, check_messages),
    ToolSpec("page_text", "读取当前页文本内容", {"type": "object", "properties": {}}, page_text),
    ToolSpec("screenshot", "截图保存", {"type": "object", "properties": {}}, screenshot),
    ToolSpec("wait", "暂停几分钟(防风控)", {
        "type": "object",
        "properties": {"minutes": {"type": "number"}},
        "required": ["minutes"],
    }, wait),
    ToolSpec("done", "本轮收工", {"type": "object", "properties": {}}, done),
]

REGISTRY: dict[str, ToolSpec] = {t.name: t for t in TOOL_SPECS}
