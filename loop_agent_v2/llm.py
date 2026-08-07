"""V2 LLM 桥接 —— 经 litellm(localhost:4000) 调真模型 DeepSeek,支持 tool calling。"""
import json
import urllib.request

LITELLM_URL = "http://localhost:4000/v1/chat/completions"
MASTER_KEY = "sk-litellm-local"
MODEL = "claude-3-haiku-20240307"   # litellm 里该别名真实转发到 deepseek/deepseek-chat


def format_tools(specs) -> list[dict]:
    """ToolSpec 列表 → 模型 tool calling schema(OpenAI 格式)。"""
    return [
        {"type": "function", "function": {"name": s.name, "description": s.description, "parameters": s.parameters}}
        for s in specs
    ]


def _http_chat(system: str, messages: list[dict], user: dict, tools: list[dict]) -> dict:
    import time
    from urllib.error import HTTPError
    from copy import deepcopy

    work = deepcopy(list(messages))   # 可修剪的工作副本,retry 时可退化历史
    last_exc = None

    def _sanitize(lst):
        """确保不发送悬挂的 assistant(tool_calls):
        - 尾部 assistant 带 tool_calls 而没有紧跟 tool 响应时,直接删掉尾部。
        - 历史中若某条 assistant(tool_calls) 的 tool_call_id 缺少对应 tool 响应(如多 tool_calls 残留),
          从第一个未闭环的 assistant 处截断,保证任意历史都满足 DeepSeek 严格配对校验。
        DeepSeek 严格要求 assistant(tool_calls) 之后必须紧跟对应 tool 消息。"""
        out = list(lst)
        while out and out[-1].get("role") == "assistant" and out[-1].get("tool_calls"):
            out.pop()
        pending: dict[int, set] = {}
        for i, m in enumerate(out):
            if m.get("role") == "assistant" and m.get("tool_calls"):
                pending[i] = {tc.get("id") for tc in m["tool_calls"]}
            elif m.get("role") == "tool":
                rid = m.get("tool_call_id")
                for start, ids in list(pending.items()):
                    if rid and rid in ids:
                        ids.discard(rid)
                        if not ids:
                            del pending[start]
        if pending:
            cut = min(pending)
            out = out[:cut]
            while out and out[-1].get("role") == "assistant" and out[-1].get("tool_calls"):
                out.pop()
        return out

    def _build():
        s = _sanitize(work)
        msgs = [{"role": "system", "content": system}, *s]
        # 工具循环中途不再灌 user:DeepSeek 严格要求 assistant(tool_calls)→tool 紧密交替,
        # 若历史最后一个 role 是 tool(上一轮工具结果),直接续问模型,不准插 user。
        # 仅当历史为空或上一轮是 user/模型已停手时,才注入当前状态。
        last_role = s[-1].get("role") if s else None
        if last_role != "tool":
            msgs.append({"role": "user", "content": json.dumps(user, ensure_ascii=False)})
        return {
            "model": MODEL,
            "messages": msgs,
            "tools": tools,
            "tool_choice": "auto",
        }

    def _send(body):
        req = urllib.request.Request(
            LITELLM_URL,
            data=json.dumps(body).encode("utf-8"),
            headers={"Authorization": f"Bearer {MASTER_KEY}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode("utf-8"))

    for attempt in range(4):
        try:
            return _send(_build())
        except HTTPError as e:
            err_body = e.read().decode("utf-8", "replace")
            is_tool_pair = "insufficient tool messages" in err_body or "tool_calls" in err_body
            if is_tool_pair and work:
                # 去掉最近一组 assistant(tool_calls)+tool,再不行就整段清空重来。
                # DeepSeek 对工具配对校验偶发严格,空历史(仅 system+user)最稳。
                work.pop()
                if work:
                    work.pop()
                print(f"[llm] 400 配对:裁剪历史重试 (history={len(work)})", flush=True)
                last_exc = e
                if not work and is_tool_pair:
                    # 已裁空仍可能再触发:用整段清空的新会话换模式
                    work[:] = []
                time.sleep(1)
            else:
                last_exc = e
                print(f"[llm] HTTP {e.code} attempt{attempt}: {err_body[:200]}", flush=True)
                time.sleep(2 * (attempt + 1))
        except Exception as e:
            last_exc = e
            time.sleep(2 * (attempt + 1))
    raise (last_exc or RuntimeError("LLM request failed"))


def llm_call(system: str, user: dict, tools: list, messages=None):
    """调用真模型,返回 {name, arguments, message};模型选择停手时返回 None。

    `messages` 传入已有的对话历史(之前的 tool 调用 + 结果),让模型"记得"它已做过什么,
    避免重复 scan。返回的 dict 里的 `message` 是本轮 assistant 消息,调用方需拼接回历史。
    """
    resp = _http_chat(system, messages or [], user, format_tools(tools))
    msg = resp["choices"][0]["message"]

    asst_msg = {
        "role": "assistant",
        "content": msg.get("content") or "",
    }
    if msg.get("tool_calls"):
        asst_msg["tool_calls"] = msg["tool_calls"]

    tool_calls = msg.get("tool_calls") or []
    if tool_calls:
        tc = tool_calls[0]
        fn = tc["function"]
        args = fn.get("arguments") or "{}"
        try:
            parsed = json.loads(args)
        except json.JSONDecodeError:
            parsed = {}
        # 只保留实际执行的那一条 tool_call:loop 层只会附加 1 条 tool 响应,
        # 若把模型返回的全部 tool_calls 存入历史,DeepSeek 严格配对校验会 400。
        asst_msg["tool_calls"] = [tc]
        return {"name": fn["name"], "arguments": parsed, "message": asst_msg}

    # 模型没请求工具(直接文字回复) → 视为本轮收尾
    return None
