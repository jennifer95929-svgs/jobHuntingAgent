import json
import os
import time
import random
import sys
from datetime import date
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests

from config import (
    SEARCH_KEYWORDS, CITIES, MAX_APPLY_PER_DAY,
    HISTORY_FILE, LOG_FILE, RESUME_FILE, MAX_RETRY, APPLY_MODE,
    JOB_SPREADSHEET_TOKEN, JOB_SHEET_ID,
)
from browser.boss_session import BossSession
from chat.generator import ChatGenerator
from resume.profile import load_profile, edit_profile
from resume import profile as resume_module
from pipeline.filter import batch_filter
from pipeline.research import company_report
from pipeline.matcher import batch_match, match_job


def log(msg: str):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def load_history() -> dict:
    today = str(date.today())
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE) as f:
                h = json.load(f)
                h.setdefault(today, {"applied": [], "chats": []})
                return h
        except (json.JSONDecodeError, IOError):
            pass
    return {today: {"applied": [], "chats": []}}


def save_history(history: dict):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def today_count(history: dict) -> int:
    today = str(date.today())
    return len(history.get(today, {}).get("applied", []))


def already_applied(history: dict, job_id: str) -> bool:
    today = str(date.today())
    applied = history.get(today, {}).get("applied", [])
    return any(a.get("id") == job_id for a in applied)


_feishu_session = requests.Session()
_feishu_token_cache = {"token": "", "expires_at": 0}
_FEISHU_BASE = "https://open.feishu.cn"


