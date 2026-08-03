import asyncio
import json
import re
import time
import urllib.request
from typing import Optional
import websockets




class CDPClient:
    """Single WebSocket connection to Chrome DevTools Protocol"""

    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._ws = None
        self._msg_id = 0

    async def connect(self):
        self._ws = await websockets.connect(self.ws_url)
        return self

    async def close(self):
        if self._ws:
            await self._ws.close()

    async def send(self, method: str, params: dict = None) -> dict:
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        await self._ws.send(json.dumps(msg))
        while True:
            resp = json.loads(await self._ws.recv())
            if resp.get("id") == self._msg_id:
                return resp

    async def evaluate(self, js: str):
        resp = await self.send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        })
        result = resp.get("result", {}).get("result", {})
        if "value" in result:
            return result["value"]
        if "description" in result:
            return result["description"]
        return None

    async def click_element(self, selector: str):
        js = f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return false;
            el.scrollIntoView({{block: 'center'}});
            el.click();
            return true;
        }})()
        """
        result = await self.evaluate(js)
        return result == "true"

    async def click_by_text(self, text: str) -> bool:
        js = f"""
        (() => {{
            const els = [...document.querySelectorAll('a, button, span, div, li')];
            const target = els.find(el => el.textContent.trim() === {json.dumps(text)});
            if (!target) return false;
            target.scrollIntoView({{block: 'center'}});
            target.click();
            return true;
        }})()
        """
        result = await self.evaluate(js)
        return result == "true"

    async def fill_input(self, placeholder: str, value: str) -> bool:
        js = f"""
        (() => {{
            const input = document.querySelector('input[placeholder*={json.dumps(placeholder)}], textarea[placeholder*={json.dumps(placeholder)}]');
            if (!input) return false;
            input.value = {json.dumps(value)};
            input.dispatchEvent(new Event('input', {{bubbles: true}}));
            input.dispatchEvent(new Event('change', {{bubbles: true}}));
            return true;
        }})()
        """
        result = await self.evaluate(js)
        return result == "true"

    async def get_text(self) -> str:
        return await self.evaluate("document.body.innerText")

    async def get_url(self) -> str:
        return await self.evaluate("window.location.href")

    async def navigate(self, url: str):
        await self.send("Page.enable")
        await self.send("Page.navigate", {"url": url})
        await asyncio.sleep(3)

    async def page_text_contains(self, text: str) -> bool:
        body = await self.get_text()
        return text in body


class AgentBrowser:
    def __init__(self, session: str = "default"):
        self.session = session
        self._page_id = None

    def _get_boss_tab(self) -> Optional[dict]:
        try:
            resp = urllib.request.urlopen("http://localhost:9222/json", timeout=3)
            tabs = json.loads(resp.read())
            for t in tabs:
                if t.get("type") == "page" and "zhipin" in t.get("url", ""):
                    return t
            for t in tabs:
                if t.get("type") == "page":
                    return t
            return None
        except Exception:
            return None

    def _run_cdp(self, fn_name: str, *args, **kwargs):
        tab = self._get_boss_tab()
        if not tab:
            raise RuntimeError("No browser tab found. Is Chrome running with --remote-debugging-port=9222?")

        async def _run():
            async with websockets.connect(tab["webSocketDebuggerUrl"], close_timeout=5) as ws:
                client = CDPClient("")
                client._ws = ws
                method = getattr(client, fn_name)
                return await method(*args, **kwargs)

        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    def _run_in_loop(self, coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    def evaluate_in_tab(self, tab_ws: str, js: str):
        async def _run():
            async with websockets.connect(tab_ws, close_timeout=10) as ws:
                client = CDPClient("")
                client._ws = ws
                return await client.evaluate(js)
        return self._run_in_loop(_run())

    def call_in_tab(self, tab_ws: str, method: str, params: dict = None) -> dict:
        async def _run():
            async with websockets.connect(tab_ws, close_timeout=10) as ws:
                client = CDPClient("")
                client._ws = ws
                return await client.send(method, params)
        return self._run_in_loop(_run())

    def create_tab(self, url: str) -> Optional[str]:
        try:
            browser_ws = json.loads(
                urllib.request.urlopen("http://localhost:9222/json/version", timeout=3).read()
            )["webSocketDebuggerUrl"]

            async def _run():
                async with websockets.connect(browser_ws, close_timeout=10) as ws:
                    client = CDPClient("")
                    client._ws = ws
                    resp = await client.send("Target.createTarget", {
                        "url": url, "newWindow": False, "background": False
                    })
                    return resp.get("result", {}).get("targetId")

            return self._run_in_loop(_run())
        except Exception:
            return None

    def close_tab(self, target_id: str):
        try:
            browser_ws = json.loads(
                urllib.request.urlopen("http://localhost:9222/json/version", timeout=3).read()
            )["webSocketDebuggerUrl"]

            async def _run():
                async with websockets.connect(browser_ws, close_timeout=5) as ws:
                    client = CDPClient("")
                    client._ws = ws
                    await client.send("Target.closeTarget", {"targetId": target_id})

            self._run_in_loop(_run())
        except Exception:
            pass

    def get_tab_by_url(self, url_pattern: str) -> Optional[dict]:
        try:
            resp = urllib.request.urlopen("http://localhost:9222/json", timeout=3)
            tabs = json.loads(resp.read())
            for t in tabs:
                if url_pattern in t.get("url", ""):
                    return t
            return None
        except Exception:
            return None

    def get_tab_by_id(self, target_id: str) -> Optional[dict]:
        try:
            resp = urllib.request.urlopen("http://localhost:9222/json", timeout=3)
            tabs = json.loads(resp.read())
            for t in tabs:
                if t.get("id") == target_id:
                    return t
            for t in tabs:
                if target_id in t.get("id", ""):
                    return t
            return None
        except Exception:
            return None

    def check_alive(self) -> bool:
        return self._get_boss_tab() is not None

    def open(self, url: str, headed: bool = True):
        self._force_navigate(url)

    def go(self, url: str):
        self._force_navigate(url)

    def _force_navigate(self, url: str):
        tab = self._get_boss_tab()
        if not tab:
            raise RuntimeError("No browser tab found")
        ws_url = tab["webSocketDebuggerUrl"]

        async def navigate():
            async with websockets.connect(ws_url, close_timeout=10) as ws:
                client = CDPClient("")
                client._ws = ws
                await client.send("Page.navigate", {"url": url})

        self._run_in_loop(navigate())

    def get_text(self) -> str:
        return self._run_cdp("get_text")

    def click(self, selector: str):
        self._run_cdp("click_element", selector)

    def click_text(self, text: str) -> bool:
        return self._run_cdp("click_by_text", text)

    def find_placeholder(self, placeholder: str) -> Optional[str]:
        return placeholder

    def find_textarea(self) -> Optional[str]:
        return "textarea"

    def type(self, text: str):
        js = f"""
        (() => {{
            const el = document.querySelector('input:focus, textarea:focus');
            if (!el) return;
            el.value += {json.dumps(text)};
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
        }})()
        """
        self._run_cdp("evaluate", js)

    def fill(self, text: str):
        js = f"""
        (() => {{
            const el = document.querySelector('input:focus, textarea:focus');
            if (!el) return;
            el.value = {json.dumps(text)};
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
        }})()
        """
        self._run_cdp("evaluate", js)

    def _screenshot_impl(self, ws_url: str, path: Optional[str] = None) -> Optional[str]:
        async def _run():
            async with websockets.connect(ws_url, close_timeout=10) as ws:
                cdp = CDPClient("")
                cdp._ws = ws
                resp = await cdp.send("Page.captureScreenshot", {"format": "png"})
                data = resp.get("result", {}).get("data", "")
                if data:
                    import base64
                    img = base64.b64decode(data)
                    save_path = path or f"/tmp/boss_{int(time.time())}.png"
                    with open(save_path, "wb") as f:
                        f.write(img)
                    return save_path
                return None
        return self._run_in_loop(_run())

    def screenshot(self, path: Optional[str] = None):
        tab = self._get_boss_tab()
        if not tab:
            return None
        return self._screenshot_impl(tab["webSocketDebuggerUrl"], path)

    def screenshot_in_tab(self, tab_ws: str, path: Optional[str] = None):
        return self._screenshot_impl(tab_ws, path)

    def close_all(self):
        pass
