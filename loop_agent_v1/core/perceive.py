import json
import urllib.request
import asyncio
import websockets

CHAT_URL = "https://www.zhipin.com/web/geek/chat"


def _get_tab_ws():
    tabs = json.loads(urllib.request.urlopen("http://localhost:9222/json", timeout=3).read())
    for t in tabs:
        if t.get("type") == "page" and CHAT_URL in t.get("url", ""):
            return t.get("webSocketDebuggerUrl")
    return None


def _cdp_client(ws: str):
    from driver.cdp_bridge import CDPClient
    return CDPClient(ws)


def perceive_badge() -> int:
    ws = _get_tab_ws()
    if not ws:
        return -1
    try:
        async def do():
            async with websockets.connect(ws, close_timeout=5) as wss:
                c = type("C", (), {"_ws": wss, "_msg_id": 0, "send": lambda s, m, p=None: None})()
                c._ws = wss
                val = await _eval_js(wss, """
                (() => {
                    const badge = document.querySelector('[class*="badge"], [class*="msg-num"], .unread, [class*="unread"]');
                    if (badge) {
                        const n = parseInt(badge.textContent);
                        return isNaN(n) ? 1 : n;
                    }
                    const items = document.querySelectorAll('li[class*="unread"]');
                    return items.length || 0;
                })()
                """)
                return int(val) if val is not None else 0
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(do())
        finally:
            loop.close()
    except Exception:
        return -1


async def _eval_js(ws, js: str):
    msg_id = 1
    import json as _json
    await ws.send(_json.dumps({"id": msg_id, "method": "Runtime.evaluate", "params": {"expression": js, "returnByValue": True}}))
    while True:
        resp = _json.loads(await ws.recv())
        if resp.get("id") == msg_id:
            result = resp.get("result", {}).get("result", {})
            if "value" in result:
                return result["value"]
            if "description" in result:
                return result["description"]
            return None


def has_changed(current: int, previous) -> bool:
    if previous is None:
        return True
    return current != previous
