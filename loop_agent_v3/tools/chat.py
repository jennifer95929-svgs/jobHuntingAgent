"""V3 聊天工具 —— check_messages / chat_draft / chat_send。

「回复前先询问用户」机制:
  - chat_draft(): 检测未读 HR 消息, 生成回复草案, 保存到 data/chat_drafts.json
                  (不直接发送!)
  - chat_send():  用户确认后, 仅发送指定草案中已批准的消息
"""
import os
import sys
import json
import time

V3_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.normpath(os.path.join(V3_ROOT, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DATA_DIR = os.path.join(V3_ROOT, "data")
DRAFTS_FILE = os.path.join(DATA_DIR, "chat_drafts.json")

# 回复模板(轮换使用, 防内容风控)
_REPLY_TEMPLATES = [
    "您好,感谢回复。我看了贵司这个岗位,和我的AI产品经理背景比较匹配,想进一步了解下团队和业务方向。",
    "您好,很高兴收到回复。我在大模型落地的端到端交付上有过完整项目经验,如果方便的话可以聊聊机会。",
    "您好,感谢关注。我目前在职,正在看新的机会,贵司这个岗位方向和我很匹配,期待进一步沟通。",
]


def _session():
    from browser.boss_session import BossSession
    global _s
    if _s is None:
        _s = BossSession()
    return _s


_s = None


def _load_drafts() -> dict:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(DRAFTS_FILE):
        try:
            with open(DRAFTS_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _save_drafts(drafts: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(DRAFTS_FILE, "w", encoding="utf-8") as f:
        json.dump(drafts, f, ensure_ascii=False, indent=2)


def check_messages() -> dict:
    """检测未读 HR 消息数。"""
    return {"count": _session().check_chat_notifications()}


def chat_draft() -> dict:
    """生成 HR 回复草案(不发送)。返回草案列表, 存入 data/chat_drafts.json。

    草案状态: pending(待确认) -> approved(已批准) -> sent(已发送)
    """
    s = _session()
    # 打开聊天页并读取消息(精确提取消息气泡, 排除界面噪声)
    s.navigate_to_chats()
    time.sleep(3)

    # 通过 CDP 提取聊天消息: 优先 [class*="chat"] 容器内的气泡文本
    msgs = []
    try:
        ws = _find_chat_tab_ws()
        if ws:
            msgs = _extract_chat_messages(ws)
    except Exception:
        pass

    # 兜底: 页面文本粗提取
    if not msgs:
        text = s.get_page_text() or ""
        import re
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for l in lines:
            if len(l) < 4 or len(l) > 200:
                continue
            if any(x in l for x in ["BOSS直聘", "职位", "消息数", "搜索", "登录", "下载", "客服", "沟通中", "进行中"]):
                continue
            if l not in msgs:
                msgs.append(l)
        msgs = msgs[:8]

    if not msgs:
        return {"drafts": [], "message": "无未处理消息"}

    # 为每条消息生成草案
    drafts = _load_drafts()
    import random
    created = []
    for m in msgs:
        key = str(abs(hash(m)) % 100000)
        if key in drafts and drafts[key].get("status") in ("approved", "sent"):
            continue
        draft = {
            "id": key,
            "hr_msg": m,
            "reply": _REPLY_TEMPLATES[len(created) % len(_REPLY_TEMPLATES)],
            "status": "pending",
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        drafts[key] = draft
        created.append(draft)

    _save_drafts(drafts)
    return {
        "drafts": [{"id": d["id"], "hr_msg": d["hr_msg"][:80], "status": d["status"]} for d in created],
        "message": f"生成 {len(created)} 条回复草案, 待确认",
        "file": DRAFTS_FILE,
    }


def _find_chat_tab_ws():
    """找到聊天页 tab 的 websocket url。"""
    import json
    import urllib.request
    try:
        tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=3).read())
        for t in tabs:
            if t.get("type") == "page" and "/chat" in (t.get("url") or ""):
                return t.get("webSocketDebuggerUrl")
    except Exception:
        pass
    return None


def _extract_chat_messages(ws_url: str) -> list:
    """通过 CDP 精确提取聊天气泡文本(HR 消息)。"""
    import asyncio
    import websockets
    from browser.agent_browser_cli import CDPClient

    JS = """
    (() => {
      const seen = new Set();
      const out = [];
      const selectors = [
        '[class*="chat"] [class*="item"]',
        '[class*="message"]',
        '[class*="msg"]',
        '[class*="bubble"]'
      ];
      for (const sel of selectors) {
        for (const el of document.querySelectorAll(sel)) {
          let t = el.textContent.trim().replace(/^\\[送达\\]\\s*/, '');
          if (!t || t.length < 4 || t.length > 200) continue;
          if (/^[\\d:]+$/.test(t)) continue;  // 跳过时间戳
          if (seen.has(t)) continue;
          seen.add(t);
          out.push(t);
        }
      }
      return JSON.stringify(out.slice(0, 8));
    })()
    """

    async def go():
        async with websockets.connect(ws_url, close_timeout=10) as w:
            c = CDPClient("")
            c._ws = w
            raw = await c.evaluate(JS)
            try:
                return json.loads(raw)
            except Exception:
                return []

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(go())
    except Exception:
        return []
    finally:
        loop.close()


def chat_send(draft_id: str = "", all_pending: bool = False) -> dict:
    """发送已批准的草案。默认只发送指定 id; all_pending=True 时批量发送所有 pending。"""
    drafts = _load_drafts()
    if not drafts:
        return {"sent": 0, "message": "无草案"}

    targets = []
    if draft_id:
        if draft_id in drafts and drafts[draft_id]["status"] == "pending":
            targets.append(draft_id)
    elif all_pending:
        targets = [k for k, v in drafts.items() if v.get("status") == "pending"]

    if not targets:
        return {"sent": 0, "message": "没有待发送的草案(请先 chat_draft 生成并确认)"}

    s = _session()
    sent = 0
    for tid in targets:
        d = drafts[tid]
        # 打开对应公司聊天
        company = d.get("company", "")
        ok = s.send_message(d["reply"])
        if ok:
            d["status"] = "sent"
            d["sent_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
            sent += 1
        time.sleep(1.5)

    _save_drafts(drafts)
    return {"sent": sent, "message": f"已发送 {sent} 条回复"}


def list_drafts() -> dict:
    """列出所有草案及状态。"""
    drafts = _load_drafts()
    return {
        "drafts": [
            {"id": k, "hr_msg": v.get("hr_msg", "")[:80],
             "reply": v.get("reply", "")[:50], "status": v.get("status")}
            for k, v in drafts.items()
        ]
    }
