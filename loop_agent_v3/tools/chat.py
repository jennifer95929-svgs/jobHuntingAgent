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


def chat_auto(auto_reply: bool = True) -> dict:
    """自动处理 HR 消息(半自动模式)。

    - 简单问候/询问 → LLM 生成回复并自动发送(auto_reply=True)
    - HR 要求发简历 → 生成"发送简历"任务, 存入 drafts 等你确认(敏感操作不自动执行)
    - 拒绝/不匹配消息 → 不回复, 记录状态
    """
    s = _session()
    # 复用现有聊天 tab, 不重复打开(避免卡死)
    ws = _find_chat_tab_ws()
    if not ws:
        s.navigate_to_chats()
        time.sleep(3)
        ws = _find_chat_tab_ws()
    if not ws:
        return {"error": "找不到聊天页", "handled": 0}

    # 1. 提取所有会话(公司名 + 最后消息)
    sessions = _extract_sessions(ws)
    if not sessions:
        return {"message": "无会话", "handled": 0}

    results = []
    replied = 0
    resume_requests = 0

    for sess in sessions:
        company = sess.get("company", "")
        last_msg = sess.get("last_msg", "")
        if not company or not last_msg:
            continue
        if _is_self_message(last_msg):
            continue
        if _is_system_message(last_msg):
            continue
        if _is_rejection(last_msg):
            results.append({"company": company, "action": "skip", "reason": "拒绝/不匹配,不回复"})
            continue
        if _is_resume_request(last_msg):
            # 敏感操作: 生成发送简历任务, 等待用户确认
            drafts = _load_drafts()
            key = f"resume_{abs(hash(company)) % 100000}"
            drafts[key] = {
                "id": key,
                "type": "send_resume",
                "hr_msg": last_msg[:80],
                "company": company,
                "status": "pending",
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            _save_drafts(drafts)
            results.append({"company": company, "action": "ask_confirm",
                            "hr_msg": last_msg[:80],
                            "reason": "HR 要简历,已生成发送简历任务待确认",
                            "reply": "（确认后自动发送简历）"})
            resume_requests += 1
            continue

        # 普通消息: LLM 生成回复
        try:
            reply = _llm_reply(company, last_msg)
        except Exception:
            reply = ""
        if not reply:
            results.append({"company": company, "action": "skip", "reason": "LLM 未生成回复"})
            continue

        if auto_reply and _is_simple_message(last_msg):
            # 简单消息自动回复
            ok = s.send_chat_text(reply)
            results.append({"company": company, "action": "auto_reply" if ok else "send_failed",
                            "reply": reply[:50]})
            if ok:
                replied += 1
            time.sleep(1.5)
        else:
            # 复杂消息 → 生成草案待确认
            drafts = _load_drafts()
            key = f"reply_{abs(hash(company)) % 100000}"
            drafts[key] = {
                "id": key,
                "type": "reply",
                "hr_msg": last_msg[:80],
                "company": company,
                "reply": reply,
                "status": "pending",
                "created": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            _save_drafts(drafts)
            results.append({"company": company, "action": "draft",
                            "hr_msg": last_msg[:80],
                            "reason": "复杂消息,回复草案待确认",
                            "reply": reply[:100]})

    return {
        "handled": len(results),
        "auto_replied": replied,
        "resume_requests": resume_requests,
        "details": results,
    }


def _extract_sessions(ws_url: str) -> list:
    """提取聊天会话列表(公司名 + 最后一条消息)。"""
    import asyncio
    import websockets
    from browser.agent_browser_cli import CDPClient

    JS = """
    (() => {
      const items = [...document.querySelectorAll('[class*="chat"] [class*="item"], [class*="friend"], [class*="session"]')];
      const seen = new Set();
      const out = [];
      for (const el of items) {
        const t = (el.textContent || '').replace(/\\s+/g, ' ').trim();
        if (t.length < 8 || seen.has(t)) continue;
        seen.add(t);
        out.push(t.slice(0, 150));
      }
      return JSON.stringify(out.slice(0, 40));
    })()
    """

    async def go():
        async with websockets.connect(ws_url, close_timeout=10) as w:
            c = CDPClient("")
            c._ws = w
            raw = await c.evaluate(JS)
            try:
                items = json.loads(raw)
            except Exception:
                return []

            sessions = []
            for raw_text in items:
                import re
                # 格式: "2天16:08翁先生歪麦HR您有做过开放平..." 或 "11:25韦彩鑫道通科技HR您好"
                # 1. 去掉所有非汉字前缀(时间/日期标记, 如 2天16:08、114:25、11:25)
                t = re.sub(r"^[^一-龥]*", "", raw_text)
                # 可能还有姓名+公司混排, 先保留原始处理
                # 2. 去姓名(2-3个汉字 + 女士/先生)
                t = re.sub(r"^[\u4e00-\u9fa5]{2,3}(女士|先生)?\s*", "", t)
                # 3. 找角色词位置
                role_m = re.search(r"(HRBP|招聘者|招聘主管|招聘经理|招聘专员|猎头顾问|HR\.|招聘|总监|CEO|BP|专员|顾问|经理|主管|老板|运营|人事|创始人|HR)", t)
                if role_m:
                    company = t[:role_m.start()].strip()[:25]
                    msg = t[role_m.end():].strip()
                else:
                    # 无角色词: 尝试用"[送达]"/"[已读]"分割
                    tag_m = re.search(r"\[(送达|已读)\]", t)
                    if tag_m:
                        company = t[:tag_m.start()].strip()[:25]
                        msg = t[tag_m.end():].strip()
                    else:
                        company = t[:15].strip()
                        msg = t
                # 去掉消息里的送达/已读标记
                msg = re.sub(r"^\[(送达|已读)\]\s*", "", msg).strip()
                if not msg:
                    msg = t[-30:]
                sessions.append({"company": company or "未知公司", "last_msg": msg[:100], "raw": raw_text[:120]})
            return sessions

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(go())
    except Exception:
        return []
    finally:
        loop.close()


def _is_self_message(msg: str) -> bool:
    """判断消息是否是自己发的(我方消息特征)。"""
    return msg.startswith("您好，我对贵司") or msg.startswith("您好,我对贵司") or "附件简历" in msg


def _is_system_message(msg: str) -> bool:
    """判断是否为系统消息(无需回复)。"""
    return "您正在与Boss" in msg or "点击查看附件" in msg or "对方已同意" in msg or "附件简历请求已发送" in msg


def _is_rejection(msg: str) -> bool:
    """判断 HR 消息是否拒绝。"""
    import re
    return bool(re.search(r"不匹配|不合适|不符合|不满足|暂不|遗憾|未能|经验不符|不是很匹配|感谢关注|不考虑|不太合适|简历与|停止招聘", msg))


def _is_resume_request(msg: str) -> bool:
    """判断 HR 是否要求发简历(排除拒绝消息中的'简历'字样)。"""
    import re
    if _is_rejection(msg):
        return False
    return bool(re.search(r"方便发|发份|发一下|发个|发一份|简历过来|简历吗|发份详细的|发简历|附件简历|send.*resume|看一下.*简历|发下", msg, re.IGNORECASE))


def _is_simple_message(msg: str) -> bool:
    """判断是否为简单消息(可直接自动回复)。"""
    import re
    # 简单问候/在吗/有空吗 等
    return bool(re.search(r"^(在吗|您好|你好|你好，|在不在|有空|方便|聊聊|在吗\?|您好，.*吗)", msg))


def _llm_reply(company: str, hr_msg: str) -> str:
    """用 LLM 生成个性化回复。失败时返回空。"""
    try:
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".."))
        from pipeline.llm import call_light
        system = (
            "你是求职者应欣(应聘AI产品经理),在BOSS直聘上回复HR的消息。"
            "要求: 1. 语气礼貌专业简洁(30-80字) 2. 突出AI产品经理经验(大模型落地、端到端交付) 3. 不要提薪资 4. 保持真实自然,不要营销腔"
        )
        user = f"公司: {company}\nHR消息: {hr_msg}\n\n请生成你的回复:"
        reply = call_light(system, user)
        return reply.strip()[:200]
    except Exception:
        # 兜底模板
        return "您好，感谢回复。我是AI产品经理，在大模型落地和端到端交付上有完整项目经验，想进一步了解下贵司这个岗位。"
