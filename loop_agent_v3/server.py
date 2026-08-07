"""V3 MCP Server —— 把 BOSS 直聘浏览器操作暴露为 MCP 工具。

工具清单(9个):
  search_jobs / scan_page / page_text / screenshot / inspect_company / apply / check_messages / wait / done

运行方式(由 opencode 拉起):
  <venv>/bin/python server.py   (stdio 模式)
"""
import asyncio
import json
import os
import sys
import time

V3_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(V3_ROOT, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
if V3_ROOT not in sys.path:
    sys.path.insert(0, V3_ROOT)

from mcp.server.lowlevel import Server
from mcp.server.context import ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool, TextContent, ListToolsResult, CallToolResult,
    PaginatedRequestParams, CallToolRequestParams,
)

from tools import (
    search_jobs, scan_page, page_text, screenshot, inspect_company,
    apply, check_messages, chat_draft, chat_send, list_drafts,
)

app = Server("boss-job-hunter-v3")

TOOL_DEFS = [
    (
        "search_jobs",
        "按关键词+城市在 BOSS直聘 打开岗位搜索页(自动清理堆积的旧搜索tab)",
        {"type": "object", "properties": {
            "keyword": {"type": "string", "description": "搜索关键词,如 AI产品经理"},
            "city": {"type": "string", "description": "城市,如 深圳"},
        }, "required": ["keyword", "city"]},
    ),
    (
        "scan_page",
        "提取当前搜索页岗位列表(最多8条:标题/薪资/公司/job_id)。只对刚 search_jobs 过的页面调用",
        {"type": "object", "properties": {}},
    ),
    (
        "inspect_company",
        "打开岗位详情页,只读检查公司规模>=50且非外包、非下架404。只对合格岗位才调用 apply",
        {"type": "object", "properties": {
            "job_id": {"type": "string", "description": "岗位ID(来自 scan_page)"},
        }, "required": ["job_id"]},
    ),
    (
        "apply",
        "投递指定岗位。内置硬护栏:每日上限50、跨日去重、验证码检测、公司规模复核,不合格自动拒绝。失败时 reason 带类型前缀(duplicate/limit/captcha/company/dead/timeout/click/error),按类型处理不要盲目重试",
        {"type": "object", "properties": {
            "job_id": {"type": "string", "description": "要投的岗位ID(必须来自 scan_page 或已 inspect 合格的岗位)"},
            "job_title": {"type": "string", "description": "岗位标题(可选,便于记录)"},
            "company": {"type": "string", "description": "公司名(可选,便于记录)"},
        }, "required": ["job_id"]},
    ),
    (
        "check_messages",
        "检测未读 HR 消息数",
        {"type": "object", "properties": {}},
    ),
    (
        "chat_draft",
        "生成 HR 回复草案(不直接发送!)。打开聊天页读取未读消息,为每条生成回复模板保存到 data/chat_drafts.json,状态为 pending。回复需用户确认后再调 chat_send 发送",
        {"type": "object", "properties": {}},
    ),
    (
        "chat_send",
        "发送已确认的回复草案。默认发指定 draft_id;all_pending=true 时批量发送所有 pending 草案。只有用户确认过的草案才发送",
        {"type": "object", "properties": {
            "draft_id": {"type": "string", "description": "要发送的草案ID(来自 chat_draft 返回),留空配合 all_pending"},
            "all_pending": {"type": "boolean", "description": "是否批量发送所有 pending 草案"},
        }},
    ),
    (
        "list_drafts",
        "列出所有回复草案及状态(pending/approved/sent),供用户审批",
        {"type": "object", "properties": {}},
    ),
    (
        "page_text",
        "读取当前页文本内容(截断2000字符),用于确认页面状态",
        {"type": "object", "properties": {}},
    ),
    (
        "screenshot",
        "截图保存到 data/shot.png",
        {"type": "object", "properties": {}},
    ),
    (
        "wait",
        "暂停几分钟(防风控,模拟人类阅读节奏)。每4-5次操作后建议 wait(1-2)",
        {"type": "object", "properties": {
            "minutes": {"type": "number", "description": "暂停分钟数(支持小数)"},
        }, "required": ["minutes"]},
    ),
    (
        "done",
        "本轮收工。今日投满50、所有关键词×城市组合穷尽、或遇验证码时调用",
        {"type": "object", "properties": {}},
    ),
]


def _dispatch(name: str, args: dict) -> dict:
    if name == "search_jobs":
        return search_jobs(**args)
    if name == "scan_page":
        return scan_page()
    if name == "inspect_company":
        return inspect_company(**args)
    if name == "apply":
        return apply(**args)
    if name == "check_messages":
        return check_messages()
    if name == "chat_draft":
        return chat_draft()
    if name == "chat_send":
        return chat_send(draft_id=args.get("draft_id", ""), all_pending=bool(args.get("all_pending", False)))
    if name == "list_drafts":
        return list_drafts()
    if name == "page_text":
        return page_text()
    if name == "screenshot":
        return screenshot()
    if name == "wait":
        minutes = float(args.get("minutes", 1))
        time.sleep(minutes * 60)
        return {"waited_minutes": minutes}
    if name == "done":
        return {"status": "done"}
    return {"error": f"unknown tool: {name}"}


async def handle_list_tools(ctx: ServerRequestContext, params: PaginatedRequestParams) -> ListToolsResult:
    tools = [Tool(name=n, description=d, input_schema=s) for n, d, s in TOOL_DEFS]
    return ListToolsResult(tools=tools)


async def handle_call_tool(ctx: ServerRequestContext, params: CallToolRequestParams) -> CallToolResult:
    name = params.name
    args = params.arguments or {}
    try:
        result = await asyncio.to_thread(_dispatch, name, args)
    except Exception as e:  # noqa: BLE001
        result = {"error": str(e)}
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False))])


app.add_request_handler("tools/list", PaginatedRequestParams, handle_list_tools)
app.add_request_handler("tools/call", CallToolRequestParams, handle_call_tool)


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())