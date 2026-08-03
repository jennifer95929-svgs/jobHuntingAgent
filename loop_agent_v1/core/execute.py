import json
import time
import urllib.request
import asyncio
import websockets

CHAT_URL = "https://www.zhipin.com/web/geek/chat"


def _get_ws():
    tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=3).read())
    for t in tabs:
        if t.get("type") == "page" and CHAT_URL in t.get("url", ""):
            return t.get("webSocketDebuggerUrl")
    return None


def _load_resume() -> str:
    try:
        from resume.profile import profile_summary
        return profile_summary()
    except Exception:
        return ""


def build_instruction(action: dict) -> dict:
    return {
        "action_id": action.get("id"),
        "type": action.get("type"),
        "target": action.get("target", {}),
        "context": {
            "resume_summary": _load_resume() if action.get("type") in ("reply_hr",) else "",
        },
        "verify_rule": _verify_rule_for(action.get("type"))
    }


def _verify_rule_for(action_type: str) -> dict:
    rules = {
        "scan_conversations": {"check": "badge_cleared", "expected": True},
        "switch_conversation": {"check": "chat_header_matches", "expected": True},
        "reply_hr": {"check": "textarea_empty", "expected": True},
        "click_exchange_card": {"check": "card_gone", "expected": True},
        "check_followup": {"check": "new_message", "expected": True},
    }
    return rules.get(action_type, {"check": "none", "expected": True})


def inject_prompt(instruction: dict):
    print(f"[inject] {json.dumps(instruction, ensure_ascii=False)[:200]}")


async def _verify_by_dom(verify_rule: dict) -> bool:
    ws = _get_ws()
    if not ws:
        return False
    async with websockets.connect(ws, close_timeout=10) as wss:
        check = verify_rule.get("check")

        if check == "badge_cleared":
            js = """
            (() => {
                const badge = document.querySelector('[class*="badge"], [class*="msg-num"]');
                return badge ? parseInt(badge.textContent) || 1 : 0;
            })()
            """
            val = await _eval_dom(wss, js)
            return int(val) == 0 if val is not None else False

        if check == "chat_header_matches":
            js = """
            (() => {
                const header = document.querySelector('[class*="chat-header"], [class*="dialog-header"]');
                return header ? header.textContent.trim() : '';
            })()
            """
            val = await _eval_dom(wss, js)
            return bool(val)

        if check == "textarea_empty":
            js = """
            (() => {
                const ta = document.querySelector('textarea');
                return ta ? ta.value.length : -1;
            })()
            """
            val = await _eval_dom(wss, js)
            try:
                return int(val) == 0
            except (ValueError, TypeError):
                return False

        if check == "card_gone":
            js = """
            (() => {
                const cards = document.querySelectorAll('[class*="exchange"], [class*="card"]');
                return cards.length;
            })()
            """
            val = await _eval_dom(wss, js)
            try:
                return int(val) == 0
            except (ValueError, TypeError):
                return False

    return True


async def _eval_dom(ws, js: str):
    import json as _json
    await ws.send(_json.dumps({"id": 1, "method": "Runtime.evaluate", "params": {"expression": js, "returnByValue": True}}))
    while True:
        resp = _json.loads(await ws.recv())
        if resp.get("id") == 1:
            result = resp.get("result", {}).get("result", {})
            if "value" in result:
                return result["value"]
            if "description" in result:
                return result["description"]
            return None


async def _fallback_cdp(action: dict) -> bool:
    ws = _get_ws()
    if not ws:
        return False
    async with websockets.connect(ws, close_timeout=10) as wss:
        atype = action.get("type")

        if atype == "switch_conversation":
            company = action.get("target", {}).get("company", "")
            js = f"""
            (() => {{
                const lis = document.querySelectorAll('li');
                for (const li of lis) {{
                    if (li.textContent.includes({json.dumps(company)})) {{
                        const r = li.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0) {{
                            li.scrollIntoView({{block: 'center'}});
                            li.click();
                            return true;
                        }}
                    }}
                }}
                return false;
            }})()
            """
            val = await _eval_dom(wss, js)
            return val == "true" or val is True

        if atype == "reply_hr":
            text = action.get("context", {}).get("reply_draft", "")
            await _eval_dom(wss, "document.querySelector('textarea')?.focus()")
            await asyncio.sleep(0.2)
            for ch in text:
                await wss.send(json.dumps({"id": 10, "method": "Input.insertText", "params": {"text": ch}}))
                await asyncio.sleep(0.005)
            await asyncio.sleep(0.5)
            await wss.send(json.dumps({"id": 11, "method": "Input.dispatchKeyEvent", "params": {"type": "rawKeyDown", "key": "Enter", "windowsVirtualKeyCode": 13, "code": "Enter"}}))
            await asyncio.sleep(0.05)
            await wss.send(json.dumps({"id": 12, "method": "Input.dispatchKeyEvent", "params": {"type": "keyUp", "key": "Enter", "windowsVirtualKeyCode": 13, "code": "Enter"}}))
            await asyncio.sleep(1)
            val = await _eval_dom(wss, "document.querySelector('textarea')?.value.length || 0")
            try:
                return int(val) == 0
            except (ValueError, TypeError):
                return False

    return False


def execute_action(action: dict) -> dict:
    from core.state import update_conversation_state

    instruction = build_instruction(action)
    inject_prompt(instruction)
    time.sleep(3)

    loop = asyncio.new_event_loop()
    try:
        ok = loop.run_until_complete(_verify_by_dom(instruction.get("verify_rule", {})))
    except Exception:
        ok = False
    finally:
        loop.close()

    if ok:
        update_conversation_state(action, {"status": "success"})
        return {"status": "success", "action_id": action.get("id")}

    inject_prompt(instruction)
    time.sleep(3)
    loop = asyncio.new_event_loop()
    try:
        ok = loop.run_until_complete(_verify_by_dom(instruction.get("verify_rule", {})))
    except Exception:
        ok = False
    finally:
        loop.close()

    if ok:
        update_conversation_state(action, {"status": "success"})
        return {"status": "success", "retried": True, "action_id": action.get("id")}

    loop = asyncio.new_event_loop()
    try:
        ok = loop.run_until_complete(_fallback_cdp(action))
    except Exception:
        ok = False
    finally:
        loop.close()

    if ok:
        update_conversation_state(action, {"status": "success"})
        return {"status": "success", "fallback": True, "action_id": action.get("id")}

    update_conversation_state(action, {"status": "failed"})
    return {"status": "failed", "action_id": action.get("id")}
