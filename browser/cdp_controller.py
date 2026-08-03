import json
import time
import base64
import urllib.request
import websocket

CDP_URL = "http://127.0.0.1:9222"


def _get_page() -> dict:
    resp = urllib.request.urlopen(f"{CDP_URL}/json/list", timeout=10)
    pages = json.loads(resp.read())
    page_pages = [p for p in pages if p.get("type") == "page"]
    if page_pages:
        return page_pages[-1]
    resp2 = urllib.request.urlopen(urllib.request.Request(f"{CDP_URL}/json/new", method="PUT"), timeout=10)
    return json.loads(resp2.read())


class CDPPage:
    def __init__(self):
        self.ws = None
        self.page = None
        self._msg_id = 0

    def connect(self, url: str = None):
        if url:
            resp = urllib.request.urlopen(url, timeout=10)
            pages = json.loads(resp.read()) if isinstance(resp.read(), bytes) else resp.read()
            self.page = _get_page()
        else:
            self.page = _get_page()
        ws_url = self.page["webSocketDebuggerUrl"]
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self._msg_id = 0
        return self

    def send(self, method: str, params: dict = None) -> dict:
        self._msg_id += 1
        msg = json.dumps({"id": self._msg_id, "method": method, "params": params or {}})
        self.ws.send(msg)
        while True:
            raw = self.ws.recv()
            data = json.loads(raw)
            if data.get("id") == self._msg_id:
                return data
            if data.get("method") == "Runtime.consoleAPICalled":
                continue

    def navigate(self, url: str):
        self.send("Page.navigate", {"url": url})
        self._wait_loaded()

    def _wait_loaded(self, timeout: float = 15):
        deadline = time.time() + timeout
        self.send("Runtime.enable")
        self.send("Page.enable")
        while time.time() < deadline:
            try:
                result = self.send("Runtime.evaluate", {
                    "expression": "document.readyState",
                    "returnByValue": True
                })
                state = result.get("result", {}).get("result", {}).get("value", "")
                if state == "complete":
                    return
            except Exception:
                pass
            time.sleep(0.5)

    def evaluate(self, js: str) -> dict:
        result = self.send("Runtime.evaluate", {"expression": js, "returnByValue": True})
        return result

    def evaluate_raw(self, js: str) -> dict:
        return self.evaluate(js).get("result", {}).get("result", {})

    def click(self, selector: str):
        js = f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return {{ok: false, error: 'element not found'}};
            const rect = el.getBoundingClientRect();
            el.scrollIntoView({{behavior: 'instant', block: 'center'}});
            return {{ok: true, x: rect.left + rect.width/2, y: rect.top + rect.height/2}};
        }})()
        """
        result = self.evaluate_raw(js)
        if not result.get("ok"):
            return False
        x, y = result["x"], result["y"]
        self.send("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1
        })
        self.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1
        })
        return True

    def _click_at(self, js_return: dict) -> bool:
        if not js_return:
            return False
        val = js_return.get("value")
        if not val or not val.get("ok"):
            return False
        x, y = val["x"], val["y"]
        self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        return True

    def click_by_text(self, text: str, tag: str = "*", partial: bool = False) -> bool:
        match_op = "includes" if partial else "==="
        js = f"""
        (() => {{
            const els = document.querySelectorAll({json.dumps(tag)});
            const el = Array.from(els).find(e => {{
                const t = e.textContent.trim().replace(/\\s+/g, ' ');
                if (t.length > 100) return false;
                return t {match_op} {json.dumps(text)};
            }});
            if (!el) return {{ok: false}};
            const rect = el.getBoundingClientRect();
            el.scrollIntoView({{behavior: 'instant', block: 'center'}});
            return {{ok: true, x: rect.left + rect.width/2, y: rect.top + rect.height/2}};
        }})()
        """
        return self._click_at(self.evaluate_raw(js))

    def click_by_selector(self, selector: str) -> bool:
        js = f"""
        (() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return {{ok: false}};
            const rect = el.getBoundingClientRect();
            el.scrollIntoView({{behavior: 'instant', block: 'center'}});
            return {{ok: true, x: rect.left + rect.width/2, y: rect.top + rect.height/2}};
        }})()
        """
        return self._click_at(self.evaluate_raw(js))

    def fill(self, selector: str, value: str):
        self.click(selector)
        self.send("Runtime.evaluate", {
            "expression": f"document.querySelector({json.dumps(selector)}).value = {json.dumps(value)}",
            "returnByValue": True
        })

    def screenshot(self, path: str = "/tmp/boss_screen.png") -> str:
        result = self.send("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        data = result.get("result", {}).get("data", "")
        if data:
            with open(path, "wb") as f:
                f.write(base64.b64decode(data))
        return path

    def get_text(self) -> str:
        result = self.evaluate_raw("document.body.innerText")
        return result.get("value", "")

    def close(self):
        if self.ws:
            self.ws.close()

    def get_job_cards(self) -> list:
        js = """
        (() => {
            const cards = document.querySelectorAll('.job-card-box');
            return JSON.stringify(Array.from(cards).slice(0,30).map(c => {
                const link = c.querySelector('a[href*="/job_detail/"]');
                const titleEl = c.querySelector('.job-name');
                const salaryEl = c.querySelector('.job-salary');
                const companyEl = c.querySelector('.company-name');
                const href = link ? link.getAttribute('href') : '';
                const match = href ? href.match(/\\/job_detail\\/([^\\/]+?)\\.html/) : null;
                return {
                    id: match ? match[1] : '',
                    title: titleEl ? titleEl.textContent.trim() : '',
                    salary: salaryEl ? salaryEl.textContent.trim() : '',
                    company: companyEl ? companyEl.textContent.trim() : '',
                    href: href ? 'https://www.zhipin.com' + href : ''
                };
            }).filter(c => c.id));
        })()
        """
        result = self.evaluate_raw(js)
        val = result.get("value", "[]")
        return json.loads(val) if isinstance(val, str) else val

    def chat_with_hr(self, greeting: str) -> bool:
        ok = self.click_by_selector(".btn-startchat") or self.click_by_selector(".btn-startchat-wrap")
        if not ok:
            return False
        time.sleep(2)
        return self._type_and_send(greeting)

    def _type_and_send(self, text: str) -> bool:
        js = """
        (() => {
            const el = document.querySelector('div[contenteditable="true"], .chat-input-area, textarea.chat-input, #chat-input');
            if (!el) return false;
            el.focus();
            return true;
        })()
        """
        result = self.evaluate_raw(js)
        if not result or not result.get("value"):
            return False
        self.send("Input.insertText", {"text": text})
        time.sleep(0.8)
        self.click_by_text("发送", "*", partial=True)
        return True

    def click_apply(self) -> bool:
        return self.chat_with_hr("你好，对这个岗位感兴趣，方便沟通吗？")


def open_boss_login():
    page = _get_page()
    ws_url = page["webSocketDebuggerUrl"]
    ws = websocket.create_connection(ws_url, timeout=10)
    ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": "https://www.zhipin.com/web/user/"}}))
    ws.recv()
    ws.close()
    print("BOSS 直聘登录页已打开，请完成登录")

def open_boss_search(keyword: str = "AI产品经理", city: str = "101280600"):
    page = _get_page()
    ws_url = page["webSocketDebuggerUrl"]
    ws = websocket.create_connection(ws_url, timeout=10)
    url = f"https://www.zhipin.com/web/geek/jobs?query={keyword}&city={city}"
    ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
    ws.recv()
    ws.close()
    return page["id"]
