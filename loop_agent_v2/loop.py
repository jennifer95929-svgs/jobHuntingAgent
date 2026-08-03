"""V2 循环脚手架 —— 只做接线,零业务决策。真模型(DeepSeek)+ 真浏览器(CDP)。"""
import json
import os
import sys

LOOP_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LOOP_ROOT)

from tools import TOOL_SPECS, REGISTRY, session
from llm import llm_call, format_tools
from context import capture, save_trace
import history as hist

MAX_ITERATIONS = int(os.environ.get("V2_MAX_ITERATIONS", "400"))  # 防失控护栏,非业务逻辑;实际投递量由 history.MAX_APPLY_PER_DAY 与验证码决定


def execute(action: dict) -> dict:
    name = action.get("name")
    args = action.get("arguments", {})
    spec = REGISTRY.get(name)
    if spec is None:
        return {"error": f"unknown tool: {name}", "available": list(REGISTRY)}
    try:
        return spec.handler(**args)
    except Exception as e:
        return {"error": str(e)}


def load_system_prompt() -> str:
    md = []
    for f in ("GOAL.md", "DOMAIN.md", "RULES.md", "PROFILE.md", "WORKFLOW.md"):
        p = os.path.join(LOOP_ROOT, f)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                md.append(fh.read())
    return "\n\n---\n\n".join(md)


def main() -> None:
    print("[v2] 启动 —— 真模型(DeepSeek)+ 真实浏览器(CDP)| 真实投递模式")
    print(f"[v2] 今日已投 {hist.today_count()}/{hist.MAX_APPLY_PER_DAY},将由模型自主投满或遇验证码自动停")
    s = session()                       # 复用同一浏览器会话
    s.ensure_browser()

    history: list[dict] = []           # 累积对话:assistant 工具调用 + tool 结果,让模型记得前因后果

    start_count = hist.today_count()
    run_target = int(os.environ.get("V2_RUN_TARGET", "5"))   # 本跑目标:再投 N 家就干净退出,由外部重启续投

    for i in range(MAX_ITERATIONS):
        # 方案3批次停止:本跑已投满 run_target,或到每日上限,干净收尾(不再硬跑长时)
        if hist.today_count() - start_count >= run_target:
            print(f"[v2] 本跑已达目标(+{run_target}家),共投 {hist.today_count()}/{hist.MAX_APPLY_PER_DAY},干净收尾(可重启续投)")
            break
        if hist.reached_daily_limit():
            print("[v2] 今日已达上限,收尾")
            break

        state = capture()

        try:
            call = llm_call(system=load_system_prompt(), user=state, tools=TOOL_SPECS, messages=history)
        except Exception as e:
            print(f"[v2] LLM 调用失败(重试仍失败): {e};本轮收尾")
            break

        if call is None:                # 模型选择停手
            print("[v2] LLM 停手,结束本轮")
            break

        print(f"[v2] #{i+1} {call['name']} args={call['arguments']}")

        result = execute(call)
        save_trace(state, call, result)
        print(f"     → {str(result)[:200]}")

        if call.get("message"):
            history.append(call["message"])
            history.append({
                "role": "tool",
                "tool_call_id": call["message"]["tool_calls"][0]["id"],
                "content": json.dumps(result, ensure_ascii=False)[:800],
            })
            # 限长:只保留最近 8 条(约4轮),避免历史膨胀诱发 DeepSeek 配对校验问题,也省 token
            del history[:-8]
    else:
        print(f"[v2] 达到 MAX_ITERATIONS={MAX_ITERATIONS} 护栏上限,结束")
    print(f"[v2] 本次运行结束。今日共投 {hist.today_count()}/{hist.MAX_APPLY_PER_DAY}。重跑 loop.py 即可续投(去重护栏自动跳过已投)。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[v2] 用户中断")
        sys.exit(0)
