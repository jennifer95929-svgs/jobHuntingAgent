"""CDP bridge for browser communication.

Wraps WebSocket connection to Chrome DevTools Protocol.
Used by perceive/execute modules to read DOM and trigger actions.
"""

import json
import asyncio
import websockets


class CDPClient:
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

    async def insert_text(self, text: str):
        for ch in text:
            await self.send("Input.insertText", {"text": ch})
            await asyncio.sleep(0.005)

    async def press_enter(self):
        await self.send("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Enter", "windowsVirtualKeyCode": 13, "code": "Enter"})
        await asyncio.sleep(0.05)
        await self.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "windowsVirtualKeyCode": 13, "code": "Enter"})
