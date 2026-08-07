"""V3 工具统一入口。"""
from tools.search import search_jobs, scan_page, page_text, screenshot
from tools.inspect import inspect_company
from tools.apply import apply
from tools.chat import check_messages, chat_draft, chat_send, list_drafts

__all__ = ["search_jobs", "scan_page", "page_text", "screenshot",
           "inspect_company", "apply", "check_messages",
           "chat_draft", "chat_send", "list_drafts"]
