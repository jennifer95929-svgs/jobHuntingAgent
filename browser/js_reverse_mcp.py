import json
import subprocess
import sys
import time
import os


class JsReverseMCP:
    def __init__(self, browser_url: str = "http://127.0.0.1:9222"):
        self.browser_url = browser_url
        self.proc = None
        self._msg_id = 0

    def start(self):
        self.proc = subprocess.Popen(
            ["npx", "js-reverse-mcp", "--browserUrl", self.browser_url],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        # Initialize MCP session
        resp = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "job-agent", "version": "1.0"}
        })
        srv_info = resp.get("result", {})
        self.server_version = srv_info.get("serverInfo", {}).get("version", "")
        self._send_notification("notifications/initialized")
        return self

    def _send(self, method: str, params: dict = None) -> dict:
        self._msg_id += 1
        req = json.dumps({
            "jsonrpc": "2.0",
            "id": self._msg_id,
            "method": method,
            "params": params or {}
        })
        self.proc.stdin.write(req + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        return json.loads(line)

    def _send_notification(self, method: str, params: dict = None):
        req = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {}
        })
        self.proc.stdin.write(req + "\n")
        self.proc.stdin.flush()

    def call_tool(self, name: str, args: dict = None) -> dict:
        return self._send("tools/call", {"name": name, "arguments": args or {}})

    def navigate(self, url: str):
        self.call_tool("navigate", {"url": url})

    def click(self, selector: str):
        return self.call_tool("click", {"selector": selector})

    def evaluate(self, js: str) -> str:
        result = self.call_tool("evaluate_script", {"script": js})
        content = result.get("result", {}).get("content", [])
        for c in content:
            if c.get("type") == "text":
                return c.get("text", "")
        return str(result)

    def screenshot(self) -> bytes:
        result = self.call_tool("screenshot")
        for c in result.get("result", {}).get("content", []):
            if c.get("type") == "resource" and c.get("mimeType") == "image/png":
                import base64
                return base64.b64decode(c["text"])
            if c.get("type") == "image":
                # might be base64 in text
                import base64
                try:
                    return base64.b64decode(c["text"])
                except Exception:
                    pass
        # Try getting the data from response
        return None

    def close(self):
        if self.proc:
            self.proc.terminate()
            self.proc.wait(timeout=5)

    def list_tools(self) -> list:
        result = self._send("tools/list")
        return result.get("result", {}).get("tools", [])