def _get_feishu_token():
    now = time.time()
    if _feishu_token_cache["token"] and now < _feishu_token_cache["expires_at"] - 60:
        return _feishu_token_cache["token"]
    resp = _feishu_session.post(
        f"{_FEISHU_BASE}/open-apis/auth/v3/tenant_access_token/internal",
        json={
            "app_id": os.environ.get("FEISHU_APP_ID", ""),
            "app_secret": os.environ.get("FEISHU_APP_SECRET", ""),
        },
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _feishu_token_cache["token"] = data["tenant_access_token"]
    _feishu_token_cache["expires_at"] = now + data.get("expire", 7200) - 60
    return _feishu_token_cache["token"]


def sync_to_feishu(job_info: dict):
    try:
        token = _get_feishu_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # 读 A 列找到最后有数据的行
        url = f"{_FEISHU_BASE}/open-apis/sheets/v2/spreadsheets/{JOB_SPREADSHEET_TOKEN}/values/{JOB_SHEET_ID}!A:A"
        resp = _feishu_session.get(url, headers=headers, timeout=10)
        rows = resp.json().get("data", {}).get("valueRange", {}).get("values", [])
        next_row = max(len(rows), 1) + 1  # 如果只有表头，从第2行开始

        today = str(date.today())
        row_data = [[
            today,
            job_info.get("time", time.strftime("%H:%M:%S")),
            job_info.get("keyword", ""),
            job_info.get("city", ""),
            job_info.get("company", ""),
            job_info.get("title", ""),
            job_info.get("salary", ""),
            "已投递",
        ]]
        body = {"valueRange": {"range": f"{JOB_SHEET_ID}!A{next_row}:H{next_row}", "values": row_data}}
        resp = _feishu_session.put(
            f"{_FEISHU_BASE}/open-apis/sheets/v2/spreadsheets/{JOB_SPREADSHEET_TOKEN}/values",
            headers=headers,
            json=body,
            timeout=10,
        )
        if resp.json().get("code") == 0:
            log(f"  已同步到飞书表格 (第{next_row}行)")
        else:
            log(f"  飞书同步失败: {resp.json()}")
    except Exception as e:
        log(f"  飞书同步异常: {e}")


def mark_applied(history: dict, job_id: str, job_info: dict):
    today = str(date.today())
    history.setdefault(today, {"applied": [], "chats": []})
    record = {"id": job_id, **job_info, "time": time.strftime("%H:%M:%S")}
    history[today]["applied"].append(record)
    save_history(history)
    sync_to_feishu(record)


class JobAgent:
    def __init__(self):
        self.session = BossSession()
        self.chat = ChatGenerator()
        self.profile = load_profile()

    def run_once(self):
        log("=== 求职 Agent 启动 ===")
        history = load_history()
        count = today_count(history)
        log(f"今日已投递: {count}/{MAX_APPLY_PER_DAY}")

        if count >= MAX_APPLY_PER_DAY:
            log("今日投递已达上限，检查是否有新消息...")
            self.handle_chats()
            return

        self.session.ensure_browser(headed=True)

        for keyword in SEARCH_KEYWORDS:
            for city in CITIES:
                count = today_count(load_history())
                if count >= MAX_APPLY_PER_DAY:
                    log("今日上限达成，停止搜索")
                    break

                log(f"搜索: {keyword} - {city}")
                try:
                    applied = self._scan_and_apply(keyword, city, history)
                    count += applied
                except Exception as e:
                    log(f"搜索 {keyword}-{city} 出错: {e}")
                    continue

        try:
            self.handle_chats()
        except Exception as e:
            log(f"处理消息出错: {e}")
        log("=== 求职 Agent 本轮完成 ===")

    def _browse_jobs_human(self, jobs: list) -> Optional[dict]:
        """模拟人类浏览岗位：逐个查看，每10个选1个投递"""
        BROWSE_PER_APPLY = 10

        for i, job in enumerate(jobs):
            idx = i + 1
            job_id = job["id"]
            log(f"浏览 [{idx}/{len(jobs)}] {job.get('title','')} @ {job.get('company','')} {job.get('salary','')}")

            # 滚动到该岗位
            ws = self.session._search_tab_ws
            scroll_js = f"""
            (() => {{
                const cards = document.querySelectorAll('.job-card-box');
                const card = cards[{i}];
                if (card) {{
                    card.scrollIntoView({{block: 'center', behavior: 'smooth'}});
                    return true;
                }}
                return false;
            }})()
            """
            self.session.browser.evaluate_in_tab(ws, scroll_js)
            self.session.random_delay(3, 6)

            # 每隔 BROWSE_PER_APPLY 个决定是否投递
            if idx % BROWSE_PER_APPLY != 0:
                continue

            # 用 LLM 从中挑出最好的一个
            batch = jobs[max(0, i - BROWSE_PER_APPLY + 1):i + 1]
            log(f"浏览完 {idx} 个，用量智筛选最佳岗位...")
            try:
                filtered = batch_filter(batch)
                if filtered:
                    pick = filtered[0]
                    log(f"选定: {pick.get('title','')} @ {pick.get('company','')} - {pick.get('salary','')}")
                    return pick
            except Exception as e:
                log(f"筛选异常: {e}")

            # LLM 失败时随机选一个
            pick = random.choice(batch)
            log(f"随机选定: {pick.get('title','')} @ {pick.get('company','')} - {pick.get('salary','')}")
            return pick

        # 浏览完所有都没走到模数，挑最后一个批次
        if jobs:
            batch = jobs[-min(BROWSE_PER_APPLY, len(jobs)):]
            log(f"浏览完所有 {len(jobs)} 个，从最后 {len(batch)} 个中选定...")
            try:
                filtered = batch_filter(batch)
                if filtered:
                    return filtered[0]
            except:
                pass
            return random.choice(batch)
        return None

    def _scan_and_apply(self, keyword: str, city: str, history: dict) -> int:
        applied = 0
        for page in range(3):
            count = today_count(load_history())
            if count >= MAX_APPLY_PER_DAY:
                break

            if page == 0:
                self.session.search_jobs(keyword, city)
            self.session.random_delay(3, 6)
            log(f"扫描第 {page+1} 页...")
            jobs = self.session.extract_job_list()
            if not jobs:
                break

            jobs = [j for j in jobs if j.get("id") and not already_applied(history, j["id"])]
            if not jobs:
                self._next_page()
                continue

            log(f"本页 {len(jobs)} 个未投递岗位")

            # 第一步: LLM快速筛选（剔除外包/小公司/不匹配）
            try:
                filtered = batch_filter(jobs)
                skipped = len(jobs) - len(filtered)
                if skipped > 0:
                    log(f"LLM筛选过滤 {skipped} 个（外包/小公司/不匹配），剩余 {len(filtered)} 个")
                jobs = filtered
            except Exception as e:
                log(f"LLM筛选异常: {e}，继续使用全部岗位")

            if not jobs:
                log("筛选后无合适岗位，翻页")
                self._next_page()
                continue

            # 第二步: 打开详情页验证公司规模（快速逐个检查）
            log("验证公司规模...")
            eligible = []
            for job in jobs[:5]:  # 一次最多检查5个
                jid = job["id"]
                ok, reason = self.session.check_company_eligible(jid)
                log(f"  {job.get('title','')[:20]} @ {job.get('company','')[:15]}: {'✓' if ok else '✗'} {reason}")
                if ok:
                    eligible.append(job)
                self.session.random_delay(1, 2)

            if not eligible:
                log("验证后无合适公司，翻页")
                self._next_page()
                continue

            log(f"通过验证 {len(eligible)} 个，模拟浏览中...")

            # 浏览 + 选一个投递
            pick = self._browse_jobs_human(eligible)
            if not pick:
                self._next_page()
                continue

            job_id = pick["id"]
            title = pick.get("title", "")
            company = pick.get("company", "")
            log(f"投递: {title} @ {company} - {pick.get('salary','')}")

            # 准备 HR 自动应答回调
            def make_reply_fn(jt=title, co=company):
                def _reply(hr_msg: str) -> Optional[str]:
                    try:
                        resume_text = resume_module.profile_summary()
                        prompt = f"""你是一位正在求职的 AI 产品经理。HR 回复了你，请根据你的简历和岗位进行回复。

要求：
- 语气自然专业，不要像模板
- 结合你的简历经历回答对方问题
- 适当引导到你的 AI 产品经验优势
- 控制在 150 字以内

### 你的简历
{resume_text}

### 岗位信息
公司: {co}
岗位: {jt}

### HR 最新消息
{hr_msg}

请直接输出回复："""
                        from pipeline.llm import call_light
                        reply = call_light("你是一位正在求职的 AI 产品经理。", prompt)
                        return reply.strip() if reply and len(reply) > 10 else None
                    except Exception as e:
                        log(f"生成回复失败: {e}")
                        return None
                return _reply

            ok = self.session.click_apply(job_id, job_title=title, company=company, reply_fn=make_reply_fn())
            if ok:
                mark_applied(history, job_id, {
                    "keyword": keyword, "city": city, "page": page + 1,
                    "company": pick.get("company", ""), "title": pick.get("title", ""),
                })
                applied += 1
                log(f"✓ ({today_count(load_history())}/{MAX_APPLY_PER_DAY})")
            else:
                log("✗ 投递失败")

            self._next_page()

        return applied

    def _next_page(self):
        ws = self.session._search_tab_ws
        if not ws:
            log("翻页失败：无搜索选项卡")
            return
        for attempt in range(2):
            js = """
            (() => {
                const all = document.querySelectorAll('a, button, span');
                for (const el of all) {
                    if (el.textContent.trim() === '下一页' && el.offsetParent !== null) {
                        el.scrollIntoView({block: 'center'});
                        el.click();
                        return true;
                    }
                }
                return false;
            })()
            """
            result = self.session.browser.evaluate_in_tab(ws, js)
            if str(result) == "true":
                self.session.random_delay(2, 4)
                return
            self.session.random_delay()
        log("翻页失败，可能已到最后一页")

    def _extract_chat_context(self, page_text: str) -> tuple:
        """从聊天页面文本中提取 (company, hr_message)"""
        lines = [l.strip() for l in page_text.split("\n") if l.strip()]
        company = ""
        hr_msg = ""
        # 找公司名：通常在聊天标题区
        for i, l in enumerate(lines):
            if "与" in l and ("沟通" in l or "聊天" in l):
                parts = l.split("与")
                if len(parts) > 1:
                    company = parts[1].split("沟通")[0].split("聊天")[0].strip()
        # 找HR最后一条消息（非自己发的、10-500字符的）
        chat_lines = [l for l in lines if 10 < len(l) < 500]
        for l in reversed(chat_lines):
            if not any(kw in l for kw in ["你好", "我是", "应欣", "很高兴", "感谢", "期待"]):
                hr_msg = l
                break
        return company, hr_msg

    def handle_chats(self, interactive: bool = True):
        """检查并回复HR消息。interactive=True 时逐条征求用户同意。"""
        log("检查新消息...")
        self.session.navigate_to_chats()
        self.session.random_delay(2, 4)

        new_msgs = self.session.check_chat_notifications()
        if new_msgs == 0:
            log("无新消息")
            return

        # 先点开每个未读聊天，收集消息
        log(f"发现 {new_msgs} 条新消息")
        replied = 0

        for i in range(min(new_msgs, 5)):
            try:
                # 尝试点击未读聊天条目
                ws = self.session._search_tab_ws
                if ws:
                    self.session.browser.evaluate_in_tab(ws, """
                    (() => {
                        const items = document.querySelectorAll('[class*="chat-item"], [class*="session"], [class*="list-item"]');
                        for (const el of items) {
                            if (el.querySelector('.unread, [class*="badge"], [class*="dot"]')) {
                                el.click(); return true;
                            }
                        }
                        // fallback: click first unread text
                        const all = document.querySelectorAll('a, div, span');
                        for (const el of all) {
                            if (el.textContent.includes('消息') && el.offsetParent !== null) {
                                el.click(); return true;
                            }
                        }
                        return false;
                    })()
                    """)
                    self.session.random_delay(2, 3)

                page_text = self.session.get_page_text()
                company, hr_msg = self._extract_chat_context(page_text)
                if not hr_msg:
                    continue

                # 生成预回答
                resume_text = resume_module.profile_summary()
                prompt = f"""你是一位正在求职的 AI 产品经理。HR 发来消息，请根据你的简历生成预回复。

    要求：
    - 语气自然专业，展示 AI 产品经验优势
    - 控制在 150 字以内

    ### 你的简历
    {resume_text}

    ### 公司
    {company or "未知公司"}

    ### HR 消息
    {hr_msg}

    请直接输出预回复："""
                from pipeline.llm import call_light
                draft = call_light("你是一位正在求职的 AI 产品经理。", prompt)
                draft = draft.strip() if draft else ""

                if interactive:
                    # 交互模式：征求用户同意
                    print(f"\n{'='*50}")
                    print(f"📩 [{company or '未知公司'}] HR 消息:")
                    print(f"  \"{hr_msg}\"")
                    if draft:
                        print(f"\n🤖 预回复:")
                        print(f"  \"{draft}\"")
                    print(f"\n{'='*50}")
                    choice = input("回复？(y=发送预回复 / 直接输入自定义回复 / n=跳过 / q=退出): ").strip()
                    if choice.lower() == "q":
                        break
                    elif choice.lower() == "n":
                        log(f"跳过 {company or '未知公司'}")
                        continue
                    elif choice.lower() == "y":
                        reply = draft
                    else:
                        reply = choice
                else:
                    reply = draft

                if reply and len(reply) > 5:
                    self.session.send_message(reply)
                    replied += 1
                    log(f"✓ 已回复 {company or '未知公司'}: {reply[:50]}...")
                    self.session.random_delay(3, 5)
                else:
                    log(f"跳过 {company or '未知公司'}: 回复内容太短")

            except Exception as e:
                log(f"回复出错: {e}")

        if replied == 0 and new_msgs > 0:
            log("所有消息均跳过")

    def _extract_latest_message(self, page_text: str) -> Optional[str]:
        lines = [l.strip() for l in page_text.split("\n") if l.strip()]
        chat_lines = [l for l in lines if 10 < len(l) < 500]
        if chat_lines:
            return chat_lines[-1]
        return None

    def _click_all(self, text: str):
        js = f"""
        (() => {{
            const all = document.querySelectorAll('a, button, span, div');
            let count = 0;
            for (const el of all) {{
                if (el.textContent.trim() === {json.dumps(text)} && el.offsetParent !== null) {{
                    el.click();
                    count++;
                }}
            }}
            return count;
        }})()
        """
        return self.session.browser._run_cdp("evaluate", js)

    def close(self):
        self.session.close()
        log("已清理工作页签")


def cmd_init():
    """启动浏览器（用户手动登录）"""
    session = BossSession()
    session.ensure_browser(headed=True)
    print("浏览器已启动，请完成 BOSS 直聘登录")
    print("登录后执行: python agent.py run")


def cmd_run():
    """执行一轮投递 + 交互式回复HR消息"""
    agent = JobAgent()
    try:
        applied = agent.run_once()
        if applied > 0:
            print(f"\n投递完成 ({applied} 家)，是否检查HR消息？")
            choice = input("检查并回复？(y=交互回复 / n=退出): ").strip().lower()
            if choice == "y":
                agent.session.random_delay(2, 4)
                agent.handle_chats(interactive=True)
    except KeyboardInterrupt:
        log("用户中断")
    except Exception as e:
        log(f"运行出错: {e}")
        import traceback
        traceback.print_exc()
    finally:
        agent.close()


def cmd_chat():
    """仅检查并自动回复消息（无人值守模式）"""
    agent = JobAgent()
    agent.session.ensure_browser(headed=True)
    agent.handle_chats(interactive=False)


def cmd_reply():
    """交互式回复HR消息：预回答→确认→发送"""
    agent = JobAgent()
    agent.session.ensure_browser(headed=True)
    agent.handle_chats(interactive=True)


def cmd_status():
    """查看今日状态"""
    history = load_history()
    today = str(date.today())
    todays = history.get(today, {})
    applied = todays.get("applied", [])
    print(f"\n📊 今日状态 ({today})")
    print(f"  投递: {len(applied)}/{MAX_APPLY_PER_DAY}")
    for a in applied:
        print(f"    ✅ {a.get('time','')} - {a.get('keyword','')} - {a.get('city','')}")
    print(f"  总历史天数: {len(history)} 天")
    total = sum(len(v.get("applied", [])) for v in history.values())
    print(f"  累计投递: {total} 次")


def cmd_edit():
    """编辑简历信息"""
    edit_profile()


def cmd_profile():
    """查看当前简历摘要"""
    print(profile_module.profile_summary())


def cmd_history():
    """查看完整历史"""
    history = load_history()
    print(json.dumps(history, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    commands = {
        "init": cmd_init,
        "run": cmd_run,
        "chat": cmd_chat,
        "reply": cmd_reply,
        "status": cmd_status,
        "edit": cmd_edit,
        "profile": cmd_profile,
        "history": cmd_history,
    }
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd in commands:
        commands[cmd]()
    else:
        print(f"用法: python agent.py {{ {'|'.join(commands)} }}")
        print("  init      启动浏览器并登录 BOSS 直聘")
        print("  run       执行一轮搜索投递")
        print("  chat      自动回复HR消息（无人值守）")
        print("  reply     交互式回复HR消息（预回答→确认→发送） ← 推荐")
        print("  status    查看今日投递状态")
        print("  edit      编辑简历信息")
        print("  profile   查看简历摘要")
        print("  history   查看完整历史")
