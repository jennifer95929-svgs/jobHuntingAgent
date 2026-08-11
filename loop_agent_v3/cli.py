"""V3 冒烟测试 CLI —— 不依赖 mcp 库,直接验证工具层 + 浏览器 + 护栏。

用法:
  python3.14 cli.py search "AI产品经理" "深圳"
  python3.14 cli.py scan
  python3.14 cli.py inspect <job_id>
  python3.14 cli.py apply <job_id> [title] [company]
  python3.14 cli.py messages
"""
import json
import os
import sys

V3_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.normpath(os.path.join(V3_ROOT, ".."))
for p in (V3_ROOT, PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from tools import search_jobs, scan_page, inspect_company, apply, check_messages, page_text, chat_draft, chat_send, list_drafts, chat_auto


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd == "search":
        print(json.dumps(search_jobs(sys.argv[2], sys.argv[3]), ensure_ascii=False))
    elif cmd == "scan":
        print(json.dumps(scan_page(), ensure_ascii=False)[:2000])
    elif cmd == "inspect":
        print(json.dumps(inspect_company(sys.argv[2]), ensure_ascii=False))
    elif cmd == "apply":
        jid, title, company = sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "", sys.argv[4] if len(sys.argv) > 4 else ""
        salary = sys.argv[5] if len(sys.argv) > 5 else ""
        print(json.dumps(apply(jid, title, company, salary), ensure_ascii=False))
    elif cmd == "messages":
        print(json.dumps(check_messages(), ensure_ascii=False))
    elif cmd == "draft":
        print(json.dumps(chat_draft(), ensure_ascii=False))
    elif cmd == "send":
        draft_id = sys.argv[2] if len(sys.argv) > 2 else ""
        all_pending = len(sys.argv) > 3 and sys.argv[3] == "--all"
        print(json.dumps(chat_send(draft_id=draft_id, all_pending=all_pending), ensure_ascii=False))
    elif cmd == "drafts":
        print(json.dumps(list_drafts(), ensure_ascii=False))
    elif cmd == "auto":
        print(json.dumps(chat_auto(), ensure_ascii=False))
    elif cmd == "page":
        print(json.dumps(page_text(), ensure_ascii=False)[:1500])
    else:
        print("用法见文件头注释")


if __name__ == "__main__":
    main()