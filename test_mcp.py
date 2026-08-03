#!/usr/bin/env python3
import subprocess, json, sys, time, os

proc = subprocess.Popen(
    ["npx", "js-reverse-mcp", "--browserUrl", "http://127.0.0.1:9222"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    text=True, bufsize=0,
)

msg_id = 0

def send(method, params=None):
    global msg_id
    msg_id += 1
    req = json.dumps({"jsonrpc":"2.0","id":msg_id,"method":method,"params":params or {}})
    proc.stdin.write(req + "\n")
    proc.stdin.flush()
    return msg_id

def recv(timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        r = os.read(proc.stdout.fileno(), 65536) if hasattr(proc.stdout, 'fileno') else None
        if r:
            # Handle multiple JSON lines
            for line in r.decode().strip().split("\n"):
                if line:
                    try:
                        return json.loads(line)
                    except:
                        pass
        time.sleep(0.2)
    return None

# Initialize
print("[1] Initialize...")
send("initialize", {"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}})
resp = recv()
print(f"    Server: {resp.get('result',{}).get('serverInfo',{}).get('name','?')} v{resp.get('result',{}).get('serverInfo',{}).get('version','?')}")

# Notify initialized
send("notifications/initialized")

# Wait for browser to be ready
print("[2] Waiting for browser...")
time.sleep(5)

# List tools
print("[3] Listing tools...")
send("tools/list")
resp = recv()
tools = resp.get("result",{}).get("tools",[]) if resp else []
print(f"    Found {len(tools)} tools")
for t in tools[:8]:
    print(f"    - {t.get('name','?'):30s} {t.get('description','')[:50]}")

# Navigate
print("\n[4] Navigate to BOSS直聘...")
send("tools/call", {"name":"navigate","arguments":{"url":"https://www.zhipin.com/web/geek/jobs?query=AI%E4%BA%A7%E5%93%81%E7%BB%8F%E7%90%86&city=101280600"}})
resp = recv()
print(f"    Result: {json.dumps(resp, indent=2)[:300]}")
time.sleep(5)

# Get page info
print("\n[5] Evaluate JS...")
send("tools/call", {"name":"evaluate_script","arguments":{"script":"document.title"}})
resp = recv()
print(f"    Title result: {json.dumps(resp, indent=2)[:200]}")

proc.terminate()
proc.wait()
print("\nDone")
